from mexc_futures_engine.nautilus_adapter.runtime_execution_wire import (
    build_execution_runtime_wire_report,
)
from mexc_futures_engine.nautilus_adapter.runtime_execution_wire import (
    summarize_execution_runtime_wire_report,
)


def test_execution_runtime_wire_ready_with_account_order_fill_objects():
    report = build_execution_runtime_wire_report(
        execution_bundle=_execution_bundle(),
        sandbox_wire=_sandbox_wire(),
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=False,
    )

    assert report["ok"] is True
    assert report["readyForSandboxedNautilusExecutionReadOnly"] is True
    assert report["sandboxWire"]["objectCounts"] == {
        "AccountState": 1,
        "FillReport": 1,
        "OrderStatusReport": 1,
    }
    assert report["nextPhase"] == "connect-read-only-nautilus-state-cache-to-strategy-handoff"


def test_execution_runtime_wire_blocks_missing_account_state():
    sandbox_wire = _sandbox_wire()
    sandbox_wire["objectCounts"] = {"OrderStatusReport": 1, "FillReport": 1}
    sandbox_wire["objectCount"] = 2

    report = build_execution_runtime_wire_report(
        execution_bundle=_execution_bundle(),
        sandbox_wire=sandbox_wire,
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=False,
    )

    assert report["ok"] is False
    assert "sandbox wire produced no AccountState objects" in report["blockers"]


def test_execution_runtime_wire_blocks_live_flag():
    report = build_execution_runtime_wire_report(
        execution_bundle=_execution_bundle(),
        sandbox_wire=_sandbox_wire(),
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=True,
    )

    assert report["ok"] is False
    assert "live trading flag is enabled; execution runtime wire requires read-only mode" in report["blockers"]


def test_execution_runtime_wire_summary_omits_inputs():
    report = build_execution_runtime_wire_report(
        execution_bundle=_execution_bundle(),
        sandbox_wire=_sandbox_wire(),
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=False,
        include_raw=True,
    )

    summary = summarize_execution_runtime_wire_report(report)

    assert "inputs" in report
    assert "inputs" not in summary
    assert summary["ok"] is True


def _execution_bundle():
    return {
        "source": "MEXC private REST read-only",
        "reportCount": 3,
        "reportCounts": {
            "AccountState": 1,
            "OrderStatusReport": 1,
            "FillReport": 1,
        },
    }


def _sandbox_wire():
    return {
        "ok": True,
        "inputReportCount": 3,
        "objectCount": 3,
        "objectCounts": {
            "AccountState": 1,
            "OrderStatusReport": 1,
            "FillReport": 1,
        },
        "objects": [
            {"class": "AccountState", "accountId": "MEXC-FUTURES"},
            {"class": "OrderStatusReport", "instrumentId": "BTC_USDT-PERP.MEXC"},
            {"class": "FillReport", "instrumentId": "BTC_USDT-PERP.MEXC"},
        ],
        "skipped": [],
        "errors": [],
        "sandboxProbe": {
            "importOk": True,
            "packageVersion": "1.227.0a20260513",
        },
    }
