from __future__ import annotations

import inspect
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from .data import MexcFuturesDataClientBoundary
from .execution import MexcFuturesExecutionClientBoundary
from .provider import MexcFuturesInstrumentProviderBoundary


REQUIRED_TEMPLATE_FILES = {
    "templateProvider": "nautilus_trader/adapters/_template/providers.py",
    "templateData": "nautilus_trader/adapters/_template/data.py",
    "templateExecution": "nautilus_trader/adapters/_template/execution.py",
    "binanceFuturesProvider": "nautilus_trader/adapters/binance/futures/providers.py",
    "binanceFuturesData": "nautilus_trader/adapters/binance/futures/data.py",
    "binanceFuturesExecution": "nautilus_trader/adapters/binance/futures/execution.py",
    "binanceFactories": "nautilus_trader/adapters/binance/factories.py",
}

REQUIRED_BOUNDARY_METHODS = {
    "instrumentProvider": ["load_all", "load_symbols"],
    "dataClient": ["stream_public"],
    "executionClient": [
        "generate_execution_reports",
        "stream_private",
        "reconcile_startup",
        "submit_order",
        "cancel_order",
        "cancel_all_orders",
    ],
}


def build_runtime_harness_report(
    *,
    adapter_manifest: dict[str, Any],
    adapter_check_report: dict[str, Any],
    upstream_probe: dict[str, Any],
    sandbox_probe: dict[str, Any] | None = None,
    template_files: dict[str, Any],
    boundary_methods: dict[str, Any],
    symbol: str,
    currency: str,
    live_trading_enabled: bool,
    include_raw: bool = False,
) -> dict[str, Any]:
    sandbox_probe = sandbox_probe or {}
    nautilus_import_ok = bool(upstream_probe.get("importOk")) or bool(sandbox_probe.get("importOk"))
    blockers: list[str] = []
    warnings: list[str] = []

    if not adapter_manifest:
        blockers.append("adapter manifest is missing")
    if adapter_manifest and adapter_manifest.get("adapter") != "mexc_futures":
        blockers.append("adapter manifest is not for mexc_futures")
    if not bool(adapter_check_report.get("readyForReadOnlyRuntime")):
        blockers.append("adapter check is not ready for read-only runtime")
    if live_trading_enabled:
        blockers.append("live trading flag is enabled; runtime harness requires read-only mode")

    missing_template_files = [
        name for name, item in template_files.items() if isinstance(item, dict) and not item.get("exists")
    ]
    for name in missing_template_files:
        blockers.append(f"Nautilus adapter reference file missing: {name}")

    missing_methods = _missing_boundary_methods(boundary_methods)
    for class_name, methods in missing_methods.items():
        blockers.append(f"{class_name} missing methods: {', '.join(methods)}")

    if not upstream_probe.get("sourcePresent"):
        blockers.append("NautilusTrader upstream source is missing")
    elif not upstream_probe.get("importOk") and not sandbox_probe.get("importOk"):
        warnings.append(
            "NautilusTrader source is present but runtime import is not available until the upstream package is built or installed"
        )
    elif not upstream_probe.get("importOk") and sandbox_probe.get("importOk"):
        warnings.append("NautilusTrader runtime import is available from sandbox wheel; source checkout is not built")
    if adapter_check_report.get("readyForLiveRuntime") is False:
        warnings.append("live runtime remains intentionally unavailable")

    ready_for_runtime_harness = not blockers
    report: dict[str, Any] = {
        "timestamp": int(time.time() * 1000),
        "targetEngine": "NautilusTrader",
        "harnessMode": "read-only-local-boundary",
        "symbol": symbol.upper(),
        "currency": currency.upper(),
        "ok": ready_for_runtime_harness,
        "readyForRuntimeHarness": ready_for_runtime_harness,
        "readyForNautilusRuntimeImport": nautilus_import_ok,
        "readyForLiveRuntime": False,
        "adapterManifest": _manifest_summary(adapter_manifest),
        "adapterCheck": _adapter_check_summary(adapter_check_report),
        "upstreamProbe": upstream_probe,
        "sandboxProbe": sandbox_probe,
        "templateFiles": template_files,
        "boundaryMethods": boundary_methods,
        "blockers": blockers,
        "warnings": warnings,
        "nextPhase": _next_phase(
            ready_for_runtime_harness=ready_for_runtime_harness,
            nautilus_import_ok=nautilus_import_ok,
        ),
    }
    if include_raw:
        report["inputs"] = {
            "adapterManifest": adapter_manifest,
            "adapterCheckReport": adapter_check_report,
            "sandboxProbe": sandbox_probe,
        }
    return report


def summarize_runtime_harness_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": report["timestamp"],
        "targetEngine": report["targetEngine"],
        "harnessMode": report["harnessMode"],
        "symbol": report["symbol"],
        "currency": report["currency"],
        "ok": report["ok"],
        "readyForRuntimeHarness": report["readyForRuntimeHarness"],
        "readyForNautilusRuntimeImport": report["readyForNautilusRuntimeImport"],
        "readyForLiveRuntime": report["readyForLiveRuntime"],
        "adapterManifest": report["adapterManifest"],
        "adapterCheck": report["adapterCheck"],
        "upstreamProbe": report["upstreamProbe"],
        "sandboxProbe": report["sandboxProbe"],
        "templateFiles": report["templateFiles"],
        "boundaryMethods": report["boundaryMethods"],
        "blockers": report["blockers"],
        "warnings": report["warnings"],
        "nextPhase": report["nextPhase"],
    }


def collect_template_files(root: Path) -> dict[str, Any]:
    upstream_root = root / "upstream" / "nautilus_trader"
    files: dict[str, Any] = {}
    for name, relative_path in REQUIRED_TEMPLATE_FILES.items():
        path = upstream_root / relative_path
        files[name] = {
            "path": str(path),
            "exists": path.exists(),
            "sizeBytes": path.stat().st_size if path.exists() else None,
        }
    return files


def inspect_boundary_methods() -> dict[str, Any]:
    classes = {
        "instrumentProvider": MexcFuturesInstrumentProviderBoundary,
        "dataClient": MexcFuturesDataClientBoundary,
        "executionClient": MexcFuturesExecutionClientBoundary,
    }
    payload: dict[str, Any] = {}
    for name, cls in classes.items():
        required = REQUIRED_BOUNDARY_METHODS[name]
        methods: dict[str, Any] = {}
        for method_name in required:
            attr = getattr(cls, method_name, None)
            methods[method_name] = {
                "exists": callable(attr),
                "signature": str(inspect.signature(attr)) if callable(attr) else None,
            }
        payload[name] = {
            "class": cls.__name__,
            "module": cls.__module__,
            "methods": methods,
            "ok": all(method["exists"] for method in methods.values()),
        }
    return payload


def probe_nautilus_runtime(root: Path) -> dict[str, Any]:
    upstream_root = root / "upstream" / "nautilus_trader"
    source_present = (upstream_root / "nautilus_trader").exists()
    if not source_present:
        return {
            "sourcePresent": False,
            "importOk": False,
            "path": str(upstream_root),
            "errorType": "missing-source",
            "error": "NautilusTrader upstream source not found",
        }

    env = os.environ.copy()
    pythonpath = str(upstream_root)
    existing_pythonpath = env.get("PYTHONPATH")
    if existing_pythonpath:
        pythonpath = f"{pythonpath}{os.pathsep}{existing_pythonpath}"
    env["PYTHONPATH"] = pythonpath

    script = (
        "import json\n"
        "try:\n"
        "    import nautilus_trader\n"
        "    print(json.dumps({'importOk': True, 'version': getattr(nautilus_trader, '__version__', None)}))\n"
        "except Exception as exc:\n"
        "    print(json.dumps({'importOk': False, 'errorType': type(exc).__name__, 'error': str(exc)}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    parsed = _parse_probe_output(result.stdout)
    return {
        "sourcePresent": True,
        "importOk": bool(parsed.get("importOk")),
        "path": str(upstream_root),
        "version": parsed.get("version"),
        "errorType": parsed.get("errorType"),
        "error": parsed.get("error"),
        "returnCode": result.returncode,
    }


def probe_sandbox_nautilus_runtime(root: Path, *, venv_dir: str = ".venv-nautilus") -> dict[str, Any]:
    venv_path = root / venv_dir
    python_path = venv_path / "bin" / "python"
    if not python_path.exists():
        return {
            "venvPresent": False,
            "importOk": False,
            "path": str(venv_path),
            "python": str(python_path),
            "errorType": "missing-venv",
            "error": "sandbox venv not found",
        }

    script = (
        "import json\n"
        "try:\n"
        "    import importlib.metadata\n"
        "    import nautilus_trader\n"
        "    from nautilus_trader.model.identifiers import Venue\n"
        "    from nautilus_trader.model.instruments import CryptoPerpetual\n"
        "    print(json.dumps({\n"
        "        'importOk': True,\n"
        "        'version': getattr(nautilus_trader, '__version__', None),\n"
        "        'packageVersion': importlib.metadata.version('nautilus_trader'),\n"
        "        'modelImportOk': CryptoPerpetual.__name__ == 'CryptoPerpetual',\n"
        "        'venueProbe': str(Venue('MEXC')),\n"
        "    }))\n"
        "except Exception as exc:\n"
        "    print(json.dumps({'importOk': False, 'errorType': type(exc).__name__, 'error': str(exc)}))\n"
    )
    result = subprocess.run(
        [str(python_path), "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    parsed = _parse_probe_output(result.stdout)
    return {
        "venvPresent": True,
        "importOk": bool(parsed.get("importOk")),
        "path": str(venv_path),
        "python": str(python_path),
        "version": parsed.get("version"),
        "packageVersion": parsed.get("packageVersion"),
        "modelImportOk": parsed.get("modelImportOk"),
        "venueProbe": parsed.get("venueProbe"),
        "errorType": parsed.get("errorType"),
        "error": parsed.get("error"),
        "returnCode": result.returncode,
    }


def _manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "adapter": manifest.get("adapter"),
        "integrationMode": manifest.get("integrationMode"),
        "nextPhase": manifest.get("nextPhase"),
        "liveMutationStatus": ((manifest.get("capabilities") or {}).get("liveMutation") or {}).get("status"),
        "requiresNautilusRuntimeForImport": ((manifest.get("runtimePolicy") or {})).get(
            "requiresNautilusRuntimeForImport"
        ),
    }


def _adapter_check_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": report.get("ok"),
        "readyForReadOnlyRuntime": report.get("readyForReadOnlyRuntime"),
        "readyForLiveRuntime": report.get("readyForLiveRuntime"),
        "nextPhase": report.get("nextPhase"),
        "blockerCount": len(report.get("blockers") or []),
        "warningCount": len(report.get("warnings") or []),
    }


def _missing_boundary_methods(boundary_methods: dict[str, Any]) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for name, methods in REQUIRED_BOUNDARY_METHODS.items():
        class_payload = boundary_methods.get(name) if isinstance(boundary_methods.get(name), dict) else {}
        method_payload = class_payload.get("methods") if isinstance(class_payload.get("methods"), dict) else {}
        missing_methods = [
            method_name
            for method_name in methods
            if not isinstance(method_payload.get(method_name), dict) or not method_payload[method_name].get("exists")
        ]
        if missing_methods:
            missing[name] = missing_methods
    return missing


def _parse_probe_output(stdout: str) -> dict[str, Any]:
    import json

    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return {"importOk": False, "errorType": "empty-output", "error": "probe produced no output"}
    try:
        parsed = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        return {"importOk": False, "errorType": type(exc).__name__, "error": str(exc)}
    return parsed if isinstance(parsed, dict) else {"importOk": False, "error": "probe output was not an object"}


def _next_phase(*, ready_for_runtime_harness: bool, nautilus_import_ok: bool) -> str:
    if not ready_for_runtime_harness:
        return "fix-runtime-harness-blockers"
    if not nautilus_import_ok:
        return "prepare-sandboxed-nautilus-runtime-install-read-only"
    return "wire-boundary-into-sandboxed-nautilus-runtime-read-only"
