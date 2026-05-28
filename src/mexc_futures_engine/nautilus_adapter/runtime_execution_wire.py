from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time
from typing import Any

from .runtime_harness import probe_sandbox_nautilus_runtime


REQUIRED_RUNTIME_EXECUTION_OBJECTS = {"AccountState"}


def wire_execution_reports_to_sandbox(
    execution_bundle: dict[str, Any],
    root: Path,
    *,
    venv_dir: str = ".venv-nautilus",
) -> dict[str, Any]:
    sandbox_probe = probe_sandbox_nautilus_runtime(root, venv_dir=venv_dir)
    reports = _extract_reports(execution_bundle)
    if not sandbox_probe.get("importOk"):
        return {
            "timestamp": int(time.time() * 1000),
            "ok": False,
            "sandboxProbe": sandbox_probe,
            "inputReportCount": len(reports),
            "objectCount": 0,
            "objectCounts": {},
            "objects": [],
            "skipped": [],
            "errors": ["sandbox Nautilus runtime import is not available"],
        }

    python_path = Path(str(sandbox_probe["python"]))
    process = subprocess.run(
        [str(python_path), "-c", _SANDBOX_EXECUTION_WIRE_SCRIPT],
        input=json.dumps(
            {
                "reports": reports,
                "accountId": _bundle_account_id(reports),
                "currency": execution_bundle.get("currency") or "USDT",
            },
            separators=(",", ":"),
            ensure_ascii=False,
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    parsed = _parse_json_output(process.stdout)
    errors = list(parsed.get("errors") or [])
    if process.returncode != 0:
        errors.append(process.stderr.strip() or f"sandbox process exited with {process.returncode}")

    objects = parsed.get("objects") if isinstance(parsed.get("objects"), list) else []
    skipped = parsed.get("skipped") if isinstance(parsed.get("skipped"), list) else []
    object_counts = _count_by_key(objects, "class")
    return {
        "timestamp": int(time.time() * 1000),
        "ok": process.returncode == 0 and not errors,
        "sandboxProbe": sandbox_probe,
        "inputReportCount": len(reports),
        "objectCount": len(objects),
        "objectCounts": object_counts,
        "objects": objects,
        "skipped": skipped,
        "errors": errors,
    }


def build_execution_runtime_wire_report(
    *,
    execution_bundle: dict[str, Any],
    sandbox_wire: dict[str, Any],
    symbol: str,
    currency: str,
    live_trading_enabled: bool,
    include_raw: bool = False,
) -> dict[str, Any]:
    object_counts = sandbox_wire.get("objectCounts") if isinstance(sandbox_wire.get("objectCounts"), dict) else {}
    report_counts = (
        execution_bundle.get("reportCounts") if isinstance(execution_bundle.get("reportCounts"), dict) else {}
    )
    blockers: list[str] = []
    warnings: list[str] = []

    if live_trading_enabled:
        blockers.append("live trading flag is enabled; execution runtime wire requires read-only mode")
    if not sandbox_wire.get("ok"):
        blockers.extend(str(error) for error in sandbox_wire.get("errors") or ["sandbox execution wire failed"])

    for required_type in sorted(REQUIRED_RUNTIME_EXECUTION_OBJECTS):
        if int(object_counts.get(required_type) or 0) <= 0:
            blockers.append(f"sandbox wire produced no {required_type} objects")

    known_input_count = sum(int(report_counts.get(name) or 0) for name in _SUPPORTED_REPORT_TYPES)
    if known_input_count and int(sandbox_wire.get("objectCount") or 0) < known_input_count:
        blockers.append("sandbox wire did not construct every supported execution report object")

    sandbox_probe = sandbox_wire.get("sandboxProbe") if isinstance(sandbox_wire.get("sandboxProbe"), dict) else {}
    if sandbox_probe.get("importOk"):
        warnings.append("using sandbox Nautilus wheel runtime; source checkout remains a reference")
    balance_adjustments = _balance_adjustments(sandbox_wire.get("objects", []))
    if balance_adjustments:
        warnings.append("account balance total normalized to satisfy Nautilus total=locked+free invariant")
    if int(report_counts.get("PositionStatusReport") or 0) <= 0:
        warnings.append("MEXC account currently has no open position reports for this symbol")
    if int(report_counts.get("OrderStatusReport") or 0) <= 0:
        warnings.append("MEXC account currently has no order status reports in the requested history window")
    if int(report_counts.get("FillReport") or 0) <= 0:
        warnings.append("MEXC account currently has no fill reports in the requested deals window")
    warnings.append("live submit/cancel remains intentionally unavailable")

    ok = not blockers
    report: dict[str, Any] = {
        "timestamp": int(time.time() * 1000),
        "targetEngine": "NautilusTrader",
        "wireMode": "sandboxed-execution-read-only",
        "symbol": symbol.upper(),
        "currency": currency.upper(),
        "ok": ok,
        "readyForSandboxedNautilusExecutionReadOnly": ok,
        "readyForLiveRuntime": False,
        "executionReports": {
            "source": execution_bundle.get("source"),
            "reportCount": execution_bundle.get("reportCount", 0),
            "reportCounts": report_counts,
        },
        "sandboxWire": {
            "ok": sandbox_wire.get("ok"),
            "inputReportCount": sandbox_wire.get("inputReportCount", 0),
            "objectCount": sandbox_wire.get("objectCount", 0),
            "objectCounts": object_counts,
            "objects": sandbox_wire.get("objects", []),
            "skipped": sandbox_wire.get("skipped", []),
            "errors": sandbox_wire.get("errors", []),
            "balanceAdjustments": balance_adjustments,
        },
        "sandboxProbe": sandbox_probe,
        "blockers": blockers,
        "warnings": warnings,
        "nextPhase": "connect-read-only-nautilus-state-cache-to-strategy-handoff",
    }
    if include_raw:
        report["inputs"] = {
            "executionBundle": execution_bundle,
            "sandboxWire": sandbox_wire,
        }
    return report


def summarize_execution_runtime_wire_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": report["timestamp"],
        "targetEngine": report["targetEngine"],
        "wireMode": report["wireMode"],
        "symbol": report["symbol"],
        "currency": report["currency"],
        "ok": report["ok"],
        "readyForSandboxedNautilusExecutionReadOnly": report["readyForSandboxedNautilusExecutionReadOnly"],
        "readyForLiveRuntime": report["readyForLiveRuntime"],
        "executionReports": report["executionReports"],
        "sandboxWire": report["sandboxWire"],
        "sandboxProbe": report["sandboxProbe"],
        "blockers": report["blockers"],
        "warnings": report["warnings"],
        "nextPhase": report["nextPhase"],
    }


_SUPPORTED_REPORT_TYPES = {
    "AccountState",
    "OrderStatusReport",
    "FillReport",
    "PositionStatusReport",
}


def _extract_reports(execution_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    reports = execution_bundle.get("reports") if isinstance(execution_bundle.get("reports"), list) else []
    return [report for report in reports if isinstance(report, dict)]


def _bundle_account_id(reports: list[dict[str, Any]]) -> str:
    for report in reports:
        if report.get("reportType") != "AccountState":
            continue
        payload = report.get("payload") if isinstance(report.get("payload"), dict) else {}
        account_id = payload.get("accountId")
        if account_id:
            return str(account_id)
    return "MEXC-FUTURES"


def _count_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "")
        if value:
            counts[value] = counts.get(value, 0) + 1
    return counts


def _parse_json_output(stdout: str) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return {"objects": [], "skipped": [], "errors": ["sandbox execution wire produced no output"]}
    try:
        parsed = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        return {"objects": [], "skipped": [], "errors": [f"sandbox execution wire produced invalid JSON: {exc}"]}
    if not isinstance(parsed, dict):
        return {"objects": [], "skipped": [], "errors": ["sandbox execution wire output was not an object"]}
    return parsed


def _balance_adjustments(objects: Any) -> list[dict[str, Any]]:
    if not isinstance(objects, list):
        return []
    adjustments: list[dict[str, Any]] = []
    for item in objects:
        if not isinstance(item, dict):
            continue
        item_adjustments = item.get("balanceAdjustments")
        if isinstance(item_adjustments, list):
            adjustments.extend(adjustment for adjustment in item_adjustments if isinstance(adjustment, dict))
    return adjustments


_SANDBOX_EXECUTION_WIRE_SCRIPT = r"""
from __future__ import annotations

from decimal import Decimal
import json
import sys

from nautilus_trader.core.uuid import UUID4
from nautilus_trader.execution.reports import FillReport
from nautilus_trader.execution.reports import OrderStatusReport
from nautilus_trader.execution.reports import PositionStatusReport
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import LiquiditySide
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import OrderStatus
from nautilus_trader.model.enums import OrderType
from nautilus_trader.model.enums import PositionSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.events import AccountState
from nautilus_trader.model.identifiers import AccountId
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import PositionId
from nautilus_trader.model.identifiers import TradeId
from nautilus_trader.model.identifiers import VenueOrderId
from nautilus_trader.model.objects import AccountBalance
from nautilus_trader.model.objects import Currency
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    reports = payload.get("reports") if isinstance(payload.get("reports"), list) else []
    default_account_id = str(payload.get("accountId") or "MEXC-FUTURES")
    default_currency = str(payload.get("currency") or "USDT").upper()
    objects = []
    skipped = []
    errors = []
    for index, report in enumerate(reports):
        try:
            report_type = report.get("reportType")
            if report_type == "AccountState":
                objects.append(account_state_object(report, default_currency))
            elif report_type == "OrderStatusReport":
                objects.append(order_status_object(report, default_account_id))
            elif report_type == "FillReport":
                objects.append(fill_report_object(report, default_account_id, default_currency))
            elif report_type == "PositionStatusReport":
                objects.append(position_status_object(report, default_account_id))
            else:
                skipped.append({"index": index, "reportType": report_type, "reason": "unsupported report type"})
        except Exception as exc:
            errors.append(
                {
                    "index": index,
                    "reportType": report.get("reportType"),
                    "type": type(exc).__name__,
                    "error": str(exc),
                }
            )
    print(json.dumps({"objects": objects, "skipped": skipped, "errors": errors}, separators=(",", ":")))
    return 0 if not errors else 1


def account_state_object(report, default_currency):
    payload = report_payload(report)
    account_id = AccountId(str(payload.get("accountId") or "MEXC-FUTURES"))
    base_currency = currency_or_none(payload.get("baseCurrency") or default_currency)
    balances = []
    balance_adjustments = []
    for balance in payload.get("balances") or []:
        if not isinstance(balance, dict):
            continue
        currency = balance_currency(balance, default_currency)
        total_value = decimal_value(balance.get("total"))
        locked_value = decimal_value(balance.get("locked"))
        free_value = decimal_value(balance.get("free"))
        model_total = total_value
        if total_value - locked_value != free_value:
            model_total = locked_value + free_value
            balance_adjustments.append(
                {
                    "currency": currency,
                    "sourceTotal": str(total_value),
                    "sourceLocked": str(locked_value),
                    "sourceFree": str(free_value),
                    "modelTotal": str(model_total),
                    "reason": "Nautilus AccountBalance requires total=locked+free",
                }
            )
        balances.append(
            AccountBalance(
                money(model_total, currency),
                money(locked_value, currency),
                money(free_value, currency),
            )
        )
    event = AccountState(
        account_id=account_id,
        account_type=account_type(payload.get("accountType")),
        base_currency=base_currency,
        reported=True,
        balances=balances,
        margins=[],
        info={"source": "MEXC private REST read-only"},
        event_id=UUID4(),
        ts_event=int(report["tsEventNs"]),
        ts_init=int(report["tsInitNs"]),
    )
    return {
        "class": "AccountState",
        "accountId": str(event.account_id),
        "accountType": event.account_type.name,
        "baseCurrency": str(event.base_currency) if event.base_currency is not None else None,
        "balanceCount": len(event.balances),
        "balances": [
            {
                "total": str(balance.total),
                "locked": str(balance.locked),
                "free": str(balance.free),
                "currency": str(balance.currency),
            }
            for balance in event.balances
        ],
        "marginCount": len(event.margins),
        "balanceAdjustments": balance_adjustments,
        "tsEvent": event.ts_event,
        "tsInit": event.ts_init,
    }


def order_status_object(report, default_account_id):
    payload = report_payload(report)
    raw_order_type = int_or_none(payload.get("orderType"))
    order = OrderStatusReport(
        account_id=AccountId(str(payload.get("accountId") or default_account_id)),
        instrument_id=instrument_id(payload),
        venue_order_id=VenueOrderId(required_str(payload.get("venueOrderId"), "venueOrderId")),
        order_side=order_side(payload.get("side")),
        order_type=order_type(raw_order_type),
        time_in_force=time_in_force(raw_order_type),
        order_status=order_status(payload),
        quantity=quantity(payload.get("quantity")),
        filled_qty=quantity(payload.get("filledQuantity")),
        report_id=UUID4(),
        ts_accepted=int(report["tsEventNs"]),
        ts_last=int(report["tsEventNs"]),
        ts_init=int(report["tsInitNs"]),
        client_order_id=client_order_id(payload.get("clientOrderId")),
        venue_position_id=position_id(payload.get("positionId")),
        price=price_or_none(payload.get("price")),
        avg_px=decimal_or_none(payload.get("avgPx")),
        post_only=raw_order_type == 2,
        reduce_only=str(payload.get("side") or "").upper() in {"CLOSE_LONG", "CLOSE_SHORT"},
    )
    return {
        "class": "OrderStatusReport",
        "accountId": str(order.account_id),
        "instrumentId": str(order.instrument_id),
        "venueOrderId": str(order.venue_order_id),
        "clientOrderId": str(order.client_order_id) if order.client_order_id is not None else None,
        "venuePositionId": str(order.venue_position_id) if order.venue_position_id is not None else None,
        "orderSide": order.order_side.name,
        "orderType": order.order_type.name,
        "timeInForce": order.time_in_force.name,
        "orderStatus": order.order_status.name,
        "quantity": str(order.quantity),
        "filledQuantity": str(order.filled_qty),
        "price": str(order.price) if order.price is not None else None,
        "avgPx": str(order.avg_px) if order.avg_px is not None else None,
        "postOnly": bool(order.post_only),
        "reduceOnly": bool(order.reduce_only),
        "rawStateCode": payload.get("rawStateCode"),
        "rawOrderType": payload.get("orderType"),
    }


def fill_report_object(report, default_account_id, default_currency):
    payload = report_payload(report)
    fill = FillReport(
        account_id=AccountId(str(payload.get("accountId") or default_account_id)),
        instrument_id=instrument_id(payload),
        venue_order_id=VenueOrderId(required_str(payload.get("venueOrderId"), "venueOrderId")),
        trade_id=TradeId(str(payload.get("tradeId") or f"{payload.get('venueOrderId')}-{report.get('tsEventNs')}")),
        order_side=order_side(payload.get("side")),
        last_qty=quantity(payload.get("quantity")),
        last_px=price(payload.get("price")),
        commission=money(payload.get("fee"), str(payload.get("feeCurrency") or default_currency).upper()),
        liquidity_side=liquidity_side(payload.get("liquiditySide")),
        report_id=UUID4(),
        ts_event=int(report["tsEventNs"]),
        ts_init=int(report["tsInitNs"]),
        client_order_id=client_order_id(payload.get("clientOrderId")),
        venue_position_id=position_id(payload.get("positionId")),
    )
    return {
        "class": "FillReport",
        "accountId": str(fill.account_id),
        "instrumentId": str(fill.instrument_id),
        "venueOrderId": str(fill.venue_order_id),
        "clientOrderId": str(fill.client_order_id) if fill.client_order_id is not None else None,
        "tradeId": str(fill.trade_id),
        "orderSide": fill.order_side.name,
        "lastQty": str(fill.last_qty),
        "lastPx": str(fill.last_px),
        "commission": str(fill.commission),
        "liquiditySide": fill.liquidity_side.name,
        "tsEvent": fill.ts_event,
        "tsInit": fill.ts_init,
    }


def position_status_object(report, default_account_id):
    payload = report_payload(report)
    position = PositionStatusReport(
        account_id=AccountId(str(payload.get("accountId") or default_account_id)),
        instrument_id=instrument_id(payload),
        position_side=position_side(payload.get("side"), payload.get("rawSideCode")),
        quantity=quantity(payload.get("quantity")),
        report_id=UUID4(),
        ts_last=int(report["tsEventNs"]),
        ts_init=int(report["tsInitNs"]),
        venue_position_id=position_id(payload.get("positionId")),
        avg_px_open=decimal_or_none(payload.get("avgPrice")),
    )
    return {
        "class": "PositionStatusReport",
        "accountId": str(position.account_id),
        "instrumentId": str(position.instrument_id),
        "venuePositionId": str(position.venue_position_id) if position.venue_position_id is not None else None,
        "positionSide": position.position_side.name,
        "quantity": str(position.quantity),
        "avgPxOpen": str(position.avg_px_open) if position.avg_px_open is not None else None,
        "tsLast": position.ts_last,
        "tsInit": position.ts_init,
    }


def report_payload(report):
    payload = report.get("payload") if isinstance(report.get("payload"), dict) else {}
    return payload


def instrument_id(payload):
    return InstrumentId.from_str(required_str(payload.get("instrumentId"), "instrumentId"))


def required_str(value, field):
    if value is None or str(value).strip() == "":
        raise ValueError(f"missing required field: {field}")
    return str(value)


def account_type(value):
    value = str(value or "MARGIN").upper()
    return getattr(AccountType, value)


def currency_or_none(value):
    if value is None:
        return None
    return Currency.from_str(str(value).upper())


def balance_currency(balance, default_currency):
    return str(balance.get("currency") or default_currency).upper()


def money(value, currency):
    return Money.from_str(f"{decimal_string(value)} {currency}")


def price(value):
    return Price.from_str(decimal_string(value))


def price_or_none(value):
    if value is None:
        return None
    return Price.from_str(decimal_string(value))


def quantity(value):
    return Quantity.from_str(decimal_string(value))


def decimal_string(value):
    if value is None or str(value).strip() == "":
        return "0"
    return str(value)


def decimal_value(value):
    return Decimal(decimal_string(value))


def decimal_or_none(value):
    if value is None or str(value).strip() == "":
        return None
    return Decimal(str(value))


def int_or_none(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def client_order_id(value):
    if value is None or str(value).strip() == "":
        return None
    return ClientOrderId(str(value))


def position_id(value):
    if value is None or str(value).strip() == "":
        return None
    return PositionId(str(value))


def order_side(value):
    value = str(value or "").upper()
    if value in {"OPEN_LONG", "CLOSE_SHORT"}:
        return OrderSide.BUY
    if value in {"OPEN_SHORT", "CLOSE_LONG"}:
        return OrderSide.SELL
    return OrderSide.NO_ORDER_SIDE


def order_type(raw_order_type):
    if raw_order_type == 5:
        return OrderType.MARKET
    return OrderType.LIMIT


def time_in_force(raw_order_type):
    if raw_order_type == 3:
        return TimeInForce.IOC
    if raw_order_type == 4:
        return TimeInForce.FOK
    return TimeInForce.GTC


def order_status(payload):
    raw_state = int_or_none(payload.get("rawStateCode"))
    quantity_value = decimal_or_none(payload.get("quantity")) or Decimal("0")
    filled_value = decimal_or_none(payload.get("filledQuantity")) or Decimal("0")
    if raw_state == 3 or (quantity_value > 0 and filled_value >= quantity_value):
        return OrderStatus.FILLED
    if filled_value > 0:
        return OrderStatus.PARTIALLY_FILLED
    if raw_state in {4, 5, 6}:
        return OrderStatus.CANCELED
    if raw_state in {7, 8}:
        return OrderStatus.REJECTED
    return OrderStatus.ACCEPTED


def liquidity_side(value):
    value = str(value or "NO_LIQUIDITY_SIDE").upper()
    return getattr(LiquiditySide, value)


def position_side(value, raw_code):
    value = str(value or "").upper()
    code = int_or_none(raw_code)
    if value in {"OPEN_LONG", "CLOSE_LONG"} or code in {1, 4}:
        return PositionSide.LONG
    if value in {"OPEN_SHORT", "CLOSE_SHORT"} or code in {2, 3}:
        return PositionSide.SHORT
    return PositionSide.FLAT


raise SystemExit(main())
"""
