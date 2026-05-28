from __future__ import annotations

import time
from typing import Any

from .execution_reports import summarize_execution_report_bundle


PRIVATE_STATE_EVENT_TYPES = {"AccountUpdate", "PositionUpdate", "OrderUpdate", "FillUpdate"}


def build_reconciliation_report(
    *,
    rest_snapshot: dict[str, Any],
    execution_bundle: dict[str, Any],
    private_ws_payload: dict[str, Any],
    symbol: str,
    currency: str,
    include_raw: bool = False,
) -> dict[str, Any]:
    rest_summary = _summarize_rest_snapshot(rest_snapshot, execution_bundle)
    private_summary = _summarize_private_ws(private_ws_payload)
    execution_summary = summarize_execution_report_bundle(execution_bundle)

    blockers: list[str] = []
    warnings: list[str] = []

    for field, label in (
        ("allAssetsSuccess", "all assets REST snapshot failed"),
        ("singleAssetSuccess", "single asset REST snapshot failed"),
        ("positionsSuccess", "open positions REST snapshot failed"),
        ("openOrdersSuccess", "open orders REST snapshot failed"),
        ("recentOrdersSuccess", "recent orders REST snapshot failed"),
    ):
        if not rest_summary[field]:
            blockers.append(label)

    if private_summary["eventCount"] == 0:
        blockers.append("private WebSocket produced no events")
    if not private_summary["loginAck"]:
        blockers.append("private WebSocket login acknowledgement missing")
    if not private_summary["filterAck"]:
        blockers.append("private WebSocket personal.filter acknowledgement missing")
    for method in private_summary["failedControlAcks"]:
        blockers.append(f"private WebSocket control acknowledgement failed: {method}")

    live_safe_state = rest_summary["globalOpenPositionCount"] == 0 and rest_summary["globalOpenOrderCount"] == 0
    if private_summary["idleOnly"]:
        warnings.append("private WebSocket returned acknowledgements only; account appears idle in this window")
    if not private_summary["hasStateUpdates"]:
        warnings.append("no private account/order/position/fill deltas observed during the WebSocket window")
    if not live_safe_state:
        warnings.append(
            "REST snapshot has open positions or open orders; do not enable live mutations until state is reviewed"
        )
    if execution_summary["reportCounts"].get("AccountState", 0) != 1:
        warnings.append("execution report bundle does not contain exactly one AccountState report")

    rest_private_ok = all(
        bool(rest_summary[field])
        for field in (
            "allAssetsSuccess",
            "singleAssetSuccess",
            "positionsSuccess",
            "openOrdersSuccess",
            "recentOrdersSuccess",
        )
    )
    private_ws_ok = private_summary["loginAck"] and private_summary["filterAck"] and not private_summary[
        "failedControlAcks"
    ]
    rest_ws_reconcilable = rest_private_ok and private_ws_ok
    readiness = {
        "restPrivateOk": rest_private_ok,
        "privateWsOk": private_ws_ok,
        "loginAck": private_summary["loginAck"],
        "filterAck": private_summary["filterAck"],
        "restWsReconcilable": rest_ws_reconcilable,
        "liveSafeState": live_safe_state,
    }

    consistency = _build_consistency(
        blockers=blockers,
        rest_private_ok=rest_private_ok,
        private_ws_ok=private_ws_ok,
        private_summary=private_summary,
        live_safe_state=live_safe_state,
    )

    report: dict[str, Any] = {
        "timestamp": int(time.time() * 1000),
        "mode": "REST_PRIVATE_WS_READ_ONLY",
        "symbol": symbol.upper(),
        "currency": currency.upper(),
        "ok": not blockers,
        "readiness": readiness,
        "rest": rest_summary,
        "executionReports": execution_summary,
        "privateWs": private_summary,
        "consistency": consistency,
        "blockers": blockers,
        "warnings": warnings,
    }
    if include_raw:
        report["inputs"] = {
            "restSnapshot": rest_snapshot,
            "executionBundle": execution_bundle,
            "privateWsPayload": private_ws_payload,
        }
    return report


def summarize_reconciliation_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": report["timestamp"],
        "mode": report["mode"],
        "symbol": report["symbol"],
        "currency": report["currency"],
        "ok": report["ok"],
        "readiness": report["readiness"],
        "rest": report["rest"],
        "executionReports": report["executionReports"],
        "privateWs": report["privateWs"],
        "consistency": report["consistency"],
        "blockers": report["blockers"],
        "warnings": report["warnings"],
    }


def _summarize_rest_snapshot(
    rest_snapshot: dict[str, Any],
    execution_bundle: dict[str, Any],
) -> dict[str, Any]:
    assets = rest_snapshot.get("assets") if isinstance(rest_snapshot.get("assets"), dict) else {}
    single_asset = rest_snapshot.get("singleAsset") if isinstance(rest_snapshot.get("singleAsset"), dict) else {}
    positions = rest_snapshot.get("positions") if isinstance(rest_snapshot.get("positions"), dict) else {}
    open_orders = rest_snapshot.get("openOrders") if isinstance(rest_snapshot.get("openOrders"), dict) else {}
    recent_orders = rest_snapshot.get("recentOrders") if isinstance(rest_snapshot.get("recentOrders"), dict) else {}

    asset_rows = _rows(assets)
    position_rows = _rows(positions)
    global_position_rows = _rows(
        rest_snapshot.get("globalPositions") if isinstance(rest_snapshot.get("globalPositions"), dict) else positions
    )
    open_order_rows = _rows(open_orders)
    recent_order_rows = _rows(recent_orders)
    target_symbol = str(rest_snapshot.get("symbol") or "").upper()
    target_open_order_rows = [
        row for row in open_order_rows if not target_symbol or str(row.get("symbol") or "").upper() == target_symbol
    ]

    return {
        "timestamp": rest_snapshot.get("timestamp"),
        "allAssetsSuccess": _response_success(assets),
        "singleAssetSuccess": _response_success(single_asset),
        "positionsSuccess": _response_success(positions),
        "openOrdersSuccess": _response_success(open_orders),
        "recentOrdersSuccess": _response_success(recent_orders),
        "assetCount": len(asset_rows),
        "openPositionCount": len(position_rows),
        "openOrderCount": len(open_order_rows),
        "targetOpenPositionCount": len(position_rows),
        "targetOpenOrderCount": len(target_open_order_rows),
        "globalOpenPositionCount": len(global_position_rows),
        "globalOpenOrderCount": len(open_order_rows),
        "recentOrderCount": len(recent_order_rows),
        "executionReportCount": execution_bundle.get("reportCount", 0),
        "executionReportCounts": execution_bundle.get("reportCounts", {}),
    }


def _summarize_private_ws(private_ws_payload: dict[str, Any]) -> dict[str, Any]:
    events = private_ws_payload.get("events") if isinstance(private_ws_payload.get("events"), list) else []
    control_acks: list[dict[str, Any]] = []
    update_counts: dict[str, int] = {}
    event_counts: dict[str, int] = {}

    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("eventType") or "PrivateUpdate")
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
        if event_type in PRIVATE_STATE_EVENT_TYPES:
            update_counts[event_type] = update_counts.get(event_type, 0) + 1
        if event_type == "ControlAck":
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            method = str(payload.get("method") or _method_from_channel(str(event.get("channel") or "")))
            control_acks.append(
                {
                    "method": method,
                    "ok": bool(payload.get("ok")),
                    "channel": event.get("channel"),
                }
            )

    successful_methods = {ack["method"] for ack in control_acks if ack["ok"]}
    failed_methods = [ack["method"] for ack in control_acks if not ack["ok"]]
    has_state_updates = any(update_counts.values())
    event_count = len([event for event in events if isinstance(event, dict)])

    return {
        "timestamp": private_ws_payload.get("timestamp"),
        "requestedMessages": private_ws_payload.get("requestedMessages"),
        "rawMessageCount": private_ws_payload.get("rawMessageCount", 0),
        "eventCount": event_count,
        "eventCounts": event_counts,
        "controlAcks": control_acks,
        "failedControlAcks": failed_methods,
        "loginAck": "login" in successful_methods,
        "filterAck": "personal.filter" in successful_methods,
        "hasStateUpdates": has_state_updates,
        "stateUpdateCounts": update_counts,
        "idleOnly": event_count > 0 and event_counts.get("ControlAck", 0) == event_count,
    }


def _build_consistency(
    *,
    blockers: list[str],
    rest_private_ok: bool,
    private_ws_ok: bool,
    private_summary: dict[str, Any],
    live_safe_state: bool,
) -> dict[str, Any]:
    if blockers:
        status = "blocked"
    elif private_summary["hasStateUpdates"]:
        status = "state-updates-observed"
    elif private_summary["idleOnly"]:
        status = "idle-private-ws-with-rest-snapshot"
    elif live_safe_state:
        status = "rest-snapshot-only"
    else:
        status = "rest-has-open-risk-state"

    reasons: list[str] = []
    if rest_private_ok:
        reasons.append("private REST account, position, order, and history endpoints returned successful snapshots")
    if private_ws_ok:
        reasons.append("private WebSocket login and personal.filter acknowledgements succeeded")
    if private_summary["idleOnly"]:
        reasons.append("private WebSocket had no state deltas during the read window")
    if private_summary["hasStateUpdates"]:
        reasons.append("private WebSocket produced account/order/position/fill deltas")
    if live_safe_state:
        reasons.append("REST snapshot has no open positions and no open orders")

    return {
        "status": status,
        "reasons": reasons,
    }


def _rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    data = response.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict) and isinstance(data.get("resultList"), list):
        return [row for row in data["resultList"] if isinstance(row, dict)]
    return []


def _response_success(response: dict[str, Any]) -> bool:
    if not isinstance(response, dict):
        return False
    if "success" in response:
        return bool(response["success"])
    if response.get("code") in (0, 200):
        return True
    return "data" in response


def _method_from_channel(channel: str) -> str:
    return channel.removeprefix("rs.")
