from mexc_futures_engine.nautilus_adapter.runtime_market_wire import build_market_runtime_wire_report
from mexc_futures_engine.nautilus_adapter.runtime_market_wire import summarize_market_runtime_wire_report


def test_market_runtime_wire_ready_with_trade_and_book_objects():
    report = build_market_runtime_wire_report(
        market_data_payloads=_market_payloads(),
        sandbox_wire=_sandbox_wire(),
        symbol="BTC_USDT",
        live_trading_enabled=False,
    )

    assert report["ok"] is True
    assert report["readyForSandboxedNautilusMarketDataReadOnly"] is True
    assert report["sandboxWire"]["objectCounts"] == {"QuoteTick": 1, "OrderBookDeltas": 1, "TradeTick": 1}
    assert any("depth-derived QuoteTick" in warning for warning in report["warnings"])
    assert report["nextPhase"] == "map-execution-reports-into-sandboxed-nautilus-runtime-read-only"


def test_market_runtime_wire_blocks_missing_trade_object():
    sandbox_wire = _sandbox_wire()
    sandbox_wire["objectCounts"] = {"OrderBookDeltas": 1}

    report = build_market_runtime_wire_report(
        market_data_payloads=_market_payloads(),
        sandbox_wire=sandbox_wire,
        symbol="BTC_USDT",
        live_trading_enabled=False,
    )

    assert report["ok"] is False
    assert "sandbox wire produced no TradeTick objects" in report["blockers"]
    assert "sandbox wire produced no QuoteTick objects" in report["blockers"]


def test_market_runtime_wire_blocks_live_flag():
    report = build_market_runtime_wire_report(
        market_data_payloads=_market_payloads(),
        sandbox_wire=_sandbox_wire(),
        symbol="BTC_USDT",
        live_trading_enabled=True,
    )

    assert report["ok"] is False
    assert "live trading flag is enabled; market runtime wire requires read-only mode" in report["blockers"]


def test_market_runtime_wire_summary_omits_inputs():
    report = build_market_runtime_wire_report(
        market_data_payloads=_market_payloads(),
        sandbox_wire=_sandbox_wire(),
        symbol="BTC_USDT",
        live_trading_enabled=False,
        include_raw=True,
    )

    summary = summarize_market_runtime_wire_report(report)

    assert "inputs" in report
    assert "inputs" not in summary
    assert summary["ok"] is True


def _market_payloads():
    return {
        "ticker": {
            "rawMessageCount": 2,
            "eventCount": 1,
            "eventCounts": {"QuoteTick": 1},
            "events": [],
        },
        "deal": {
            "rawMessageCount": 2,
            "eventCount": 1,
            "eventCounts": {"TradeTick": 1},
            "events": [],
        },
        "depth": {
            "rawMessageCount": 2,
            "eventCount": 1,
            "eventCounts": {"OrderBookDeltas": 1},
            "events": [],
        },
    }


def _sandbox_wire():
    return {
        "ok": True,
        "inputEventCount": 3,
        "objectCount": 3,
        "objectCounts": {"QuoteTick": 1, "TradeTick": 1, "OrderBookDeltas": 1},
        "objects": [
            {"class": "QuoteTick", "instrumentId": "BTC_USDT-PERP.MEXC"},
            {"class": "TradeTick", "instrumentId": "BTC_USDT-PERP.MEXC"},
            {"class": "OrderBookDeltas", "instrumentId": "BTC_USDT-PERP.MEXC"},
        ],
        "skipped": [
            {
                "eventType": "QuoteTick",
                "instrumentId": "BTC_USDT-PERP.MEXC",
                "reason": "missing bidSize/askSize",
            }
        ],
        "errors": [],
        "sandboxProbe": {
            "importOk": True,
            "packageVersion": "1.227.0a20260513",
        },
    }
