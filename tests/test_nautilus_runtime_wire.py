from mexc_futures_engine.nautilus_adapter.runtime_wire import build_runtime_wire_report
from mexc_futures_engine.nautilus_adapter.runtime_wire import summarize_runtime_wire_report


def test_runtime_wire_report_ready_for_sandboxed_readonly_runtime():
    report = build_runtime_wire_report(
        instrument_report=_instrument_report(),
        sandbox_wire=_sandbox_wire(),
        symbols=["BTC_USDT"],
        live_trading_enabled=False,
    )

    assert report["ok"] is True
    assert report["readyForSandboxedNautilusRuntimeReadOnly"] is True
    assert report["readyForLiveRuntime"] is False
    assert report["sandboxWire"]["objectCount"] == 1
    assert report["sandboxWire"]["objects"][0]["class"] == "CryptoPerpetual"
    assert report["nextPhase"] == "map-market-data-events-into-sandboxed-nautilus-runtime-read-only"


def test_runtime_wire_report_blocks_wire_errors():
    sandbox_wire = _sandbox_wire()
    sandbox_wire["ok"] = False
    sandbox_wire["errors"] = ["precision mismatch"]

    report = build_runtime_wire_report(
        instrument_report=_instrument_report(),
        sandbox_wire=sandbox_wire,
        symbols=["BTC_USDT"],
        live_trading_enabled=False,
    )

    assert report["ok"] is False
    assert "precision mismatch" in report["blockers"]


def test_runtime_wire_report_blocks_live_flag():
    report = build_runtime_wire_report(
        instrument_report=_instrument_report(),
        sandbox_wire=_sandbox_wire(),
        symbols=["BTC_USDT"],
        live_trading_enabled=True,
    )

    assert report["ok"] is False
    assert "live trading flag is enabled; sandbox runtime wire requires read-only mode" in report["blockers"]


def test_runtime_wire_summary_omits_inputs():
    report = build_runtime_wire_report(
        instrument_report=_instrument_report(),
        sandbox_wire=_sandbox_wire(),
        symbols=["BTC_USDT"],
        live_trading_enabled=False,
        include_raw=True,
    )

    summary = summarize_runtime_wire_report(report)

    assert "inputs" in report
    assert "inputs" not in summary
    assert summary["ok"] is True


def _instrument_report():
    return {
        "loaded": 1,
        "selectedContracts": 1,
        "mappingErrors": [],
        "symbolsPreview": ["BTC_USDT"],
    }


def _sandbox_wire():
    return {
        "ok": True,
        "inputCount": 1,
        "objectCount": 1,
        "objects": [
            {
                "instrumentId": "BTC_USDT-PERP.MEXC",
                "rawSymbol": "BTC_USDT",
                "class": "CryptoPerpetual",
            }
        ],
        "errors": [],
        "sandboxProbe": {
            "importOk": True,
            "packageVersion": "1.227.0a20260513",
        },
    }
