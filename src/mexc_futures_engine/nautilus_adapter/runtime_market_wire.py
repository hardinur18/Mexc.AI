from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time
from typing import Any

from .runtime_harness import probe_sandbox_nautilus_runtime


REQUIRED_RUNTIME_MARKET_OBJECTS = {"QuoteTick", "TradeTick", "OrderBookDeltas"}


def wire_market_data_payloads_to_sandbox(
    market_data_payloads: dict[str, dict[str, Any]],
    root: Path,
    *,
    venv_dir: str = ".venv-nautilus",
) -> dict[str, Any]:
    sandbox_probe = probe_sandbox_nautilus_runtime(root, venv_dir=venv_dir)
    events = _extract_events(market_data_payloads)
    if not sandbox_probe.get("importOk"):
        return {
            "timestamp": int(time.time() * 1000),
            "ok": False,
            "sandboxProbe": sandbox_probe,
            "inputEventCount": len(events),
            "objectCount": 0,
            "objectCounts": {},
            "objects": [],
            "skipped": [],
            "errors": ["sandbox Nautilus runtime import is not available"],
        }

    python_path = Path(str(sandbox_probe["python"]))
    process = subprocess.run(
        [str(python_path), "-c", _SANDBOX_MARKET_DATA_WIRE_SCRIPT],
        input=json.dumps({"events": events}, separators=(",", ":"), ensure_ascii=False),
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
    object_counts = _count_by_key(objects, "class")
    skipped = parsed.get("skipped") if isinstance(parsed.get("skipped"), list) else []
    return {
        "timestamp": int(time.time() * 1000),
        "ok": process.returncode == 0 and not errors,
        "sandboxProbe": sandbox_probe,
        "inputEventCount": len(events),
        "objectCount": len(objects),
        "objectCounts": object_counts,
        "objects": objects,
        "skipped": skipped,
        "errors": errors,
    }


def build_market_runtime_wire_report(
    *,
    market_data_payloads: dict[str, dict[str, Any]],
    sandbox_wire: dict[str, Any],
    symbol: str,
    live_trading_enabled: bool,
    include_raw: bool = False,
) -> dict[str, Any]:
    event_counts = _market_event_counts(market_data_payloads)
    object_counts = sandbox_wire.get("objectCounts") if isinstance(sandbox_wire.get("objectCounts"), dict) else {}
    blockers: list[str] = []
    warnings: list[str] = []

    if live_trading_enabled:
        blockers.append("live trading flag is enabled; market runtime wire requires read-only mode")
    if not sandbox_wire.get("ok"):
        blockers.extend(str(error) for error in sandbox_wire.get("errors") or ["sandbox market data wire failed"])

    for required_type in sorted(REQUIRED_RUNTIME_MARKET_OBJECTS):
        if int(object_counts.get(required_type) or 0) <= 0:
            blockers.append(f"sandbox wire produced no {required_type} objects")

    skipped = sandbox_wire.get("skipped") if isinstance(sandbox_wire.get("skipped"), list) else []
    quote_skips = [
        item
        for item in skipped
        if isinstance(item, dict)
        and item.get("eventType") == "QuoteTick"
        and item.get("reason") == "missing bidSize/askSize"
    ]
    if quote_skips and int(object_counts.get("QuoteTick") or 0) <= 0:
        warnings.append("MEXC ticker lacks bid/ask sizes, so Nautilus QuoteTick is not constructed from ticker")
    elif quote_skips:
        warnings.append("ticker-derived QuoteTick skipped; using depth-derived QuoteTick with real sizes")

    sandbox_probe = sandbox_wire.get("sandboxProbe") if isinstance(sandbox_wire.get("sandboxProbe"), dict) else {}
    if sandbox_probe.get("importOk"):
        warnings.append("using sandbox Nautilus wheel runtime; source checkout remains a reference")
    warnings.append("live submit/cancel remains intentionally unavailable")

    ok = not blockers
    report: dict[str, Any] = {
        "timestamp": int(time.time() * 1000),
        "targetEngine": "NautilusTrader",
        "wireMode": "sandboxed-market-data-read-only",
        "symbol": symbol.upper(),
        "ok": ok,
        "readyForSandboxedNautilusMarketDataReadOnly": ok,
        "readyForLiveRuntime": False,
        "marketData": {
            "channels": {
                channel: {
                    "rawMessageCount": payload.get("rawMessageCount", 0),
                    "eventCount": payload.get("eventCount", 0),
                    "eventCounts": payload.get("eventCounts", {}),
                }
                for channel, payload in sorted(market_data_payloads.items())
            },
            "eventCounts": event_counts,
        },
        "sandboxWire": {
            "ok": sandbox_wire.get("ok"),
            "inputEventCount": sandbox_wire.get("inputEventCount", 0),
            "objectCount": sandbox_wire.get("objectCount", 0),
            "objectCounts": object_counts,
            "objects": sandbox_wire.get("objects", []),
            "skipped": skipped,
            "errors": sandbox_wire.get("errors", []),
        },
        "sandboxProbe": sandbox_probe,
        "blockers": blockers,
        "warnings": warnings,
        "nextPhase": "map-execution-reports-into-sandboxed-nautilus-runtime-read-only",
    }
    if include_raw:
        report["inputs"] = {
            "marketDataPayloads": market_data_payloads,
            "sandboxWire": sandbox_wire,
        }
    return report


def summarize_market_runtime_wire_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": report["timestamp"],
        "targetEngine": report["targetEngine"],
        "wireMode": report["wireMode"],
        "symbol": report["symbol"],
        "ok": report["ok"],
        "readyForSandboxedNautilusMarketDataReadOnly": report[
            "readyForSandboxedNautilusMarketDataReadOnly"
        ],
        "readyForLiveRuntime": report["readyForLiveRuntime"],
        "marketData": report["marketData"],
        "sandboxWire": report["sandboxWire"],
        "sandboxProbe": report["sandboxProbe"],
        "blockers": report["blockers"],
        "warnings": report["warnings"],
        "nextPhase": report["nextPhase"],
    }


def _extract_events(market_data_payloads: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for channel, payload in sorted(market_data_payloads.items()):
        payload_events = payload.get("events") if isinstance(payload.get("events"), list) else []
        for event in payload_events:
            if isinstance(event, dict):
                events.append({"sourceChannel": channel, **event})
    return events


def _market_event_counts(market_data_payloads: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for payload in market_data_payloads.values():
        event_counts = payload.get("eventCounts") if isinstance(payload.get("eventCounts"), dict) else {}
        for event_type, count in event_counts.items():
            counts[str(event_type)] = counts.get(str(event_type), 0) + int(count or 0)
    return counts


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
        return {"objects": [], "skipped": [], "errors": ["sandbox market wire produced no output"]}
    try:
        parsed = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        return {"objects": [], "skipped": [], "errors": [f"sandbox market wire produced invalid JSON: {exc}"]}
    if not isinstance(parsed, dict):
        return {"objects": [], "skipped": [], "errors": ["sandbox market wire output was not an object"]}
    return parsed


_SANDBOX_MARKET_DATA_WIRE_SCRIPT = r"""
from __future__ import annotations

import json
import sys
import time

from nautilus_trader.model.data import BookOrder
from nautilus_trader.model.data import OrderBookDelta
from nautilus_trader.model.data import OrderBookDeltas
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.enums import BookAction
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import TradeId
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    objects = []
    skipped = []
    errors = []
    for index, event in enumerate(events):
        try:
            event_type = event.get("eventType")
            if event_type == "QuoteTick":
                item = quote_tick_or_skip(event)
                if item.get("skipped"):
                    skipped.append(item["skipped"])
                else:
                    objects.append(item["object"])
            elif event_type == "TradeTick":
                objects.append(trade_tick_object(event))
            elif event_type == "OrderBookDeltas":
                objects.append(order_book_deltas_object(event))
            else:
                skipped.append({"index": index, "eventType": event_type, "reason": "unsupported event type"})
        except Exception as exc:
            errors.append({"index": index, "eventType": event.get("eventType"), "type": type(exc).__name__, "error": str(exc)})
    print(json.dumps({"objects": objects, "skipped": skipped, "errors": errors}, separators=(",", ":")))
    return 0 if not errors else 1


def quote_tick_or_skip(event):
    payload = event.get("payload") or {}
    if payload.get("bidSize") is None or payload.get("askSize") is None:
        return {
            "skipped": {
                "eventType": "QuoteTick",
                "instrumentId": event.get("instrumentId"),
                "reason": "missing bidSize/askSize",
            }
        }
    tick = QuoteTick(
        instrument_id=InstrumentId.from_str(event["instrumentId"]),
        bid_price=Price.from_str(payload["bidPrice"]),
        ask_price=Price.from_str(payload["askPrice"]),
        bid_size=Quantity.from_str(payload["bidSize"]),
        ask_size=Quantity.from_str(payload["askSize"]),
        ts_event=int(event["tsEventNs"]),
        ts_init=int(event["tsInitNs"]),
    )
    return {
        "object": {
            "class": "QuoteTick",
            "instrumentId": str(tick.instrument_id),
            "bidPrice": str(tick.bid_price),
            "askPrice": str(tick.ask_price),
            "bidSize": str(tick.bid_size),
            "askSize": str(tick.ask_size),
            "tsEvent": tick.ts_event,
            "tsInit": tick.ts_init,
        }
    }


def trade_tick_object(event):
    payload = event.get("payload") or {}
    trade_id = str(payload.get("tradeId") or f"mexc-{event.get('tsEventNs')}")
    tick = TradeTick(
        instrument_id=InstrumentId.from_str(event["instrumentId"]),
        price=Price.from_str(payload["price"]),
        size=Quantity.from_str(payload["size"]),
        aggressor_side=aggressor_side(payload.get("aggressorSide")),
        trade_id=TradeId(trade_id),
        ts_event=int(event["tsEventNs"]),
        ts_init=int(event["tsInitNs"]),
    )
    return {
        "class": "TradeTick",
        "instrumentId": str(tick.instrument_id),
        "price": str(tick.price),
        "size": str(tick.size),
        "aggressorSide": str(tick.aggressor_side),
        "tradeId": str(tick.trade_id),
        "tsEvent": tick.ts_event,
        "tsInit": tick.ts_init,
    }


def order_book_deltas_object(event):
    instrument_id = InstrumentId.from_str(event["instrumentId"])
    payload = event.get("payload") or {}
    sequence = int(event.get("sequence") or payload.get("version") or payload.get("endSequence") or 0)
    deltas = []
    for row in payload.get("deltas") or []:
        order = BookOrder(
            side=order_side(row.get("side")),
            price=Price.from_str(row["price"]),
            size=Quantity.from_str(row["size"]),
            order_id=0,
        )
        deltas.append(
            OrderBookDelta(
                instrument_id=instrument_id,
                action=book_action(row.get("action")),
                order=order,
                flags=0,
                sequence=sequence,
                ts_event=int(event["tsEventNs"]),
                ts_init=int(event["tsInitNs"]),
            )
        )
    batch = OrderBookDeltas(instrument_id, deltas)
    return {
        "class": "OrderBookDeltas",
        "instrumentId": str(batch.instrument_id),
        "deltaCount": len(batch.deltas),
        "sequence": batch.sequence,
        "tsEvent": batch.ts_event,
        "tsInit": batch.ts_init,
    }


def aggressor_side(value):
    value = str(value or "NO_AGGRESSOR").upper()
    return getattr(AggressorSide, value)


def order_side(value):
    value = str(value or "").upper()
    if value == "BID":
        return OrderSide.BUY
    if value == "ASK":
        return OrderSide.SELL
    return OrderSide.NO_ORDER_SIDE


def book_action(value):
    value = str(value or "").upper()
    return getattr(BookAction, value)


raise SystemExit(main())
"""
