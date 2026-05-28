from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import time
from typing import Any

from .nautilus_mapping import MEXC_VENUE


@dataclass(frozen=True)
class MarketDataEventSpec:
    event_type: str
    instrument_id: str
    raw_symbol: str
    venue: str
    ts_event_ns: int
    ts_init_ns: int
    sequence: int | None
    payload: dict[str, Any]
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {
            "eventType": data.pop("event_type"),
            "instrumentId": data.pop("instrument_id"),
            "rawSymbol": data.pop("raw_symbol"),
            "venue": data.pop("venue"),
            "tsEventNs": data.pop("ts_event_ns"),
            "tsInitNs": data.pop("ts_init_ns"),
            "sequence": data.pop("sequence"),
            "payload": data.pop("payload"),
            "raw": data.pop("raw"),
        }


def parse_public_ws_message(
    message: dict[str, Any],
    *,
    ts_init_ms: int | None = None,
) -> list[MarketDataEventSpec]:
    return MarketDataParser().parse_public_ws_message(message, ts_init_ms=ts_init_ms)


def parse_public_ws_messages(messages: list[dict[str, Any]]) -> list[MarketDataEventSpec]:
    parser = MarketDataParser()
    events: list[MarketDataEventSpec] = []
    for message in messages:
        events.extend(parser.parse_public_ws_message(message))
    return events


class MarketDataParser:
    def __init__(self) -> None:
        self._books: dict[str, _DepthBook] = {}

    def parse_public_ws_message(
        self,
        message: dict[str, Any],
        *,
        ts_init_ms: int | None = None,
    ) -> list[MarketDataEventSpec]:
        channel = str(message.get("channel") or "")
        if channel.startswith("rs.sub."):
            return []
        if channel == "push.ticker":
            event = _parse_ticker(message, ts_init_ms=ts_init_ms)
            return [event] if event else []
        if channel == "push.deal":
            event = _parse_deal(message, ts_init_ms=ts_init_ms)
            return [event] if event else []
        if channel == "push.depth":
            book = _parse_depth(message, ts_init_ms=ts_init_ms)
            if book is None:
                return []
            depth_book = self._books.setdefault(book.raw_symbol, _DepthBook())
            quote_payload = depth_book.apply(book.payload)
            events = []
            if quote_payload is not None:
                events.append(_depth_quote_from_book(book, quote_payload))
            events.append(book)
            return events
        return []


class _DepthBook:
    def __init__(self) -> None:
        self._bids: dict[Decimal, Decimal] = {}
        self._asks: dict[Decimal, Decimal] = {}
        self._last_quote: tuple[str, str, str, str] | None = None

    def apply(self, payload: dict[str, Any]) -> dict[str, str] | None:
        deltas = payload.get("deltas") if isinstance(payload.get("deltas"), list) else []
        for row in deltas:
            if not isinstance(row, dict):
                continue
            price = _as_decimal(row.get("price"))
            size = _as_decimal(row.get("size"))
            if price is None or size is None:
                continue
            levels = self._bids if row.get("side") == "BID" else self._asks
            if size <= 0 or row.get("action") == "DELETE":
                levels.pop(price, None)
            else:
                levels[price] = size

        top_bid = self._top_bid()
        top_ask = self._top_ask()
        if top_bid is None or top_ask is None:
            return None
        bid_price, bid_size = top_bid
        ask_price, ask_size = top_ask
        price_precision = max(_decimal_places(bid_price), _decimal_places(ask_price))
        size_precision = max(_decimal_places(bid_size), _decimal_places(ask_size))
        quote = (
            _decimal_string(bid_price, precision=price_precision),
            _decimal_string(ask_price, precision=price_precision),
            _decimal_string(bid_size, precision=size_precision),
            _decimal_string(ask_size, precision=size_precision),
        )
        if quote == self._last_quote:
            return None
        self._last_quote = quote
        return {
            "bidPrice": quote[0],
            "askPrice": quote[1],
            "bidSize": quote[2],
            "askSize": quote[3],
        }

    def _top_bid(self) -> tuple[Decimal, Decimal] | None:
        if not self._bids:
            return None
        price = max(self._bids)
        return price, self._bids[price]

    def _top_ask(self) -> tuple[Decimal, Decimal] | None:
        if not self._asks:
            return None
        price = min(self._asks)
        return price, self._asks[price]


def _depth_quote_from_book(book: MarketDataEventSpec, quote_payload: dict[str, str]) -> MarketDataEventSpec:
    payload = {
        **quote_payload,
        "source": "MEXC push.depth",
        "bookSequence": book.sequence,
        "beginSequence": book.payload.get("beginSequence"),
        "endSequence": book.payload.get("endSequence"),
        "version": book.payload.get("version"),
        "note": "Derived from maintained depth book with real top-of-book sizes.",
    }
    return MarketDataEventSpec(
        event_type="QuoteTick",
        instrument_id=book.instrument_id,
        raw_symbol=book.raw_symbol,
        venue=book.venue,
        ts_event_ns=book.ts_event_ns,
        ts_init_ns=book.ts_init_ns,
        sequence=book.sequence,
        payload=payload,
        raw=book.raw,
    )


def _parse_public_ws_message_stateless(
    message: dict[str, Any],
    *,
    ts_init_ms: int | None = None,
) -> list[MarketDataEventSpec]:
    channel = str(message.get("channel") or "")
    if channel.startswith("rs.sub."):
        return []
    if channel == "push.ticker":
        event = _parse_ticker(message, ts_init_ms=ts_init_ms)
        return [event] if event else []
    if channel == "push.deal":
        event = _parse_deal(message, ts_init_ms=ts_init_ms)
        return [event] if event else []
    if channel == "push.depth":
        book = _parse_depth(message, ts_init_ms=ts_init_ms)
        return [book] if book else []
    return []


def symbol_to_instrument_id(symbol: str, *, venue: str = MEXC_VENUE) -> str:
    return f"{symbol.upper()}-PERP.{venue}"


def _parse_ticker(message: dict[str, Any], *, ts_init_ms: int | None) -> MarketDataEventSpec | None:
    data = message.get("data") if isinstance(message.get("data"), dict) else {}
    symbol = _message_symbol(message, data)
    if not symbol:
        return None

    ts_event_ms = _as_int(data.get("timestamp")) or _as_int(message.get("ts")) or _now_ms()
    return MarketDataEventSpec(
        event_type="QuoteTick",
        instrument_id=symbol_to_instrument_id(symbol),
        raw_symbol=symbol,
        venue=MEXC_VENUE,
        ts_event_ns=ts_event_ms * 1_000_000,
        ts_init_ns=_ts_init_ns(ts_init_ms),
        sequence=None,
        payload={
            "bidPrice": _as_decimal_string(data.get("bid1")),
            "askPrice": _as_decimal_string(data.get("ask1")),
            "bidSize": None,
            "askSize": None,
            "lastPrice": _as_decimal_string(data.get("lastPrice")),
            "fairPrice": _as_decimal_string(data.get("fairPrice")),
            "indexPrice": _as_decimal_string(data.get("indexPrice")),
            "fundingRate": _as_decimal_string(data.get("fundingRate")),
            "source": "MEXC push.ticker",
            "note": "MEXC ticker does not include top-of-book sizes; use depth stream for book sizes.",
        },
        raw=message,
    )


def _parse_deal(message: dict[str, Any], *, ts_init_ms: int | None) -> MarketDataEventSpec | None:
    data = message.get("data") if isinstance(message.get("data"), dict) else {}
    symbol = _message_symbol(message, data)
    if not symbol:
        return None

    ts_event_ms = _as_int(data.get("t")) or _as_int(message.get("ts")) or _now_ms()
    return MarketDataEventSpec(
        event_type="TradeTick",
        instrument_id=symbol_to_instrument_id(symbol),
        raw_symbol=symbol,
        venue=MEXC_VENUE,
        ts_event_ns=ts_event_ms * 1_000_000,
        ts_init_ns=_ts_init_ns(ts_init_ms),
        sequence=None,
        payload={
            "tradeId": str(data.get("i")) if data.get("i") is not None else None,
            "price": _as_decimal_string(data.get("p")),
            "size": _as_decimal_string(data.get("v")),
            "aggressorSide": "NO_AGGRESSOR",
            "rawTradeTypeCode": data.get("T"),
            "rawOrderSideCode": data.get("O"),
            "rawMatchTypeCode": data.get("M"),
            "source": "MEXC push.deal",
        },
        raw=message,
    )


def _parse_depth(message: dict[str, Any], *, ts_init_ms: int | None) -> MarketDataEventSpec | None:
    data = message.get("data") if isinstance(message.get("data"), dict) else {}
    symbol = _message_symbol(message, data)
    if not symbol:
        return None

    ts_event_ms = _as_int(message.get("ts")) or _now_ms()
    version = _as_int(data.get("version")) or _as_int(data.get("end"))
    deltas = [
        *_parse_depth_rows(data.get("bids"), side="BID"),
        *_parse_depth_rows(data.get("asks"), side="ASK"),
    ]
    return MarketDataEventSpec(
        event_type="OrderBookDeltas",
        instrument_id=symbol_to_instrument_id(symbol),
        raw_symbol=symbol,
        venue=MEXC_VENUE,
        ts_event_ns=ts_event_ms * 1_000_000,
        ts_init_ns=_ts_init_ns(ts_init_ms),
        sequence=version,
        payload={
            "bookType": "L2_MBP",
            "beginSequence": _as_int(data.get("begin")),
            "endSequence": _as_int(data.get("end")),
            "version": version,
            "deltas": deltas,
            "source": "MEXC push.depth",
        },
        raw=message,
    )


def _parse_depth_rows(rows: Any, *, side: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []

    deltas: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 2:
            continue
        size = _as_float(row[1])
        action = "DELETE" if size == 0 else "UPDATE"
        deltas.append(
            {
                "side": side,
                "action": action,
                "price": _as_decimal_string(row[0]),
                "size": _as_decimal_string(row[1]),
                "orderCount": _as_int(row[2]) if len(row) > 2 else None,
            }
        )
    return deltas


def _message_symbol(message: dict[str, Any], data: dict[str, Any]) -> str | None:
    raw_symbol = message.get("symbol") or data.get("symbol")
    if not raw_symbol:
        return None
    return str(raw_symbol).upper()


def _ts_init_ns(ts_init_ms: int | None) -> int:
    return (ts_init_ms if ts_init_ms is not None else _now_ms()) * 1_000_000


def _now_ms() -> int:
    return int(time.time() * 1000)


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _decimal_places(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    return abs(exponent) if exponent < 0 else 0


def _decimal_string(value: Decimal, *, precision: int | None = None) -> str:
    if precision is not None:
        return format(value, f".{precision}f")
    return format(value.normalize(), "f")


def _as_decimal_string(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except (InvalidOperation, ValueError):
        return str(value)
