from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


MEXC_CANDLE_INTERVALS: dict[str, str] = {
    "1m": "Min1",
    "5m": "Min5",
    "15m": "Min15",
    "30m": "Min30",
    "1h": "Min60",
    "4h": "Hour4",
    "8h": "Hour8",
    "1d": "Day1",
    "1w": "Week1",
    "1M": "Month1",
}

_MEXC_TO_CANONICAL_INTERVAL = {value: key for key, value in MEXC_CANDLE_INTERVALS.items()}
_CANDLE_INTERVAL_MS = {
    "1m": 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "8h": 8 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
    "1w": 7 * 24 * 60 * 60_000,
    "1M": 30 * 24 * 60 * 60_000,
}


class CandleParseError(ValueError):
    pass


@dataclass(frozen=True)
class Candle:
    symbol: str
    interval: str
    exchange_interval: str
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    close_time_ms: int | None = None
    is_closed: bool | None = None
    source: str = "MEXC"
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("open", "high", "low", "close", "volume", "quote_volume"):
            data[key] = _decimal_string(getattr(self, key))
        return data


def mexc_candle_interval(interval: str) -> str:
    if interval in MEXC_CANDLE_INTERVALS:
        return MEXC_CANDLE_INTERVALS[interval]
    if interval in _MEXC_TO_CANONICAL_INTERVAL:
        return interval
    raise CandleParseError(f"unsupported MEXC candle interval: {interval}")


def canonical_candle_interval(interval: str) -> str:
    if interval in MEXC_CANDLE_INTERVALS:
        return interval
    if interval in _MEXC_TO_CANONICAL_INTERVAL:
        return _MEXC_TO_CANONICAL_INTERVAL[interval]
    raise CandleParseError(f"unsupported MEXC candle interval: {interval}")


def candle_interval_ms(interval: str) -> int:
    canonical = canonical_candle_interval(interval)
    return _CANDLE_INTERVAL_MS[canonical]


def parse_rest_klines(response: dict[str, Any], *, symbol: str, interval: str) -> list[Candle]:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    times = _list_field(data, "time")
    opens = _list_field(data, "open")
    highs = _list_field(data, "high")
    lows = _list_field(data, "low")
    closes = _list_field(data, "close")
    volumes = _list_field(data, "vol")
    amounts = _list_field(data, "amount")

    row_count = min(len(times), len(opens), len(highs), len(lows), len(closes), len(volumes), len(amounts))
    exchange_interval = mexc_candle_interval(interval)
    canonical_interval = canonical_candle_interval(interval)

    candles: list[Candle] = []
    for index in range(row_count):
        raw = {
            "time": times[index],
            "open": opens[index],
            "high": highs[index],
            "low": lows[index],
            "close": closes[index],
            "vol": volumes[index],
            "amount": amounts[index],
        }
        candles.append(
            Candle(
                symbol=symbol.upper(),
                interval=canonical_interval,
                exchange_interval=exchange_interval,
                open_time_ms=_timestamp_ms(times[index]),
                open=_decimal(opens[index], "open"),
                high=_decimal(highs[index], "high"),
                low=_decimal(lows[index], "low"),
                close=_decimal(closes[index], "close"),
                volume=_decimal(volumes[index], "vol"),
                quote_volume=_decimal(amounts[index], "amount"),
                source="MEXC REST /api/v1/contract/kline",
                raw=raw,
            )
        )
    return candles


def parse_ws_kline(message: dict[str, Any]) -> Candle | None:
    if message.get("channel") != "push.kline":
        return None
    data = message.get("data") if isinstance(message.get("data"), dict) else {}
    symbol = message.get("symbol") or data.get("symbol")
    interval = data.get("interval")
    if not symbol or not interval:
        return None

    open_time_ms = _timestamp_ms(_required(data, "t"))
    return Candle(
        symbol=str(symbol).upper(),
        interval=canonical_candle_interval(str(interval)),
        exchange_interval=mexc_candle_interval(str(interval)),
        open_time_ms=open_time_ms,
        close_time_ms=_timestamp_ms(message["ts"]) if message.get("ts") is not None else None,
        open=_decimal(_required(data, "o"), "o"),
        high=_decimal(_required(data, "h"), "h"),
        low=_decimal(_required(data, "l"), "l"),
        close=_decimal(_required(data, "c"), "c"),
        volume=_decimal(_required(data, "q"), "q"),
        quote_volume=_decimal(_required(data, "a"), "a"),
        is_closed=None,
        source="MEXC WS push.kline",
        raw=message,
    )


def _list_field(data: dict[str, Any], key: str) -> list[Any]:
    value = data.get(key)
    return value if isinstance(value, list) else []


def _required(data: dict[str, Any], key: str) -> Any:
    if key not in data:
        raise CandleParseError(f"missing candle field: {key}")
    return data[key]


def _timestamp_ms(value: Any) -> int:
    timestamp = int(value)
    if timestamp < 10_000_000_000:
        return timestamp * 1000
    return timestamp


def _decimal(value: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CandleParseError(f"invalid decimal for {field_name}: {value}") from exc


def _decimal_string(value: Decimal) -> str:
    return format(value.normalize(), "f")
