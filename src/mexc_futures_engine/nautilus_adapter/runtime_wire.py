from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time
from typing import Any

from .runtime_harness import probe_sandbox_nautilus_runtime


def wire_instrument_specs_to_sandbox(
    specs: list[dict[str, Any]],
    root: Path,
    *,
    venv_dir: str = ".venv-nautilus",
) -> dict[str, Any]:
    sandbox_probe = probe_sandbox_nautilus_runtime(root, venv_dir=venv_dir)
    if not sandbox_probe.get("importOk"):
        return {
            "timestamp": int(time.time() * 1000),
            "ok": False,
            "sandboxProbe": sandbox_probe,
            "inputCount": len(specs),
            "objectCount": 0,
            "objects": [],
            "errors": ["sandbox Nautilus runtime import is not available"],
        }

    python_path = Path(str(sandbox_probe["python"]))
    process = subprocess.run(
        [str(python_path), "-c", _SANDBOX_INSTRUMENT_WIRE_SCRIPT],
        input=json.dumps({"specs": specs}, separators=(",", ":"), ensure_ascii=False),
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
    return {
        "timestamp": int(time.time() * 1000),
        "ok": process.returncode == 0 and not errors and len(objects) == len(specs),
        "sandboxProbe": sandbox_probe,
        "inputCount": len(specs),
        "objectCount": len(objects),
        "objects": objects,
        "errors": errors,
    }


def build_runtime_wire_report(
    *,
    instrument_report: dict[str, Any],
    sandbox_wire: dict[str, Any],
    symbols: list[str],
    live_trading_enabled: bool,
    include_raw: bool = False,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    loaded = _as_int(instrument_report.get("loaded")) or 0
    if loaded <= 0:
        blockers.append("instrument provider loaded zero specs")
    if sandbox_wire.get("inputCount") != loaded:
        blockers.append("sandbox wire input count does not match provider loaded count")
    if not sandbox_wire.get("ok"):
        blockers.extend(str(error) for error in sandbox_wire.get("errors") or ["sandbox instrument wire failed"])
    if live_trading_enabled:
        blockers.append("live trading flag is enabled; sandbox runtime wire requires read-only mode")

    sandbox_probe = sandbox_wire.get("sandboxProbe") if isinstance(sandbox_wire.get("sandboxProbe"), dict) else {}
    if sandbox_probe.get("importOk"):
        warnings.append("using sandbox Nautilus wheel runtime; source checkout remains a reference")
    warnings.append("live submit/cancel remains intentionally unavailable")

    ok = not blockers
    report: dict[str, Any] = {
        "timestamp": int(time.time() * 1000),
        "targetEngine": "NautilusTrader",
        "wireMode": "sandboxed-runtime-read-only",
        "symbols": symbols,
        "ok": ok,
        "readyForSandboxedNautilusRuntimeReadOnly": ok,
        "readyForLiveRuntime": False,
        "instrumentProvider": {
            "loaded": loaded,
            "selectedContracts": instrument_report.get("selectedContracts"),
            "mappingErrors": instrument_report.get("mappingErrors", []),
            "symbolsPreview": instrument_report.get("symbolsPreview", []),
        },
        "sandboxWire": {
            "ok": sandbox_wire.get("ok"),
            "inputCount": sandbox_wire.get("inputCount", 0),
            "objectCount": sandbox_wire.get("objectCount", 0),
            "objects": sandbox_wire.get("objects", []),
            "errors": sandbox_wire.get("errors", []),
        },
        "sandboxProbe": sandbox_probe,
        "blockers": blockers,
        "warnings": warnings,
        "nextPhase": "map-market-data-events-into-sandboxed-nautilus-runtime-read-only",
    }
    if include_raw:
        report["inputs"] = {
            "instrumentReport": instrument_report,
            "sandboxWire": sandbox_wire,
        }
    return report


def summarize_runtime_wire_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": report["timestamp"],
        "targetEngine": report["targetEngine"],
        "wireMode": report["wireMode"],
        "symbols": report["symbols"],
        "ok": report["ok"],
        "readyForSandboxedNautilusRuntimeReadOnly": report["readyForSandboxedNautilusRuntimeReadOnly"],
        "readyForLiveRuntime": report["readyForLiveRuntime"],
        "instrumentProvider": report["instrumentProvider"],
        "sandboxWire": report["sandboxWire"],
        "sandboxProbe": report["sandboxProbe"],
        "blockers": report["blockers"],
        "warnings": report["warnings"],
        "nextPhase": report["nextPhase"],
    }


def _parse_json_output(stdout: str) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return {"objects": [], "errors": ["sandbox wire produced no output"]}
    try:
        parsed = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        return {"objects": [], "errors": [f"sandbox wire produced invalid JSON: {exc}"]}
    return parsed if isinstance(parsed, dict) else {"objects": [], "errors": ["sandbox wire output was not an object"]}


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_SANDBOX_INSTRUMENT_WIRE_SCRIPT = r"""
from __future__ import annotations

from decimal import Decimal
import json
import sys
import time

from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.instruments import CryptoPerpetual
from nautilus_trader.model.objects import Currency
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    specs = payload.get("specs") if isinstance(payload.get("specs"), list) else []
    objects = []
    errors = []
    for index, spec in enumerate(specs):
        try:
            instrument = spec_to_crypto_perpetual(spec)
            objects.append(
                {
                    "instrumentId": str(instrument.id),
                    "rawSymbol": str(instrument.raw_symbol),
                    "class": instrument.__class__.__name__,
                    "baseCurrency": str(instrument.base_currency),
                    "quoteCurrency": str(instrument.quote_currency),
                    "settlementCurrency": str(instrument.settlement_currency),
                    "isInverse": bool(instrument.is_inverse),
                    "pricePrecision": instrument.price_precision,
                    "sizePrecision": instrument.size_precision,
                    "priceIncrement": str(instrument.price_increment),
                    "sizeIncrement": str(instrument.size_increment),
                    "multiplier": str(instrument.multiplier),
                    "lotSize": str(instrument.lot_size),
                    "marginInit": str(instrument.margin_init) if instrument.margin_init is not None else None,
                    "marginMaint": str(instrument.margin_maint) if instrument.margin_maint is not None else None,
                    "makerFee": str(instrument.maker_fee) if instrument.maker_fee is not None else None,
                    "takerFee": str(instrument.taker_fee) if instrument.taker_fee is not None else None,
                }
            )
        except Exception as exc:
            errors.append({"index": index, "symbol": spec.get("rawSymbol"), "type": type(exc).__name__, "error": str(exc)})
    print(json.dumps({"objects": objects, "errors": errors}, separators=(",", ":")))
    return 0 if not errors else 1


def spec_to_crypto_perpetual(spec):
    if spec.get("instrumentType") != "CryptoPerpetual":
        raise ValueError(f"unsupported instrumentType: {spec.get('instrumentType')}")
    ts_event = int(spec.get("tsEventNs") or time.time_ns())
    ts_init = time.time_ns()
    return CryptoPerpetual(
        instrument_id=InstrumentId.from_str(spec["instrumentId"]),
        raw_symbol=Symbol(spec["rawSymbol"]),
        base_currency=Currency.from_str(spec["baseCurrency"]),
        quote_currency=Currency.from_str(spec["quoteCurrency"]),
        settlement_currency=Currency.from_str(spec["settlementCurrency"]),
        is_inverse=bool(spec.get("isInverse")),
        price_precision=int(spec["pricePrecision"]),
        size_precision=int(spec["sizePrecision"]),
        price_increment=Price.from_str(spec["priceIncrement"]),
        size_increment=Quantity.from_str(spec["sizeIncrement"]),
        ts_event=ts_event,
        ts_init=ts_init,
        multiplier=Quantity.from_str(spec.get("multiplier") or "1"),
        lot_size=Quantity.from_str(spec.get("lotSize") or spec["sizeIncrement"]),
        max_quantity=quantity_or_none(spec.get("maxQuantity")),
        min_quantity=quantity_or_none(spec.get("minQuantity")),
        margin_init=decimal_or_none(spec.get("marginInit")),
        margin_maint=decimal_or_none(spec.get("marginMaint")),
        maker_fee=decimal_or_none(spec.get("makerFee")),
        taker_fee=decimal_or_none(spec.get("takerFee")),
        info=spec.get("info") or {},
    )


def quantity_or_none(value):
    if value is None:
        return None
    return Quantity.from_str(str(value))


def decimal_or_none(value):
    if value is None:
        return None
    return Decimal(str(value))


raise SystemExit(main())
"""
