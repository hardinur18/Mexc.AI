from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


MEXC_VENUE = "MEXC"


@dataclass(frozen=True)
class NautilusInstrumentSpec:
    venue: str
    instrument_type: str
    instrument_id: str
    raw_symbol: str
    base_currency: str
    quote_currency: str
    settlement_currency: str
    is_inverse: bool
    price_precision: int
    size_precision: int
    price_increment: str
    size_increment: str
    multiplier: str
    lot_size: str
    min_quantity: str | None
    max_quantity: str | None
    margin_init: str | None
    margin_maint: str | None
    maker_fee: str | None
    taker_fee: str | None
    ts_event_ns: int | None
    info: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {
            "venue": data.pop("venue"),
            "instrumentType": data.pop("instrument_type"),
            "instrumentId": data.pop("instrument_id"),
            "rawSymbol": data.pop("raw_symbol"),
            "baseCurrency": data.pop("base_currency"),
            "quoteCurrency": data.pop("quote_currency"),
            "settlementCurrency": data.pop("settlement_currency"),
            "isInverse": data.pop("is_inverse"),
            "pricePrecision": data.pop("price_precision"),
            "sizePrecision": data.pop("size_precision"),
            "priceIncrement": data.pop("price_increment"),
            "sizeIncrement": data.pop("size_increment"),
            "multiplier": data.pop("multiplier"),
            "lotSize": data.pop("lot_size"),
            "minQuantity": data.pop("min_quantity"),
            "maxQuantity": data.pop("max_quantity"),
            "marginInit": data.pop("margin_init"),
            "marginMaint": data.pop("margin_maint"),
            "makerFee": data.pop("maker_fee"),
            "takerFee": data.pop("taker_fee"),
            "tsEventNs": data.pop("ts_event_ns"),
            "info": data.pop("info"),
        }


def contract_row_to_nautilus_spec(row: dict[str, Any], *, venue: str = MEXC_VENUE) -> NautilusInstrumentSpec:
    symbol = _required_str(row, "symbol").upper()
    base_currency = _required_str(row, "baseCoin").upper()
    quote_currency = _required_str(row, "quoteCoin").upper()
    settlement_currency = str(row.get("settleCoin") or quote_currency).upper()
    price_unit = _required_decimal_str(row, "priceUnit")
    vol_unit = _required_decimal_str(row, "volUnit")
    contract_size = _required_decimal_str(row, "contractSize")
    price_precision = _required_int(row, "priceScale")
    size_precision = int(row.get("volScale") or 0)
    created_ms = _as_int(row.get("createTime"))

    return NautilusInstrumentSpec(
        venue=venue,
        instrument_type="CryptoPerpetual",
        instrument_id=f"{symbol}-PERP.{venue}",
        raw_symbol=symbol,
        base_currency=base_currency,
        quote_currency=quote_currency,
        settlement_currency=settlement_currency,
        is_inverse=settlement_currency == base_currency,
        price_precision=price_precision,
        size_precision=size_precision,
        price_increment=price_unit,
        size_increment=vol_unit,
        multiplier=contract_size,
        lot_size=vol_unit,
        min_quantity=_decimal_str(row.get("minVol")),
        max_quantity=_decimal_str(row.get("maxVol")),
        margin_init=_decimal_str(row.get("initialMarginRate")),
        margin_maint=_decimal_str(row.get("maintenanceMarginRate")),
        maker_fee=_decimal_str(row.get("makerFeeRate")),
        taker_fee=_decimal_str(row.get("takerFeeRate")),
        ts_event_ns=created_ms * 1_000_000 if created_ms is not None else None,
        info={
            "apiAllowed": row.get("apiAllowed"),
            "state": row.get("state"),
            "isHidden": row.get("isHidden"),
            "minLeverage": row.get("minLeverage"),
            "maxLeverage": row.get("maxLeverage"),
            "riskLimitMode": row.get("riskLimitMode"),
            "riskLimitType": row.get("riskLimitType"),
            "riskLimitCustom": row.get("riskLimitCustom"),
            "source": "MEXC /api/v1/contract/detail/country",
        },
    )


def _required_str(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"missing required contract field: {key}")
    return str(value)


def _required_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if value is None:
        raise ValueError(f"missing required contract field: {key}")
    return int(value)


def _required_decimal_str(row: dict[str, Any], key: str) -> str:
    value = _decimal_str(row.get(key))
    if value is None:
        raise ValueError(f"missing required contract field: {key}")
    return value


def _decimal_str(value: Any) -> str | None:
    if value is None:
        return None
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return format(decimal.normalize(), "f")


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
