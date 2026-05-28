from mexc_futures_engine.execution_reports import build_execution_report_bundle
from mexc_futures_engine.reconciliation import build_reconciliation_report
from mexc_futures_engine.reconciliation import summarize_reconciliation_report


def test_ack_only_private_ws_reconciles_with_clean_rest_snapshot():
    report = build_reconciliation_report(
        rest_snapshot=_rest_snapshot(open_orders=[]),
        execution_bundle=_execution_bundle(open_orders=[]),
        private_ws_payload=_private_ws_payload(["login", "personal.filter"]),
        symbol="BTC_USDT",
        currency="USDT",
    )

    assert report["ok"] is True
    assert report["readiness"]["restWsReconcilable"] is True
    assert report["readiness"]["liveSafeState"] is True
    assert report["consistency"]["status"] == "idle-private-ws-with-rest-snapshot"
    assert report["privateWs"]["idleOnly"] is True
    assert "inputs" not in report


def test_missing_private_filter_ack_blocks_reconciliation():
    report = build_reconciliation_report(
        rest_snapshot=_rest_snapshot(open_orders=[]),
        execution_bundle=_execution_bundle(open_orders=[]),
        private_ws_payload=_private_ws_payload(["login"]),
        symbol="BTC_USDT",
        currency="USDT",
    )

    assert report["ok"] is False
    assert report["readiness"]["privateWsOk"] is False
    assert "private WebSocket personal.filter acknowledgement missing" in report["blockers"]


def test_open_order_keeps_report_ok_but_not_live_safe():
    open_orders = [{"symbol": "BTC_USDT", "orderId": "order-1", "side": 1, "state": 1, "vol": 1}]
    report = build_reconciliation_report(
        rest_snapshot=_rest_snapshot(open_orders=open_orders),
        execution_bundle=_execution_bundle(open_orders=open_orders),
        private_ws_payload=_private_ws_payload(["login", "personal.filter"]),
        symbol="BTC_USDT",
        currency="USDT",
    )

    assert report["ok"] is True
    assert report["readiness"]["restWsReconcilable"] is True
    assert report["readiness"]["liveSafeState"] is False
    assert report["rest"]["openOrderCount"] == 1
    assert report["rest"]["globalOpenOrderCount"] == 1
    assert any("open positions or open orders" in warning for warning in report["warnings"])


def test_global_position_keeps_live_state_unsafe_even_when_target_symbol_clean():
    global_positions = [{"symbol": "ETH_USDT", "positionId": "position-1", "holdVol": 1}]
    report = build_reconciliation_report(
        rest_snapshot=_rest_snapshot(open_orders=[], global_positions=global_positions),
        execution_bundle=_execution_bundle(open_orders=[]),
        private_ws_payload=_private_ws_payload(["login", "personal.filter"]),
        symbol="BTC_USDT",
        currency="USDT",
    )

    assert report["ok"] is True
    assert report["readiness"]["liveSafeState"] is False
    assert report["rest"]["targetOpenPositionCount"] == 0
    assert report["rest"]["globalOpenPositionCount"] == 1


def test_reconciliation_summary_omits_raw_inputs():
    report = build_reconciliation_report(
        rest_snapshot=_rest_snapshot(open_orders=[]),
        execution_bundle=_execution_bundle(open_orders=[]),
        private_ws_payload=_private_ws_payload(["login", "personal.filter"]),
        symbol="BTC_USDT",
        currency="USDT",
        include_raw=True,
    )

    summary = summarize_reconciliation_report(report)

    assert "inputs" in report
    assert "inputs" not in summary
    assert summary["executionReports"]["reportCount"] == 1


def _rest_snapshot(open_orders, global_positions=None):
    return {
        "timestamp": 1778733932000,
        "symbol": "BTC_USDT",
        "currency": "USDT",
        "assets": {"success": True, "data": [{"currency": "USDT", "equity": 6}]},
        "singleAsset": {
            "success": True,
            "data": {
                "currency": "USDT",
                "equity": 6,
                "availableBalance": 6,
                "frozenBalance": 0,
            },
        },
        "globalPositions": {"success": True, "data": global_positions or []},
        "positions": {"success": True, "data": []},
        "openOrders": {"success": True, "data": open_orders},
        "recentOrders": {"success": True, "data": {"resultList": []}},
    }


def _execution_bundle(open_orders):
    return build_execution_report_bundle(
        asset_response=_rest_snapshot(open_orders)["singleAsset"],
        positions_response={"success": True, "data": []},
        open_orders_response={"success": True, "data": open_orders},
        history_orders_response={"success": True, "data": {"resultList": []}},
        order_deals_response={"success": True, "data": []},
        symbol="BTC_USDT",
        currency="USDT",
        include_raw=False,
    )


def _private_ws_payload(methods):
    events = [
        {
            "eventType": "ControlAck",
            "channel": f"rs.{method}",
            "venue": "MEXC",
            "payload": {"method": method, "ok": True, "source": "MEXC private WebSocket"},
        }
        for method in methods
    ]
    event_counts = {"ControlAck": len(events)}
    return {
        "timestamp": 1778733933000,
        "requestedMessages": 5,
        "rawMessageCount": len(events),
        "eventCount": len(events),
        "eventCounts": event_counts,
        "events": events,
    }
