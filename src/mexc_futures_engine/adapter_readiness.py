from __future__ import annotations

import time
from typing import Any


EXPECTED_MARKET_EVENTS = {
    "deal": ("TradeTick",),
    "depth": ("OrderBookDeltas", "QuoteTick"),
}


def build_nautilus_adapter_readiness_report(
    *,
    instrument_report: dict[str, Any],
    market_data_payloads: dict[str, dict[str, Any]],
    reconciliation_report: dict[str, Any],
    upstream_reference: dict[str, Any],
    symbol: str,
    currency: str,
    live_trading_enabled: bool,
    include_raw: bool = False,
) -> dict[str, Any]:
    components = {
        "upstreamReference": _upstream_component(upstream_reference),
        "instrumentProvider": _instrument_component(instrument_report),
        "marketDataBridge": _market_data_component(market_data_payloads),
        "executionReports": _execution_component(reconciliation_report.get("executionReports", {})),
        "privateStream": _private_stream_component(reconciliation_report.get("privateWs", {})),
        "reconciliation": _reconciliation_component(reconciliation_report),
        "liveMutation": _live_mutation_component(live_trading_enabled),
    }

    blockers: list[str] = []
    warnings: list[str] = []
    for name, component in components.items():
        if not component["ok"]:
            blockers.extend(component["reasons"])
        warnings.extend(component.get("warnings", []))

    read_only_components = (
        "upstreamReference",
        "instrumentProvider",
        "marketDataBridge",
        "executionReports",
        "privateStream",
        "reconciliation",
        "liveMutation",
    )
    ready_for_readonly_runtime = all(bool(components[name]["ok"]) for name in read_only_components)

    report: dict[str, Any] = {
        "timestamp": int(time.time() * 1000),
        "targetEngine": "NautilusTrader",
        "integrationMode": "local-read-only-adapter-bridge",
        "symbol": symbol.upper(),
        "currency": currency.upper(),
        "ok": ready_for_readonly_runtime and not blockers,
        "readyForReadOnlyRuntime": ready_for_readonly_runtime,
        "readyForLiveRuntime": False,
        "components": components,
        "blockers": blockers,
        "warnings": warnings,
        "nextPhase": _next_phase(ready_for_readonly_runtime, blockers),
    }
    if include_raw:
        report["inputs"] = {
            "instrumentReport": instrument_report,
            "marketDataPayloads": market_data_payloads,
            "reconciliationReport": reconciliation_report,
            "upstreamReference": upstream_reference,
        }
    return report


def summarize_nautilus_adapter_readiness_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": report["timestamp"],
        "targetEngine": report["targetEngine"],
        "integrationMode": report["integrationMode"],
        "symbol": report["symbol"],
        "currency": report["currency"],
        "ok": report["ok"],
        "readyForReadOnlyRuntime": report["readyForReadOnlyRuntime"],
        "readyForLiveRuntime": report["readyForLiveRuntime"],
        "components": report["components"],
        "blockers": report["blockers"],
        "warnings": report["warnings"],
        "nextPhase": report["nextPhase"],
    }


def _upstream_component(upstream_reference: dict[str, Any]) -> dict[str, Any]:
    nautilus = upstream_reference.get("nautilusTrader") if isinstance(upstream_reference, dict) else {}
    exists = bool(isinstance(nautilus, dict) and nautilus.get("exists"))
    return {
        "ok": exists,
        "status": "available" if exists else "missing",
        "path": nautilus.get("path") if isinstance(nautilus, dict) else None,
        "revision": nautilus.get("revision") if isinstance(nautilus, dict) else None,
        "reasons": [] if exists else ["NautilusTrader upstream reference is missing"],
        "warnings": [],
    }


def _instrument_component(instrument_report: dict[str, Any]) -> dict[str, Any]:
    loaded = _as_int(instrument_report.get("loaded")) or 0
    mapping_errors = instrument_report.get("mappingErrors")
    mapping_error_count = len(mapping_errors) if isinstance(mapping_errors, list) else 0
    ok = loaded > 0 and mapping_error_count == 0
    reasons = []
    if loaded <= 0:
        reasons.append("instrument provider loaded zero specs")
    if mapping_error_count:
        reasons.append(f"instrument provider has {mapping_error_count} mapping errors")
    return {
        "ok": ok,
        "status": "ready" if ok else "blocked",
        "loaded": loaded,
        "selectedContracts": instrument_report.get("selectedContracts"),
        "mappingErrorCount": mapping_error_count,
        "symbolsPreview": instrument_report.get("symbolsPreview", []),
        "reasons": reasons,
        "warnings": [],
    }


def _market_data_component(market_data_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    channels: dict[str, dict[str, Any]] = {}
    reasons: list[str] = []
    warnings: list[str] = []

    for channel, expected_events in EXPECTED_MARKET_EVENTS.items():
        payload = market_data_payloads.get(channel) if isinstance(market_data_payloads, dict) else None
        payload = payload if isinstance(payload, dict) else {}
        event_counts = payload.get("eventCounts") if isinstance(payload.get("eventCounts"), dict) else {}
        event_count = _as_int(payload.get("eventCount")) or 0
        expected_counts = {event: _as_int(event_counts.get(event)) or 0 for event in expected_events}
        channel_ok = all(count > 0 for count in expected_counts.values())
        channels[channel] = {
            "ok": channel_ok,
            "expectedEvents": list(expected_events),
            "eventCount": event_count,
            "expectedEventCounts": expected_counts,
            "expectedEventCount": sum(expected_counts.values()),
            "rawMessageCount": payload.get("rawMessageCount", 0),
        }
        if not channel_ok:
            for expected_event, expected_count in expected_counts.items():
                if expected_count <= 0:
                    reasons.append(f"{channel} bridge produced no {expected_event} events")
        if event_count == 0 and payload.get("rawMessageCount", 0):
            warnings.append(f"{channel} WebSocket produced raw messages but no parsed market data events")

    ok = all(channel["ok"] for channel in channels.values())
    return {
        "ok": ok,
        "status": "ready" if ok else "blocked",
        "channels": channels,
        "reasons": reasons,
        "warnings": warnings,
    }


def _execution_component(execution_summary: dict[str, Any]) -> dict[str, Any]:
    counts = execution_summary.get("reportCounts") if isinstance(execution_summary.get("reportCounts"), dict) else {}
    account_state_count = _as_int(counts.get("AccountState")) or 0
    report_count = _as_int(execution_summary.get("reportCount")) or 0
    ok = account_state_count == 1 and report_count >= 1
    reasons = []
    if account_state_count != 1:
        reasons.append("execution reports must include exactly one AccountState report")
    if report_count < 1:
        reasons.append("execution report bundle is empty")
    return {
        "ok": ok,
        "status": "ready" if ok else "blocked",
        "reportCount": report_count,
        "reportCounts": counts,
        "reasons": reasons,
        "warnings": [],
    }


def _private_stream_component(private_ws_summary: dict[str, Any]) -> dict[str, Any]:
    login_ack = bool(private_ws_summary.get("loginAck"))
    filter_ack = bool(private_ws_summary.get("filterAck"))
    failed_acks = private_ws_summary.get("failedControlAcks")
    failed_ack_count = len(failed_acks) if isinstance(failed_acks, list) else 0
    ok = login_ack and filter_ack and failed_ack_count == 0
    reasons = []
    if not login_ack:
        reasons.append("private stream login acknowledgement missing")
    if not filter_ack:
        reasons.append("private stream personal.filter acknowledgement missing")
    if failed_ack_count:
        reasons.append(f"private stream has {failed_ack_count} failed acknowledgements")
    warnings = []
    if private_ws_summary.get("idleOnly"):
        warnings.append("private stream ACK-only window; normal for idle account")
    return {
        "ok": ok,
        "status": "ready" if ok else "blocked",
        "loginAck": login_ack,
        "filterAck": filter_ack,
        "eventCount": private_ws_summary.get("eventCount", 0),
        "idleOnly": bool(private_ws_summary.get("idleOnly")),
        "reasons": reasons,
        "warnings": warnings,
    }


def _reconciliation_component(reconciliation_report: dict[str, Any]) -> dict[str, Any]:
    readiness = reconciliation_report.get("readiness") if isinstance(reconciliation_report.get("readiness"), dict) else {}
    ok = bool(reconciliation_report.get("ok")) and bool(readiness.get("restWsReconcilable"))
    reasons = list(reconciliation_report.get("blockers") or []) if not ok else []
    warnings = list(reconciliation_report.get("warnings") or [])
    return {
        "ok": ok,
        "status": "ready" if ok else "blocked",
        "restWsReconcilable": bool(readiness.get("restWsReconcilable")),
        "liveSafeState": bool(readiness.get("liveSafeState")),
        "consistencyStatus": (reconciliation_report.get("consistency") or {}).get("status"),
        "reasons": reasons,
        "warnings": warnings,
    }


def _live_mutation_component(live_trading_enabled: bool) -> dict[str, Any]:
    locked = not live_trading_enabled
    return {
        "ok": locked,
        "status": "locked" if locked else "manual-review-required",
        "submitCancelImplemented": False,
        "cliExposesLiveOrder": False,
        "reasons": [] if locked else ["live trading flag is enabled while submit/cancel is not adapter-ready"],
        "warnings": ["live submit/cancel remains intentionally unavailable"],
    }


def _next_phase(ready_for_readonly_runtime: bool, blockers: list[str]) -> str:
    if not ready_for_readonly_runtime:
        return "fix-read-only-adapter-blockers"
    if blockers:
        return "review-blockers"
    return "prepare-sandboxed-nautilus-runtime-install-read-only"


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
