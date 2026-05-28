from mexc_futures_engine.nautilus_adapter.runtime_harness import build_runtime_harness_report
from mexc_futures_engine.nautilus_adapter.runtime_harness import inspect_boundary_methods
from mexc_futures_engine.nautilus_adapter.runtime_harness import summarize_runtime_harness_report


def test_runtime_harness_ready_when_boundary_and_references_are_complete():
    report = build_runtime_harness_report(
        adapter_manifest=_manifest(),
        adapter_check_report=_adapter_check(),
        upstream_probe=_upstream_probe(import_ok=False),
        template_files=_template_files(),
        boundary_methods=inspect_boundary_methods(),
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=False,
    )

    assert report["ok"] is True
    assert report["readyForRuntimeHarness"] is True
    assert report["readyForNautilusRuntimeImport"] is False
    assert report["readyForLiveRuntime"] is False
    assert report["blockers"] == []
    assert report["nextPhase"] == "prepare-sandboxed-nautilus-runtime-install-read-only"
    assert any("runtime import is not available" in warning for warning in report["warnings"])


def test_runtime_harness_accepts_sandbox_runtime_import():
    report = build_runtime_harness_report(
        adapter_manifest=_manifest(),
        adapter_check_report=_adapter_check(),
        upstream_probe=_upstream_probe(import_ok=False),
        sandbox_probe={
            "venvPresent": True,
            "importOk": True,
            "version": "1.227.0",
            "packageVersion": "1.227.0a20260513",
            "modelImportOk": True,
        },
        template_files=_template_files(),
        boundary_methods=inspect_boundary_methods(),
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=False,
    )

    assert report["ok"] is True
    assert report["readyForNautilusRuntimeImport"] is True
    assert report["nextPhase"] == "wire-boundary-into-sandboxed-nautilus-runtime-read-only"
    assert any("sandbox wheel" in warning for warning in report["warnings"])


def test_runtime_harness_blocks_missing_boundary_method():
    methods = inspect_boundary_methods()
    methods["executionClient"]["methods"]["reconcile_startup"]["exists"] = False

    report = build_runtime_harness_report(
        adapter_manifest=_manifest(),
        adapter_check_report=_adapter_check(),
        upstream_probe=_upstream_probe(import_ok=True),
        template_files=_template_files(),
        boundary_methods=methods,
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=False,
    )

    assert report["ok"] is False
    assert "executionClient missing methods: reconcile_startup" in report["blockers"]
    assert report["nextPhase"] == "fix-runtime-harness-blockers"


def test_runtime_harness_blocks_live_flag():
    report = build_runtime_harness_report(
        adapter_manifest=_manifest(),
        adapter_check_report=_adapter_check(),
        upstream_probe=_upstream_probe(import_ok=True),
        template_files=_template_files(),
        boundary_methods=inspect_boundary_methods(),
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=True,
    )

    assert report["ok"] is False
    assert "live trading flag is enabled; runtime harness requires read-only mode" in report["blockers"]


def test_runtime_harness_summary_omits_raw_inputs():
    report = build_runtime_harness_report(
        adapter_manifest=_manifest(),
        adapter_check_report=_adapter_check(),
        upstream_probe=_upstream_probe(import_ok=True),
        template_files=_template_files(),
        boundary_methods=inspect_boundary_methods(),
        symbol="BTC_USDT",
        currency="USDT",
        live_trading_enabled=False,
        include_raw=True,
    )

    summary = summarize_runtime_harness_report(report)

    assert "inputs" in report
    assert "inputs" not in summary
    assert summary["ok"] is True


def _manifest():
    return {
        "adapter": "mexc_futures",
        "integrationMode": "packaged-read-only-boundary",
        "nextPhase": "wire-boundary-into-nautilus-runtime-harness-read-only",
        "capabilities": {"liveMutation": {"status": "locked"}},
        "runtimePolicy": {"requiresNautilusRuntimeForImport": False},
    }


def _adapter_check():
    return {
        "ok": True,
        "readyForReadOnlyRuntime": True,
        "readyForLiveRuntime": False,
        "nextPhase": "wire-boundary-into-nautilus-runtime-harness-read-only",
        "blockers": [],
        "warnings": [],
    }


def _upstream_probe(*, import_ok):
    return {
        "sourcePresent": True,
        "importOk": import_ok,
        "path": "upstream/nautilus_trader",
        "version": None,
        "errorType": None if import_ok else "ModuleNotFoundError",
        "error": None if import_ok else "No module named 'nautilus_trader.core.data'",
    }


def _template_files():
    return {
        "templateProvider": {"exists": True},
        "templateData": {"exists": True},
        "templateExecution": {"exists": True},
        "binanceFuturesProvider": {"exists": True},
        "binanceFuturesData": {"exists": True},
        "binanceFuturesExecution": {"exists": True},
        "binanceFactories": {"exists": True},
    }
