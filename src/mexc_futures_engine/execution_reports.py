from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import time
from typing import Any

from .market_data import symbol_to_instrument_id
from .nautilus_mapping import MEXC_VENUE


MEXC_SIDE_LABELS = {
    1: "OPEN_LONG",
    2: "CLOSE_SHORT",
    3: "OPEN_SHORT",
    4: "CLOSE_LONG",
}


@dataclass(frozen=True)
class ExecutionReportSpec:
    report_type: str
    venue: str
    ts_event_ns: int
    ts_init_ns: int
    payload: dict[str, Any]
    raw: dict[str, Any] | list[dict[str, Any]]

    def to_dict(self, *, include_raw: bool = True) -> dict[str, Any]:
        data = asdict(self)
        raw = data.pop("raw")
        payload = {
            "reportType": data.pop("report_type"),
            "venue": data.pop("venue"),
            "tsEventNs": data.pop("ts_event_ns"),
            "tsInitNs": data.pop("ts_init_ns"),
            "payload": data.pop("payload"),
        }
        if include_raw:
            payload["raw"] = raw
        return payload


def build_execution_report_bundle(
    *,
    asset_response: dict[str, Any],
    positions_response: dict[str, Any],
    open_orders_response: dict[str, Any],
    history_orders_response: dict[str, Any],
    order_deals_response: dict[str, Any] | None = None,
    symbol: str | None,
    currency: str,
    include_raw: bool = True,
) -> dict[str, Any]:
    ts_init_ns = _now_ms() * 1_000_000
    reports: list[ExecutionReportSpec] = []
    reports.append(_asset_to_account_state(asset_response, currency=currency, ts_init_ns=ts_init_ns))
    reports.extend(_positions_to_reports(_rows(positions_response), ts_init_ns=ts_init_ns))
    reports.extend(_orders_to_reports(_rows(open_orders_response), source="open_orders", ts_init_ns=ts_init_ns))
    reports.extend(_orders_to_reports(_rows(history_orders_response), source="history_orders", ts_init_ns=ts_init_ns))
    if order_deals_response is not None:
        reports.extend(_fills_to_reports(_rows(order_deals_response), ts_init_ns=ts_init_ns))

    report_dicts = [report.to_dict(include_raw=include_raw) for report in reports]
    counts: dict[str, int] = {}
    for report in report_dicts:
        report_type = str(report["reportType"])
        counts[report_type] = counts.get(report_type, 0) + 1

    return {
        "timestamp": int(time.time() * 1000),
        "source": "MEXC private REST read-only",
        "symbol": symbol.upper() if symbol else None,
        "currency": currency.upper(),
        "reportCount": len(report_dicts),
        "reportCounts": counts,
        "reports": report_dicts,
    }


def summarize_execution_report_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": bundle["timestamp"],
        "source": bundle["source"],
        "symbol": bundle["symbol"],
        "currency": bundle["currency"],
        "reportCount": bundle["reportCount"],
        "reportCounts": bundle["reportCounts"],
    }


def _asset_to_account_state(
    response: dict[str, Any],
    *,
    currency: str,
    ts_init_ns: int,
) -> ExecutionReportSpec:
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    ts_event_ns = ts_init_ns
    return ExecutionReportSpec(
        report_type="AccountState",
        venue=MEXC_VENUE,
        ts_event_ns=ts_event_ns,
        ts_init_ns=ts_init_ns,
        payload={
            "accountId": f"{MEXC_VENUE}-FUTURES",
            "accountType": "MARGIN",
            "baseCurrency": currency.upper(),
            "balances": [
                {
                    "currency": str(data.get("currency") or currency).upper(),
                    "total": _decimal_str(data.get("equity")),
                    "free": _decimal_str(data.get("availableBalance")),
                    "locked": _decimal_str(data.get("frozenBalance")),
                    "cashBalance": _decimal_str(data.get("cashBalance")),
                    "unrealized": _decimal_str(data.get("unrealized")),
                    "positionMargin": _decimal_str(data.get("positionMargin")),
                }
            ],
        },
        raw=data,
    )


def _positions_to_reports(rows: list[dict[str, Any]], *, ts_init_ns: int) -> list[ExecutionReportSpec]:
    reports: list[ExecutionReportSpec] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        ts_event_ms = _as_int(row.get("updateTime")) or _as_int(row.get("createTime")) or _now_ms()
        side_code = _as_int(row.get("side") or row.get("positionType"))
        reports.append(
            ExecutionReportSpec(
                report_type="PositionStatusReport",
                venue=MEXC_VENUE,
                ts_event_ns=ts_event_ms * 1_000_000,
                ts_init_ns=ts_init_ns,
                payload={
                    "instrumentId": symbol_to_instrument_id(symbol) if symbol else None,
                    "rawSymbol": symbol or None,
                    "positionId": str(row.get("positionId")) if row.get("positionId") is not None else None,
                    "side": _side_label(side_code),
                    "rawSideCode": side_code,
                    "quantity": _decimal_str(row.get("holdVol") or row.get("vol")),
                    "avgPrice": _decimal_str(row.get("openAvgPrice") or row.get("avgPrice")),
                    "unrealized": _decimal_str(row.get("unrealized")),
                    "leverage": _as_int(row.get("leverage")),
                },
                raw=row,
            )
        )
    return reports


def _orders_to_reports(rows: list[dict[str, Any]], *, source: str, ts_init_ns: int) -> list[ExecutionReportSpec]:
    reports: list[ExecutionReportSpec] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        ts_event_ms = _as_int(row.get("updateTime")) or _as_int(row.get("createTime")) or _now_ms()
        side_code = _as_int(row.get("side"))
        reports.append(
            ExecutionReportSpec(
                report_type="OrderStatusReport",
                venue=MEXC_VENUE,
                ts_event_ns=ts_event_ms * 1_000_000,
                ts_init_ns=ts_init_ns,
                payload={
                    "source": source,
                    "instrumentId": symbol_to_instrument_id(symbol) if symbol else None,
                    "rawSymbol": symbol or None,
                    "venueOrderId": str(row.get("orderId")) if row.get("orderId") is not None else None,
                    "clientOrderId": str(row.get("externalOid")) if row.get("externalOid") is not None else None,
                    "orderType": row.get("orderType"),
                    "side": _side_label(side_code),
                    "rawSideCode": side_code,
                    "rawStateCode": row.get("state"),
                    "price": _decimal_str(row.get("price")),
                    "quantity": _decimal_str(row.get("vol")),
                    "filledQuantity": _decimal_str(row.get("dealVol")),
                    "avgPx": _decimal_str(row.get("dealAvgPrice")),
                    "leverage": _as_int(row.get("leverage")),
                    "openType": row.get("openType"),
                    "positionId": str(row.get("positionId")) if row.get("positionId") is not None else None,
                    "fee": _decimal_str(row.get("totalFee") or row.get("fee")),
                    "feeCurrency": row.get("feeCurrency"),
                    "profit": _decimal_str(row.get("profit")),
                },
                raw=row,
            )
        )
    return reports


def _fills_to_reports(rows: list[dict[str, Any]], *, ts_init_ns: int) -> list[ExecutionReportSpec]:
    reports: list[ExecutionReportSpec] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        ts_event_ms = _as_int(row.get("timestamp")) or _now_ms()
        side_code = _as_int(row.get("side"))
        reports.append(
            ExecutionReportSpec(
                report_type="FillReport",
                venue=MEXC_VENUE,
                ts_event_ns=ts_event_ms * 1_000_000,
                ts_init_ns=ts_init_ns,
                payload={
                    "instrumentId": symbol_to_instrument_id(symbol) if symbol else None,
                    "rawSymbol": symbol or None,
                    "venueOrderId": str(row.get("orderId")) if row.get("orderId") is not None else None,
                    "tradeId": str(row.get("id")) if row.get("id") is not None else None,
                    "clientOrderId": str(row.get("externalOid")) if row.get("externalOid") is not None else None,
                    "side": _side_label(side_code),
                    "rawSideCode": side_code,
                    "price": _decimal_str(row.get("price")),
                    "quantity": _decimal_str(row.get("vol")),
                    "liquiditySide": "TAKER" if row.get("taker") is True else "MAKER" if row.get("taker") is False else None,
                    "fee": _decimal_str(row.get("fee")),
                    "feeCurrency": row.get("feeCurrency"),
                    "profit": _decimal_str(row.get("profit")),
                },
                raw=row,
            )
        )
    return reports


def _rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict) and isinstance(data.get("resultList"), list):
        return [row for row in data["resultList"] if isinstance(row, dict)]
    return []


def _side_label(side_code: int | None) -> str | None:
    if side_code is None:
        return None
    return MEXC_SIDE_LABELS.get(side_code, f"MEXC_SIDE_{side_code}")


def _decimal_str(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except (InvalidOperation, ValueError):
        return str(value)


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _now_ms() -> int:
    return int(time.time() * 1000)
