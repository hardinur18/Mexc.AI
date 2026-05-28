from mexc_futures_engine.adapter_readiness import build_nautilus_adapter_readiness_report
from mexc_futures_engine.adapter_readiness import summarize_nautilus_adapter_readiness_report


def test_nautilus_adapter_readiness_passes_for_complete_readonly_inputs():
    report = build_nautilus_adapter_readiness_report(
        instrument_report=_instrument_report(),
        market_data_payloads=_market_data_payloads(),
        reconciliation_report=_reconciliation_report(),
        upstream_reference=_upstream_reference(),
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=False,
    )

    assert report["ok"] is True
    assert report["readyForReadOnlyRuntime"] is True
    assert report["readyForLiveRuntime"] is False
    assert report["components"]["instrumentProvider"]["loaded"] == 1
    assert report["components"]["marketDataBridge"]["channels"]["depth"]["expectedEventCounts"] == {
        "OrderBookDeltas": 1,
        "QuoteTick": 1,
    }
    assert report["components"]["liveMutation"]["status"] == "locked"
    assert report["nextPhase"] == "prepare-sandboxed-nautilus-runtime-install-read-only"


def test_nautilus_adapter_readiness_blocks_missing_market_data_channel():
    market_data = _market_data_payloads()
    market_data["depth"] = {"eventCount": 0, "eventCounts": {}, "rawMessageCount": 1}

    report = build_nautilus_adapter_readiness_report(
        instrument_report=_instrument_report(),
        market_data_payloads=market_data,
        reconciliation_report=_reconciliation_report(),
        upstream_reference=_upstream_reference(),
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=False,
    )

    assert report["ok"] is False
    assert report["readyForReadOnlyRuntime"] is False
    assert "depth bridge produced no OrderBookDeltas events" in report["blockers"]
    assert "depth WebSocket produced raw messages but no parsed market data events" in report["warnings"]


def test_nautilus_adapter_summary_omits_raw_inputs():
    report = build_nautilus_adapter_readiness_report(
        instrument_report=_instrument_report(),
        market_data_payloads=_market_data_payloads(),
        reconciliation_report=_reconciliation_report(),
        upstream_reference=_upstream_reference(),
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=False,
        include_raw=True,
    )

    summary = summarize_nautilus_adapter_readiness_report(report)

    assert "inputs" in report
    assert "inputs" not in summary
    assert summary["ok"] is True


def test_live_enabled_is_not_live_runtime_ready():
    report = build_nautilus_adapter_readiness_report(
        instrument_report=_instrument_report(),
        market_data_payloads=_market_data_payloads(),
        reconciliation_report=_reconciliation_report(),
        upstream_reference=_upstream_reference(),
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=True,
    )

    assert report["readyForReadOnlyRuntime"] is False
    assert report["ok"] is False
    assert report["readyForLiveRuntime"] is False
    assert report["components"]["liveMutation"]["status"] == "manual-review-required"
    assert "live trading flag is enabled while submit/cancel is not adapter-ready" in report["blockers"]


def _instrument_report():
    return {
        "loaded": 1,
        "selectedContracts": 1,
        "mappingErrors": [],
        "symbolsPreview": ["BTC_USDT"],
    }


def _market_data_payloads():
    return {
        "ticker": {"eventCount": 1, "eventCounts": {"QuoteTick": 1}, "rawMessageCount": 2},
        "deal": {"eventCount": 1, "eventCounts": {"TradeTick": 1}, "rawMessageCount": 2},
        "depth": {
            "eventCount": 2,
            "eventCounts": {"QuoteTick": 1, "OrderBookDeltas": 1},
            "rawMessageCount": 2,
        },
    }


def _reconciliation_report():
    return {
        "ok": True,
        "readiness": {
            "restWsReconcilable": True,
            "liveSafeState": True,
        },
        "executionReports": {
            "reportCount": 1,
            "reportCounts": {"AccountState": 1},
        },
        "privateWs": {
            "loginAck": True,
            "filterAck": True,
            "failedControlAcks": [],
            "eventCount": 2,
            "idleOnly": True,
        },
        "consistency": {"status": "idle-private-ws-with-rest-snapshot"},
        "blockers": [],
        "warnings": [],
    }


def _upstream_reference():
    return {
        "nautilusTrader": {
            "path": "upstream/nautilus_trader",
            "exists": True,
            "revision": "abc1234",
        }
    }
