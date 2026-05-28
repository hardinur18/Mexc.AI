from __future__ import annotations

from decimal import Decimal, InvalidOperation
import time
from typing import Any


ACTIVE_ORDER_STATUSES = {"ACCEPTED", "PARTIALLY_FILLED", "SUBMITTED", "PENDING_UPDATE"}


def build_nautilus_state_handoff_report(
    *,
    instrument_wire: dict[str, Any],
    market_wire: dict[str, Any],
    execution_wire: dict[str, Any],
    strategy_signal: dict[str, Any] | None,
    symbol: str,
    currency: str,
    live_trading_enabled: bool,
    include_raw: bool = False,
) -> dict[str, Any]:
    symbol = symbol.upper()
    currency = currency.upper()
    state_cache = _build_state_cache(
        instrument_wire=instrument_wire,
        market_wire=market_wire,
        execution_wire=execution_wire,
        symbol=symbol,
        currency=currency,
    )
    blockers = _handoff_blockers(
        instrument_wire=instrument_wire,
        market_wire=market_wire,
        execution_wire=execution_wire,
        state_cache=state_cache,
        live_trading_enabled=live_trading_enabled,
    )
    warnings = _handoff_warnings(
        market_wire=market_wire,
        execution_wire=execution_wire,
        state_cache=state_cache,
    )
    strategy_preview = _strategy_preview(strategy_signal)
    if strategy_preview.get("side") == "hold":
        warnings.append("strategy preview is hold; no candidate order handoff")

    ready = not blockers
    report: dict[str, Any] = {
        "timestamp": int(time.time() * 1000),
        "targetEngine": "NautilusTrader",
        "handoffMode": "sandboxed-state-cache-to-strategy-read-only",
        "symbol": symbol,
        "currency": currency,
        "ok": ready,
        "readyForStrategyReadOnly": ready,
        "readyForLiveRuntime": False,
        "stateCache": state_cache,
        "strategyHandoff": {
            "safeToEvaluateSignals": ready,
            "safeToOpenNewPositionPreflight": ready
            and state_cache["account"]["globalOpenPositionCount"] == 0
            and state_cache["account"]["globalActiveOrderCount"] == 0,
            "requiresPreflightBeforeAnyLiveOrder": True,
            "source": "Nautilus sandbox wire objects + MEXC real read-only strategy preview",
            "strategyPreview": strategy_preview,
        },
        "wires": {
            "instrument": _wire_summary(instrument_wire, ready_key="readyForSandboxedNautilusRuntimeReadOnly"),
            "market": _wire_summary(market_wire, ready_key="readyForSandboxedNautilusMarketDataReadOnly"),
            "execution": _wire_summary(execution_wire, ready_key="readyForSandboxedNautilusExecutionReadOnly"),
        },
        "blockers": blockers,
        "warnings": warnings,
        "nextPhase": "persist-state-handoff-loop-and-paper-trading-audit",
    }
    if include_raw:
        report["inputs"] = {
            "instrumentWire": instrument_wire,
            "marketWire": market_wire,
            "executionWire": execution_wire,
            "strategySignal": strategy_signal,
        }
    return report


def summarize_nautilus_state_handoff_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": report["timestamp"],
        "targetEngine": report["targetEngine"],
        "handoffMode": report["handoffMode"],
        "symbol": report["symbol"],
        "currency": report["currency"],
        "ok": report["ok"],
        "readyForStrategyReadOnly": report["readyForStrategyReadOnly"],
        "readyForLiveRuntime": report["readyForLiveRuntime"],
        "stateCache": report["stateCache"],
        "strategyHandoff": report["strategyHandoff"],
        "wires": report["wires"],
        "blockers": report["blockers"],
        "warnings": report["warnings"],
        "nextPhase": report["nextPhase"],
    }


def _build_state_cache(
    *,
    instrument_wire: dict[str, Any],
    market_wire: dict[str, Any],
    execution_wire: dict[str, Any],
    symbol: str,
    currency: str,
) -> dict[str, Any]:
    instrument_objects = _objects(instrument_wire)
    market_objects = _objects(market_wire)
    execution_objects = _objects(execution_wire)
    account = _first_object(execution_objects, "AccountState") or {}
    all_position_objects = _objects_by_class(execution_objects, "PositionStatusReport")
    all_order_objects = _objects_by_class(execution_objects, "OrderStatusReport")
    fill_objects = _objects_by_class(execution_objects, "FillReport")
    target_instrument_id = f"{symbol}-PERP.MEXC"
    position_objects = _objects_for_instrument(all_position_objects, target_instrument_id)
    order_objects = _objects_for_instrument(all_order_objects, target_instrument_id)
    global_active_orders = [
        order for order in all_order_objects if str(order.get("orderStatus") or "").upper() in ACTIVE_ORDER_STATUSES
    ]
    active_orders = [
        order for order in order_objects if str(order.get("orderStatus") or "").upper() in ACTIVE_ORDER_STATUSES
    ]

    return {
        "source": "sandboxed Nautilus runtime wire output",
        "symbol": symbol,
        "currency": currency,
        "instrument": _instrument_summary(_first_object(instrument_objects, "CryptoPerpetual")),
        "market": _market_summary(market_objects),
        "account": _account_summary(
            account=account,
            positions=position_objects,
            active_orders=active_orders,
            global_positions=all_position_objects,
            global_active_orders=global_active_orders,
            fills=fill_objects,
            currency=currency,
        ),
        "execution": {
            "recentOrderCount": len(order_objects),
            "globalRecentOrderCount": len(all_order_objects),
            "activeOrderCount": len(active_orders),
            "globalActiveOrderCount": len(global_active_orders),
            "recentFillCount": len(fill_objects),
            "latestOrder": _latest_execution_object(order_objects),
            "latestFill": _latest_execution_object(fill_objects),
            "balanceAdjustments": _balance_adjustments(execution_wire),
        },
    }


def _handoff_blockers(
    *,
    instrument_wire: dict[str, Any],
    market_wire: dict[str, Any],
    execution_wire: dict[str, Any],
    state_cache: dict[str, Any],
    live_trading_enabled: bool,
) -> list[str]:
    blockers: list[str] = []
    if live_trading_enabled:
        blockers.append("live trading flag is enabled; state handoff requires read-only mode")
    if not instrument_wire.get("ok"):
        blockers.extend(_wire_errors("instrument wire", instrument_wire))
    if not market_wire.get("ok"):
        blockers.extend(_wire_errors("market wire", market_wire))
    if not execution_wire.get("ok"):
        blockers.extend(_wire_errors("execution wire", execution_wire))
    if not state_cache["instrument"].get("instrumentId"):
        blockers.append("state cache has no CryptoPerpetual instrument")
    if not state_cache["market"].get("hasTradeTick"):
        blockers.append("state cache has no TradeTick market object")
    if not state_cache["market"].get("hasQuoteTick"):
        blockers.append("state cache has no QuoteTick market object")
    if not state_cache["market"].get("hasOrderBookDeltas"):
        blockers.append("state cache has no OrderBookDeltas market object")
    if not state_cache["account"].get("accountId"):
        blockers.append("state cache has no AccountState object")
    return blockers


def _handoff_warnings(
    *,
    market_wire: dict[str, Any],
    execution_wire: dict[str, Any],
    state_cache: dict[str, Any],
) -> list[str]:
    warnings = []
    warnings.extend(str(warning) for warning in market_wire.get("warnings") or [])
    warnings.extend(str(warning) for warning in execution_wire.get("warnings") or [])
    if state_cache["execution"].get("balanceAdjustments"):
        warnings.append("state cache carries normalized account balance totals from execution wire")
    if state_cache["account"]["openPositionCount"] > 0:
        warnings.append("strategy handoff sees existing open position state")
    if state_cache["execution"]["activeOrderCount"] > 0:
        warnings.append("strategy handoff sees active order state")
    warnings.append("live submit/cancel remains intentionally unavailable")
    return _dedupe(warnings)


def _wire_summary(wire: dict[str, Any], *, ready_key: str) -> dict[str, Any]:
    sandbox_wire = wire.get("sandboxWire") if isinstance(wire.get("sandboxWire"), dict) else {}
    return {
        "ok": bool(wire.get("ok")),
        "ready": bool(wire.get(ready_key)),
        "wireMode": wire.get("wireMode"),
        "objectCount": sandbox_wire.get("objectCount", 0),
        "objectCounts": sandbox_wire.get("objectCounts", {}),
        "blockers": wire.get("blockers", []),
        "errors": sandbox_wire.get("errors", []),
    }


def _wire_errors(label: str, wire: dict[str, Any]) -> list[str]:
    sandbox_wire = wire.get("sandboxWire") if isinstance(wire.get("sandboxWire"), dict) else {}
    errors = wire.get("blockers") or sandbox_wire.get("errors") or [f"{label} failed"]
    return [f"{label}: {error}" for error in errors]


def _objects(wire: dict[str, Any]) -> list[dict[str, Any]]:
    sandbox_wire = wire.get("sandboxWire") if isinstance(wire.get("sandboxWire"), dict) else {}
    objects = sandbox_wire.get("objects") if isinstance(sandbox_wire.get("objects"), list) else []
    return [item for item in objects if isinstance(item, dict)]


def _objects_by_class(objects: list[dict[str, Any]], class_name: str) -> list[dict[str, Any]]:
    return [item for item in objects if item.get("class") == class_name]


def _objects_for_instrument(objects: list[dict[str, Any]], instrument_id: str) -> list[dict[str, Any]]:
    return [item for item in objects if str(item.get("instrumentId") or "") == instrument_id]


def _first_object(objects: list[dict[str, Any]], class_name: str) -> dict[str, Any] | None:
    for item in objects:
        if item.get("class") == class_name:
            return item
    return None


def _instrument_summary(instrument: dict[str, Any] | None) -> dict[str, Any]:
    instrument = instrument or {}
    return {
        "instrumentId": instrument.get("instrumentId"),
        "rawSymbol": instrument.get("rawSymbol"),
        "baseCurrency": instrument.get("baseCurrency"),
        "quoteCurrency": instrument.get("quoteCurrency"),
        "settlementCurrency": instrument.get("settlementCurrency"),
        "priceIncrement": instrument.get("priceIncrement"),
        "sizeIncrement": instrument.get("sizeIncrement"),
        "multiplier": instrument.get("multiplier"),
        "lotSize": instrument.get("lotSize"),
        "marginInit": instrument.get("marginInit"),
        "marginMaint": instrument.get("marginMaint"),
        "makerFee": instrument.get("makerFee"),
        "takerFee": instrument.get("takerFee"),
    }


def _market_summary(objects: list[dict[str, Any]]) -> dict[str, Any]:
    quote = _first_object(objects, "QuoteTick") or {}
    trade = _first_object(objects, "TradeTick") or {}
    book = _first_object(objects, "OrderBookDeltas") or {}
    return {
        "hasQuoteTick": bool(quote),
        "hasTradeTick": bool(trade),
        "hasOrderBookDeltas": bool(book),
        "topOfBook": {
            "instrumentId": quote.get("instrumentId"),
            "bidPrice": quote.get("bidPrice"),
            "askPrice": quote.get("askPrice"),
            "bidSize": quote.get("bidSize"),
            "askSize": quote.get("askSize"),
            "tsEvent": quote.get("tsEvent"),
            "tsInit": quote.get("tsInit"),
        }
        if quote
        else None,
        "lastTrade": {
            "instrumentId": trade.get("instrumentId"),
            "price": trade.get("price"),
            "size": trade.get("size"),
            "tradeId": trade.get("tradeId"),
            "aggressorSide": trade.get("aggressorSide"),
            "tsEvent": trade.get("tsEvent"),
            "tsInit": trade.get("tsInit"),
        }
        if trade
        else None,
        "bookDeltas": {
            "instrumentId": book.get("instrumentId"),
            "deltaCount": book.get("deltaCount"),
            "sequence": book.get("sequence"),
            "tsEvent": book.get("tsEvent"),
        }
        if book
        else None,
    }


def _account_summary(
    *,
    account: dict[str, Any],
    positions: list[dict[str, Any]],
    active_orders: list[dict[str, Any]],
    global_positions: list[dict[str, Any]],
    global_active_orders: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    currency: str,
) -> dict[str, Any]:
    balances = account.get("balances") if isinstance(account.get("balances"), list) else []
    balance = _find_balance(balances, currency)
    return {
        "accountId": account.get("accountId"),
        "accountType": account.get("accountType"),
        "baseCurrency": account.get("baseCurrency"),
        "balance": balance,
        "openPositionCount": len(positions),
        "activeOrderCount": len(active_orders),
        "globalOpenPositionCount": len(global_positions),
        "globalActiveOrderCount": len(global_active_orders),
        "recentFillCount": len(fills),
    }


def _find_balance(balances: list[Any], currency: str) -> dict[str, Any] | None:
    for balance in balances:
        if not isinstance(balance, dict):
            continue
        if str(balance.get("currency") or "").upper() != currency:
            continue
        return {
            "currency": currency,
            "total": _money_amount(balance.get("total")),
            "locked": _money_amount(balance.get("locked")),
            "free": _money_amount(balance.get("free")),
        }
    return None


def _latest_execution_object(objects: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not objects:
        return None
    return objects[0]


def _balance_adjustments(execution_wire: dict[str, Any]) -> list[dict[str, Any]]:
    sandbox_wire = execution_wire.get("sandboxWire") if isinstance(execution_wire.get("sandboxWire"), dict) else {}
    adjustments = sandbox_wire.get("balanceAdjustments")
    return [item for item in adjustments if isinstance(item, dict)] if isinstance(adjustments, list) else []


def _strategy_preview(strategy_signal: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(strategy_signal, dict):
        return {
            "available": False,
            "side": None,
            "confidence": None,
            "preflightAllowed": None,
            "candidateOrder": None,
        }

    signal_outer = strategy_signal.get("signal") if isinstance(strategy_signal.get("signal"), dict) else {}
    signal = signal_outer.get("signal") if isinstance(signal_outer.get("signal"), dict) else {}
    preflight = strategy_signal.get("preflight") if isinstance(strategy_signal.get("preflight"), dict) else None
    return {
        "available": True,
        "side": signal.get("side"),
        "confidence": signal.get("confidence"),
        "reasons": signal.get("reasons", []),
        "preflightAllowed": preflight.get("preflightAllowed") if preflight else None,
        "preflightReasons": preflight.get("reasons", []) if preflight else [],
        "candidateOrder": signal_outer.get("candidateOrder"),
        "metrics": signal_outer.get("metrics") if isinstance(signal_outer.get("metrics"), dict) else {},
    }


def _money_amount(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    amount = text.split()[0]
    try:
        return format(Decimal(amount).normalize(), "f")
    except (InvalidOperation, ValueError):
        return amount


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
