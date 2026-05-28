from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import subprocess
import sys
import time

from .adapter_readiness import build_nautilus_adapter_readiness_report
from .adapter_readiness import summarize_nautilus_adapter_readiness_report
from .candles import candle_interval_ms
from .candles import parse_rest_klines
from .client import MexcApiError, MexcFuturesClient
from .execution_reports import build_execution_report_bundle
from .execution_reports import summarize_execution_report_bundle
from .indicators import build_candle_trend_report
from .indicators import build_candle_volatility_report
from .market_data import MarketDataParser
from .market_data import parse_public_ws_message
from .models import OpenType, OrderRequest, OrderType, Side
from .nautilus_mapping import contract_row_to_nautilus_spec
from .nautilus_adapter import build_adapter_manifest
from .nautilus_adapter import build_execution_runtime_wire_report
from .nautilus_adapter import build_market_runtime_wire_report
from .nautilus_adapter import build_nautilus_state_handoff_report
from .nautilus_adapter import build_runtime_harness_report
from .nautilus_adapter import build_runtime_wire_report
from .nautilus_adapter import MexcFuturesDataClientBoundary
from .nautilus_adapter import MexcFuturesExecutionClientBoundary
from .nautilus_adapter import MexcFuturesInstrumentProviderBoundary
from .nautilus_adapter import summarize_execution_runtime_wire_report
from .nautilus_adapter import summarize_market_runtime_wire_report
from .nautilus_adapter import summarize_nautilus_state_handoff_report
from .nautilus_adapter import summarize_runtime_harness_report
from .nautilus_adapter import summarize_runtime_wire_report
from .nautilus_adapter import wire_execution_reports_to_sandbox
from .nautilus_adapter import wire_market_data_payloads_to_sandbox
from .nautilus_adapter import wire_instrument_specs_to_sandbox
from .nautilus_adapter.runtime_harness import collect_template_files
from .nautilus_adapter.runtime_harness import inspect_boundary_methods
from .nautilus_adapter.runtime_harness import probe_nautilus_runtime
from .nautilus_adapter.runtime_harness import probe_sandbox_nautilus_runtime
from .nautilus_provider import MexcNautilusInstrumentProvider
from .nautilus_provider import normalize_symbols
from .pairs import pair_summary, parse_contract_pairs
from .paper import build_paper_audit_report
from .paper import build_paper_collection_snapshot
from .paper import build_paper_decision_report
from .paper import build_paper_edge_report
from .paper import build_paper_ledger_report
from .paper import build_paper_readiness_report
from .paper import DEFAULT_ROLLING_WINDOWS
from .paper import PRICE_SIMULATION_CANDLE_HIGH_LOW
from .paper import PRICE_SIMULATION_SAMPLE_CLOSE
from .paper import apply_paper_side_quality_governor
from .paper import summarize_paper_decision_report
from .performance import build_paper_performance_report
from .profit_hunt import build_profit_hunt_report
from .profit_hunt import DEFAULT_CONFIDENCE_THRESHOLDS
from .private_stream import parse_private_ws_message
from .reconciliation import build_reconciliation_report
from .reconciliation import summarize_reconciliation_report
from .risk import RiskEngine, RiskRejected
from .settings import MexcSettings, RiskSettings
from .store import StateStore
from .strategy import evaluate_strategy_events
from .ws import (
    MexcWebSocketClient,
    MexcWebSocketError,
    deal_subscription,
    depth_subscription,
    ticker_subscription,
)


SIDE_MAP = {
    "open-long": Side.OPEN_LONG,
    "close-short": Side.CLOSE_SHORT,
    "open-short": Side.OPEN_SHORT,
    "close-long": Side.CLOSE_LONG,
}

ORDER_TYPE_MAP = {
    "limit": OrderType.LIMIT,
    "post-only": OrderType.POST_ONLY,
    "ioc": OrderType.IOC,
    "fok": OrderType.FOK,
    "market": OrderType.MARKET,
}

OPEN_TYPE_MAP = {
    "isolated": OpenType.ISOLATED,
    "cross": OpenType.CROSS,
}


def _parse_rolling_windows(value: str) -> tuple[int, ...]:
    windows: list[int] = []
    for raw_part in value.split(","):
        part = raw_part.strip()
        if not part:
            continue
        try:
            window = int(part)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("rolling windows must be comma-separated integers") from exc
        if window <= 0:
            raise argparse.ArgumentTypeError("rolling windows must be positive")
        windows.append(window)
    if not windows:
        raise argparse.ArgumentTypeError("at least one rolling window is required")
    return tuple(sorted(set(windows)))


def _parse_confidence_thresholds(value: str) -> tuple[float, ...]:
    thresholds: list[float] = []
    for raw_part in value.split(","):
        part = raw_part.strip()
        if not part:
            continue
        try:
            threshold = float(part)
        except ValueError as exc:
            raise MexcApiError("confidence-thresholds must be comma-separated numbers") from exc
        if threshold < 0 or threshold > 1:
            raise MexcApiError("confidence-thresholds must be between 0 and 1")
        thresholds.append(threshold)
    if not thresholds:
        raise MexcApiError("at least one confidence threshold is required")
    return tuple(sorted(set(thresholds)))


def _parse_float_sweep(value: str | None, *, label: str) -> tuple[float, ...]:
    if value is None or not value.strip():
        return ()
    numbers: list[float] = []
    for raw_part in value.split(","):
        part = raw_part.strip()
        if not part:
            continue
        try:
            number = float(part)
        except ValueError as exc:
            raise MexcApiError(f"{label} must be comma-separated numbers") from exc
        if number < 0:
            raise MexcApiError(f"{label} values must be non-negative")
        numbers.append(number)
    return tuple(sorted(set(numbers)))


def summarize_paper_readiness_report(report: dict[str, object]) -> dict[str, object]:
    components = report.get("components") if isinstance(report.get("components"), list) else []
    failed_components = [
        {
            "name": component.get("name"),
            "blockers": component.get("blockers", []),
        }
        for component in components
        if isinstance(component, dict) and component.get("passed") is not True
    ]
    performance_summary = (
        report.get("performanceSummary") if isinstance(report.get("performanceSummary"), dict) else {}
    )
    return {
        "timestamp": report.get("timestamp"),
        "mode": report.get("mode"),
        "readinessProfile": report.get("readinessProfile"),
        "symbol": report.get("symbol"),
        "currency": report.get("currency"),
        "localPaperReadinessPercent": report.get("localPaperReadinessPercent"),
        "sampleCount": report.get("sampleCount"),
        "targetSampleCount": report.get("targetSampleCount"),
        "readyForLocalPaperStrategy": report.get("readyForLocalPaperStrategy"),
        "readyForLive": report.get("readyForLive"),
        "liveOrderSubmitted": report.get("liveOrderSubmitted"),
        "collectionProgress": report.get("collectionProgress", {}),
        "failedComponents": failed_components,
        "performanceReady": performance_summary.get("readyForLocalPaperPerformance"),
        "nextActions": report.get("nextActions", []),
        "output": report.get("output"),
    }


def build_client() -> MexcFuturesClient:
    return MexcFuturesClient(
        MexcSettings.from_env(),
        risk_engine=RiskEngine(RiskSettings.from_env()),
    )


def print_json(data: object) -> None:
    print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mexc-engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("ping")

    contract_parser = subparsers.add_parser("contract")
    contract_parser.add_argument("symbol", nargs="?")

    nautilus_parser = subparsers.add_parser("nautilus-instrument")
    nautilus_parser.add_argument("symbol")

    nautilus_all_parser = subparsers.add_parser("nautilus-instruments")
    nautilus_all_parser.add_argument("--symbols", action="append")
    nautilus_all_parser.add_argument("--include-non-tradable", action="store_true")
    nautilus_all_parser.add_argument("--summary-only", action="store_true")
    nautilus_all_parser.add_argument("--output")

    adapter_check_parser = subparsers.add_parser("nautilus-adapter-check")
    adapter_check_parser.add_argument("--symbol", default="BTC_USDT")
    adapter_check_parser.add_argument("--currency", default="USDT")
    adapter_check_parser.add_argument("--market-messages", type=int, default=2)
    adapter_check_parser.add_argument("--private-ws-messages", type=int, default=5)
    adapter_check_parser.add_argument("--history-limit", type=int, default=20)
    adapter_check_parser.add_argument("--deals-limit", type=int, default=20)
    adapter_check_parser.add_argument("--summary-only", action="store_true")
    adapter_check_parser.add_argument("--include-raw", action="store_true")
    adapter_check_parser.add_argument("--save", action="store_true")
    adapter_check_parser.add_argument("--output")

    adapter_manifest_parser = subparsers.add_parser("nautilus-adapter-manifest")
    adapter_manifest_parser.add_argument("--output")

    runtime_harness_parser = subparsers.add_parser("nautilus-runtime-harness")
    runtime_harness_parser.add_argument("--symbol", default="BTC_USDT")
    runtime_harness_parser.add_argument("--currency", default="USDT")
    runtime_harness_parser.add_argument("--market-messages", type=int, default=5)
    runtime_harness_parser.add_argument("--private-ws-messages", type=int, default=5)
    runtime_harness_parser.add_argument("--history-limit", type=int, default=20)
    runtime_harness_parser.add_argument("--deals-limit", type=int, default=20)
    runtime_harness_parser.add_argument("--summary-only", action="store_true")
    runtime_harness_parser.add_argument("--include-raw", action="store_true")
    runtime_harness_parser.add_argument("--save", action="store_true")
    runtime_harness_parser.add_argument("--output")

    runtime_wire_parser = subparsers.add_parser("nautilus-runtime-wire")
    runtime_wire_parser.add_argument("--symbol", action="append")
    runtime_wire_parser.add_argument("--summary-only", action="store_true")
    runtime_wire_parser.add_argument("--include-raw", action="store_true")
    runtime_wire_parser.add_argument("--save", action="store_true")
    runtime_wire_parser.add_argument("--output")

    market_wire_parser = subparsers.add_parser("nautilus-market-wire")
    market_wire_parser.add_argument("--symbol", default="BTC_USDT")
    market_wire_parser.add_argument("--messages", type=int, default=5)
    market_wire_parser.add_argument("--summary-only", action="store_true")
    market_wire_parser.add_argument("--include-raw", action="store_true")
    market_wire_parser.add_argument("--save", action="store_true")
    market_wire_parser.add_argument("--output")

    execution_wire_parser = subparsers.add_parser("nautilus-execution-wire")
    execution_wire_parser.add_argument("--symbol", default="BTC_USDT")
    execution_wire_parser.add_argument("--currency", default="USDT")
    execution_wire_parser.add_argument("--history-limit", type=int, default=20)
    execution_wire_parser.add_argument("--deals-limit", type=int, default=20)
    execution_wire_parser.add_argument("--summary-only", action="store_true")
    execution_wire_parser.add_argument("--include-raw", action="store_true")
    execution_wire_parser.add_argument("--save", action="store_true")
    execution_wire_parser.add_argument("--output")

    state_handoff_parser = subparsers.add_parser("nautilus-state-handoff")
    state_handoff_parser.add_argument("--symbol", default="BTC_USDT")
    state_handoff_parser.add_argument("--currency", default="USDT")
    state_handoff_parser.add_argument("--market-messages", type=int, default=5)
    state_handoff_parser.add_argument("--history-limit", type=int, default=20)
    state_handoff_parser.add_argument("--deals-limit", type=int, default=20)
    state_handoff_parser.add_argument("--leverage", type=int, default=2)
    state_handoff_parser.add_argument("--max-notional", type=float, default=10.0)
    state_handoff_parser.add_argument("--summary-only", action="store_true")
    state_handoff_parser.add_argument("--include-raw", action="store_true")
    state_handoff_parser.add_argument("--save", action="store_true")
    state_handoff_parser.add_argument("--output")

    paper_decision_parser = subparsers.add_parser("nautilus-paper-decision")
    paper_decision_parser.add_argument("--symbol", default="BTC_USDT")
    paper_decision_parser.add_argument("--currency", default="USDT")
    paper_decision_parser.add_argument("--market-messages", type=int, default=5)
    paper_decision_parser.add_argument("--history-limit", type=int, default=20)
    paper_decision_parser.add_argument("--deals-limit", type=int, default=20)
    paper_decision_parser.add_argument("--leverage", type=int, default=2)
    paper_decision_parser.add_argument("--max-notional", type=float, default=10.0)
    paper_decision_parser.add_argument("--min-confidence", type=float, default=0.65)
    paper_decision_parser.add_argument("--max-margin-fraction", type=float, default=0.75)
    paper_decision_parser.add_argument("--paper-equity")
    paper_decision_parser.add_argument("--min-depth-imbalance", type=float, default=0.12)
    paper_decision_parser.add_argument("--max-spread-bps", type=float, default=2.5)
    paper_decision_parser.add_argument("--max-abs-funding-rate", type=float, default=0.0005)
    paper_decision_parser.add_argument("--max-market-age-seconds", type=int, default=60)
    paper_decision_parser.add_argument("--quality-gate-lookback", type=int, default=50)
    paper_decision_parser.add_argument("--quality-min-samples", type=int, default=5)
    paper_decision_parser.add_argument("--quality-edge-horizon-samples", type=int, default=3)
    paper_decision_parser.add_argument("--quality-min-edge-evaluable", type=int, default=3)
    paper_decision_parser.add_argument("--quality-min-edge-win-rate", type=float, default=0.55)
    paper_decision_parser.add_argument("--quality-min-side-edge-evaluable", type=int, default=2)
    paper_decision_parser.add_argument("--quality-min-side-edge-win-rate", type=float, default=0.55)
    paper_decision_parser.add_argument("--quality-recovery-window-evaluable", type=int, default=3)
    paper_decision_parser.add_argument("--quality-recovery-min-win-rate", type=float, default=0.55)
    paper_decision_parser.add_argument("--quality-max-sample-age-seconds", type=int, default=3600)
    paper_decision_parser.add_argument(
        "--quality-rolling-windows",
        type=_parse_rolling_windows,
        default=DEFAULT_ROLLING_WINDOWS,
    )
    paper_decision_parser.add_argument("--trend-filter", action="store_true")
    paper_decision_parser.add_argument("--trend-interval", default="1m")
    paper_decision_parser.add_argument("--trend-lookback", type=int, default=60)
    paper_decision_parser.add_argument("--trend-short-period", type=int, default=5)
    paper_decision_parser.add_argument("--trend-long-period", type=int, default=20)
    paper_decision_parser.add_argument("--trend-max-candle-age-seconds", type=int, default=300)
    paper_decision_parser.add_argument("--volatility-filter", action="store_true")
    paper_decision_parser.add_argument("--volatility-interval", default="1m")
    paper_decision_parser.add_argument("--volatility-lookback", type=int, default=60)
    paper_decision_parser.add_argument("--min-avg-range-bps", type=float)
    paper_decision_parser.add_argument("--max-avg-range-bps", type=float)
    paper_decision_parser.add_argument("--min-latest-range-bps", type=float)
    paper_decision_parser.add_argument("--max-latest-range-bps", type=float)
    paper_decision_parser.add_argument("--volatility-max-candle-age-seconds", type=int, default=300)
    paper_decision_parser.add_argument("--summary-only", action="store_true")
    paper_decision_parser.add_argument("--include-raw", action="store_true")
    paper_decision_parser.add_argument("--save", action="store_true")
    paper_decision_parser.add_argument("--output")

    paper_loop_parser = subparsers.add_parser("nautilus-paper-loop")
    paper_loop_parser.add_argument("--symbol", default="BTC_USDT")
    paper_loop_parser.add_argument("--currency", default="USDT")
    paper_loop_parser.add_argument("--market-messages", type=int, default=5)
    paper_loop_parser.add_argument("--history-limit", type=int, default=20)
    paper_loop_parser.add_argument("--deals-limit", type=int, default=20)
    paper_loop_parser.add_argument("--leverage", type=int, default=2)
    paper_loop_parser.add_argument("--max-notional", type=float, default=10.0)
    paper_loop_parser.add_argument("--min-confidence", type=float, default=0.65)
    paper_loop_parser.add_argument("--max-margin-fraction", type=float, default=0.75)
    paper_loop_parser.add_argument("--paper-equity")
    paper_loop_parser.add_argument("--min-depth-imbalance", type=float, default=0.12)
    paper_loop_parser.add_argument("--max-spread-bps", type=float, default=2.5)
    paper_loop_parser.add_argument("--max-abs-funding-rate", type=float, default=0.0005)
    paper_loop_parser.add_argument("--max-market-age-seconds", type=int, default=60)
    paper_loop_parser.add_argument("--quality-gate-lookback", type=int, default=50)
    paper_loop_parser.add_argument("--quality-min-samples", type=int, default=5)
    paper_loop_parser.add_argument("--quality-edge-horizon-samples", type=int, default=3)
    paper_loop_parser.add_argument("--quality-min-edge-evaluable", type=int, default=3)
    paper_loop_parser.add_argument("--quality-min-edge-win-rate", type=float, default=0.55)
    paper_loop_parser.add_argument("--quality-min-side-edge-evaluable", type=int, default=2)
    paper_loop_parser.add_argument("--quality-min-side-edge-win-rate", type=float, default=0.55)
    paper_loop_parser.add_argument("--quality-recovery-window-evaluable", type=int, default=3)
    paper_loop_parser.add_argument("--quality-recovery-min-win-rate", type=float, default=0.55)
    paper_loop_parser.add_argument("--quality-max-sample-age-seconds", type=int, default=3600)
    paper_loop_parser.add_argument(
        "--quality-rolling-windows",
        type=_parse_rolling_windows,
        default=DEFAULT_ROLLING_WINDOWS,
    )
    paper_loop_parser.add_argument("--trend-filter", action="store_true")
    paper_loop_parser.add_argument("--trend-interval", default="1m")
    paper_loop_parser.add_argument("--trend-lookback", type=int, default=60)
    paper_loop_parser.add_argument("--trend-short-period", type=int, default=5)
    paper_loop_parser.add_argument("--trend-long-period", type=int, default=20)
    paper_loop_parser.add_argument("--trend-max-candle-age-seconds", type=int, default=300)
    paper_loop_parser.add_argument("--volatility-filter", action="store_true")
    paper_loop_parser.add_argument("--volatility-interval", default="1m")
    paper_loop_parser.add_argument("--volatility-lookback", type=int, default=60)
    paper_loop_parser.add_argument("--min-avg-range-bps", type=float)
    paper_loop_parser.add_argument("--max-avg-range-bps", type=float)
    paper_loop_parser.add_argument("--min-latest-range-bps", type=float)
    paper_loop_parser.add_argument("--max-latest-range-bps", type=float)
    paper_loop_parser.add_argument("--volatility-max-candle-age-seconds", type=int, default=300)
    paper_loop_parser.add_argument("--iterations", type=int, default=3)
    paper_loop_parser.add_argument("--interval", type=float, default=5.0)
    paper_loop_parser.add_argument("--target-samples", type=int)
    paper_loop_parser.add_argument("--target-closed-trades", type=int)
    paper_loop_parser.add_argument("--readiness-after", action="store_true")
    paper_loop_parser.add_argument("--readiness-output")
    paper_loop_parser.add_argument("--readiness-initial-equity")
    paper_loop_parser.add_argument("--include-raw", action="store_true")
    paper_loop_parser.add_argument("--save", action="store_true")
    paper_loop_parser.add_argument("--output")

    paper_audit_parser = subparsers.add_parser("nautilus-paper-audit")
    paper_audit_parser.add_argument("--symbol", default="BTC_USDT")
    paper_audit_parser.add_argument("--currency", default="USDT")
    paper_audit_parser.add_argument("--lookback", type=int, default=20)
    paper_audit_parser.add_argument("--min-samples", type=int, default=3)
    paper_audit_parser.add_argument("--edge-horizon-samples", type=int, default=1)
    paper_audit_parser.add_argument("--min-edge-evaluable", type=int, default=3)
    paper_audit_parser.add_argument("--min-edge-win-rate", type=float, default=0.55)
    paper_audit_parser.add_argument("--min-side-edge-evaluable", type=int, default=2)
    paper_audit_parser.add_argument("--min-side-edge-win-rate", type=float, default=0.55)
    paper_audit_parser.add_argument("--recovery-window-evaluable", type=int, default=3)
    paper_audit_parser.add_argument("--recovery-min-win-rate", type=float, default=0.55)
    paper_audit_parser.add_argument("--max-sample-age-seconds", type=int, default=3600)
    paper_audit_parser.add_argument("--rolling-windows", type=_parse_rolling_windows, default=DEFAULT_ROLLING_WINDOWS)
    paper_audit_parser.add_argument(
        "--price-simulation",
        choices=(PRICE_SIMULATION_SAMPLE_CLOSE, PRICE_SIMULATION_CANDLE_HIGH_LOW),
        default=PRICE_SIMULATION_CANDLE_HIGH_LOW,
    )
    paper_audit_parser.add_argument("--candle-interval", default="1m")
    paper_audit_parser.add_argument("--candle-lookback", type=int, default=240)
    paper_audit_parser.add_argument("--no-sample-close-fallback", action="store_true")
    paper_audit_parser.add_argument("--output")

    paper_edge_parser = subparsers.add_parser("nautilus-paper-edge")
    paper_edge_parser.add_argument("--symbol", default="BTC_USDT")
    paper_edge_parser.add_argument("--currency", default="USDT")
    paper_edge_parser.add_argument("--lookback", type=int, default=50)
    paper_edge_parser.add_argument("--horizon-samples", type=int, default=1)
    paper_edge_parser.add_argument("--min-evaluable", type=int, default=3)
    paper_edge_parser.add_argument(
        "--price-simulation",
        choices=(PRICE_SIMULATION_SAMPLE_CLOSE, PRICE_SIMULATION_CANDLE_HIGH_LOW),
        default=PRICE_SIMULATION_CANDLE_HIGH_LOW,
    )
    paper_edge_parser.add_argument("--candle-interval", default="1m")
    paper_edge_parser.add_argument("--candle-lookback", type=int, default=240)
    paper_edge_parser.add_argument("--no-sample-close-fallback", action="store_true")
    paper_edge_parser.add_argument("--output")

    paper_ledger_parser = subparsers.add_parser("nautilus-paper-ledger")
    paper_ledger_parser.add_argument("--symbol", default="BTC_USDT")
    paper_ledger_parser.add_argument("--currency", default="USDT")
    paper_ledger_parser.add_argument("--lookback", type=int, default=100)
    paper_ledger_parser.add_argument("--horizon-samples", type=int, default=3)
    paper_ledger_parser.add_argument("--include-probes", action="store_true")
    paper_ledger_parser.add_argument(
        "--price-simulation",
        choices=(PRICE_SIMULATION_SAMPLE_CLOSE, PRICE_SIMULATION_CANDLE_HIGH_LOW),
        default=PRICE_SIMULATION_SAMPLE_CLOSE,
    )
    paper_ledger_parser.add_argument("--candle-interval", default="1m")
    paper_ledger_parser.add_argument("--candle-lookback", type=int, default=120)
    paper_ledger_parser.add_argument("--no-sample-close-fallback", action="store_true")
    paper_ledger_parser.add_argument("--save", action="store_true")
    paper_ledger_parser.add_argument("--output")

    paper_performance_parser = subparsers.add_parser("nautilus-paper-performance")
    paper_performance_parser.add_argument("--symbol", default="BTC_USDT")
    paper_performance_parser.add_argument("--currency", default="USDT")
    paper_performance_parser.add_argument("--lookback", type=int, default=100)
    paper_performance_parser.add_argument("--horizon-samples", type=int, default=3)
    paper_performance_parser.add_argument("--include-probes", action="store_true")
    paper_performance_parser.add_argument(
        "--price-simulation",
        choices=(PRICE_SIMULATION_SAMPLE_CLOSE, PRICE_SIMULATION_CANDLE_HIGH_LOW),
        default=PRICE_SIMULATION_SAMPLE_CLOSE,
    )
    paper_performance_parser.add_argument("--candle-interval", default="1m")
    paper_performance_parser.add_argument("--candle-lookback", type=int, default=120)
    paper_performance_parser.add_argument("--no-sample-close-fallback", action="store_true")
    paper_performance_parser.add_argument("--ledger")
    paper_performance_parser.add_argument("--initial-equity")
    paper_performance_parser.add_argument("--save", action="store_true")
    paper_performance_parser.add_argument("--output")

    profit_hunt_parser = subparsers.add_parser("nautilus-profit-hunt")
    profit_hunt_parser.add_argument("--symbol", default="BTC_USDT")
    profit_hunt_parser.add_argument("--currency", default="USDT")
    profit_hunt_parser.add_argument("--lookback", type=int, default=100)
    profit_hunt_parser.add_argument("--horizon-samples", type=int, default=3)
    profit_hunt_parser.add_argument("--candle-interval", default="1m")
    profit_hunt_parser.add_argument("--candle-lookback", type=int, default=240)
    profit_hunt_parser.add_argument("--initial-equity")
    profit_hunt_parser.add_argument("--confidence-thresholds", default=",".join(str(item) for item in DEFAULT_CONFIDENCE_THRESHOLDS))
    profit_hunt_parser.add_argument("--min-depth-imbalance-sweep", default="")
    profit_hunt_parser.add_argument("--max-spread-bps-sweep", default="")
    profit_hunt_parser.add_argument("--max-abs-funding-rate-sweep", default="")
    profit_hunt_parser.add_argument("--min-avg-range-bps-sweep", default="")
    profit_hunt_parser.add_argument("--max-avg-range-bps-sweep", default="")
    profit_hunt_parser.add_argument("--min-latest-range-bps-sweep", default="")
    profit_hunt_parser.add_argument("--max-latest-range-bps-sweep", default="")
    profit_hunt_parser.add_argument("--min-closed-count", type=int, default=50)
    profit_hunt_parser.add_argument("--min-win-rate", type=float, default=0.55)
    profit_hunt_parser.add_argument("--min-profit-factor", type=float, default=1.25)
    profit_hunt_parser.add_argument("--max-drawdown-pct", type=float, default=0.02)
    profit_hunt_parser.add_argument("--save", action="store_true")
    profit_hunt_parser.add_argument("--output")

    pairs_parser = subparsers.add_parser("pairs")
    pairs_parser.add_argument("--api-tradable-only", action="store_true")

    ticker_parser = subparsers.add_parser("ticker")
    ticker_parser.add_argument("symbol", nargs="?")

    depth_parser = subparsers.add_parser("depth")
    depth_parser.add_argument("symbol")
    depth_parser.add_argument("--limit", type=int)

    index_parser = subparsers.add_parser("index-price")
    index_parser.add_argument("symbol")

    fair_parser = subparsers.add_parser("fair-price")
    fair_parser.add_argument("symbol")

    funding_parser = subparsers.add_parser("funding-rate")
    funding_parser.add_argument("symbol")

    klines_parser = subparsers.add_parser("klines")
    klines_parser.add_argument("symbol")
    klines_parser.add_argument("--interval", default="1m")
    klines_parser.add_argument("--lookback", type=int, default=60)
    klines_parser.add_argument("--start-time-ms", type=int)
    klines_parser.add_argument("--end-time-ms", type=int)
    klines_parser.add_argument("--summary-only", action="store_true")

    subparsers.add_parser("network-check")
    subparsers.add_parser("dns-check")
    readiness_parser = subparsers.add_parser("readiness")
    readiness_parser.add_argument("--symbol", default="BTC_USDT")
    readiness_parser.add_argument("--currency", default="USDT")
    readiness_parser.add_argument("--lookback", type=int, default=100)
    readiness_parser.add_argument("--target-samples", type=int, default=100)
    readiness_parser.add_argument("--min-samples", type=int, default=5)
    readiness_parser.add_argument("--edge-horizon-samples", type=int, default=3)
    readiness_parser.add_argument("--min-edge-evaluable", type=int, default=3)
    readiness_parser.add_argument("--min-edge-win-rate", type=float, default=0.55)
    readiness_parser.add_argument("--min-side-edge-evaluable", type=int, default=2)
    readiness_parser.add_argument("--min-side-edge-win-rate", type=float, default=0.55)
    readiness_parser.add_argument("--recovery-window-evaluable", type=int, default=3)
    readiness_parser.add_argument("--recovery-min-win-rate", type=float, default=0.55)
    readiness_parser.add_argument("--max-sample-age-seconds", type=int, default=3600)
    readiness_parser.add_argument("--rolling-windows", type=_parse_rolling_windows, default=DEFAULT_ROLLING_WINDOWS)
    readiness_parser.add_argument(
        "--price-simulation",
        choices=(PRICE_SIMULATION_SAMPLE_CLOSE, PRICE_SIMULATION_CANDLE_HIGH_LOW),
        default=PRICE_SIMULATION_CANDLE_HIGH_LOW,
    )
    readiness_parser.add_argument("--candle-interval", default="1m")
    readiness_parser.add_argument("--candle-lookback", type=int, default=240)
    readiness_parser.add_argument("--no-sample-close-fallback", action="store_true")
    readiness_parser.add_argument("--performance-initial-equity")
    readiness_parser.add_argument("--performance-horizon-samples", type=int)
    readiness_parser.add_argument("--performance-include-probes", action="store_true")
    readiness_parser.add_argument("--min-performance-closed-count", type=int, default=50)
    readiness_parser.add_argument("--min-performance-win-rate", type=float, default=0.55)
    readiness_parser.add_argument("--min-profit-factor", type=float, default=1.25)
    readiness_parser.add_argument("--max-drawdown-pct", type=float, default=0.02)
    readiness_parser.add_argument("--max-consecutive-losses", type=int, default=3)
    readiness_parser.add_argument("--output")

    smoke_parser = subparsers.add_parser("smoke-readonly")
    smoke_parser.add_argument("--symbol", default="BTC_USDT")
    smoke_parser.add_argument("--currency", default="USDT")

    asset_parser = subparsers.add_parser("asset")
    asset_parser.add_argument("currency")

    subparsers.add_parser("assets")

    positions_parser = subparsers.add_parser("positions")
    positions_parser.add_argument("symbol", nargs="?")

    orders_parser = subparsers.add_parser("open-orders")
    orders_parser.add_argument("--page-num", type=int, default=1)
    orders_parser.add_argument("--page-size", type=int, default=100)

    history_parser = subparsers.add_parser("history-orders")
    history_parser.add_argument("--symbol")
    history_parser.add_argument("--page-num", type=int, default=1)
    history_parser.add_argument("--page-size", type=int, default=20)
    history_parser.add_argument("--states")

    deals_parser = subparsers.add_parser("order-deals")
    deals_parser.add_argument("symbol")
    deals_parser.add_argument("--page-num", type=int, default=1)
    deals_parser.add_argument("--page-size", type=int, default=100)

    reconcile_parser = subparsers.add_parser("reconcile")
    reconcile_parser.add_argument("--symbol")
    reconcile_parser.add_argument("--currency", default="USDT")
    reconcile_parser.add_argument("--summary-only", action="store_true")
    reconcile_parser.add_argument("--save", action="store_true")

    reconcile_engine_parser = subparsers.add_parser("reconcile-engine")
    reconcile_engine_parser.add_argument("--symbol", default="BTC_USDT")
    reconcile_engine_parser.add_argument("--currency", default="USDT")
    reconcile_engine_parser.add_argument("--ws-messages", type=int, default=5)
    reconcile_engine_parser.add_argument("--history-limit", type=int, default=20)
    reconcile_engine_parser.add_argument("--deals-limit", type=int, default=20)
    reconcile_engine_parser.add_argument("--summary-only", action="store_true")
    reconcile_engine_parser.add_argument("--include-raw", action="store_true")
    reconcile_engine_parser.add_argument("--save", action="store_true")
    reconcile_engine_parser.add_argument("--output")

    exec_reports_parser = subparsers.add_parser("execution-reports")
    exec_reports_parser.add_argument("--symbol", default="BTC_USDT")
    exec_reports_parser.add_argument("--currency", default="USDT")
    exec_reports_parser.add_argument("--history-limit", type=int, default=20)
    exec_reports_parser.add_argument("--deals-limit", type=int, default=20)
    exec_reports_parser.add_argument("--summary-only", action="store_true")
    exec_reports_parser.add_argument("--include-raw", action="store_true")
    exec_reports_parser.add_argument("--save", action="store_true")
    exec_reports_parser.add_argument("--output")

    store_parser = subparsers.add_parser("store")
    store_parser.add_argument("action", choices=("stats", "latest"))
    store_parser.add_argument("--event-type")
    store_parser.add_argument("--symbol")
    store_parser.add_argument("--currency")
    store_parser.add_argument("--limit", type=int, default=20)

    subparsers.add_parser("safety-status")
    subparsers.add_parser("audit-safety")

    kill_parser = subparsers.add_parser("kill-switch")
    kill_parser.add_argument("action", choices=("on", "off", "status"))

    ws_public_parser = subparsers.add_parser("ws-public")
    ws_public_parser.add_argument("channel", choices=("ticker", "deal", "depth"))
    ws_public_parser.add_argument("symbol")
    ws_public_parser.add_argument("--messages", type=int, default=5)

    ws_bridge_parser = subparsers.add_parser("ws-bridge")
    ws_bridge_parser.add_argument("channel", choices=("ticker", "deal", "depth"))
    ws_bridge_parser.add_argument("symbol")
    ws_bridge_parser.add_argument("--messages", type=int, default=5)
    ws_bridge_parser.add_argument("--include-raw", action="store_true")
    ws_bridge_parser.add_argument("--save", action="store_true")

    ws_private_parser = subparsers.add_parser("ws-private")
    ws_private_parser.add_argument("--messages", type=int, default=5)

    ws_private_bridge_parser = subparsers.add_parser("ws-private-bridge")
    ws_private_bridge_parser.add_argument("--messages", type=int, default=5)
    ws_private_bridge_parser.add_argument("--include-raw", action="store_true")
    ws_private_bridge_parser.add_argument("--save", action="store_true")

    dry_order_parser = subparsers.add_parser("dry-run-order")
    dry_order_parser.add_argument("--symbol", required=True)
    dry_order_parser.add_argument("--side", choices=sorted(SIDE_MAP), required=True)
    dry_order_parser.add_argument("--order-type", choices=sorted(ORDER_TYPE_MAP), required=True)
    dry_order_parser.add_argument("--open-type", choices=sorted(OPEN_TYPE_MAP), default="isolated")
    dry_order_parser.add_argument("--price", type=float, required=True)
    dry_order_parser.add_argument("--vol", type=float, required=True)
    dry_order_parser.add_argument("--contract-size", type=float)
    dry_order_parser.add_argument("--leverage", type=int)
    dry_order_parser.add_argument("--currency", default="USDT")
    dry_order_parser.add_argument("--external-oid")
    dry_order_parser.add_argument("--stop-loss-price", type=float)
    dry_order_parser.add_argument("--take-profit-price", type=float)

    preflight_parser = subparsers.add_parser("preflight-order")
    preflight_parser.add_argument("--symbol", required=True)
    preflight_parser.add_argument("--side", choices=sorted(SIDE_MAP), required=True)
    preflight_parser.add_argument("--order-type", choices=sorted(ORDER_TYPE_MAP), required=True)
    preflight_parser.add_argument("--open-type", choices=sorted(OPEN_TYPE_MAP), default="isolated")
    preflight_parser.add_argument("--price", type=float, required=True)
    preflight_parser.add_argument("--vol", type=float, required=True)
    preflight_parser.add_argument("--leverage", type=int)
    preflight_parser.add_argument("--stop-loss-price", type=float)
    preflight_parser.add_argument("--take-profit-price", type=float)
    preflight_parser.add_argument("--currency", default="USDT")
    preflight_parser.add_argument("--save", action="store_true")

    signal_parser = subparsers.add_parser("strategy-signal")
    signal_parser.add_argument("--symbol", required=True)
    signal_parser.add_argument("--currency", default="USDT")
    signal_parser.add_argument("--leverage", type=int, default=2)
    signal_parser.add_argument("--max-notional", type=float, default=10.0)
    signal_parser.add_argument("--save", action="store_true")

    runner_parser = subparsers.add_parser("strategy-run")
    runner_parser.add_argument("--symbol", required=True)
    runner_parser.add_argument("--currency", default="USDT")
    runner_parser.add_argument("--leverage", type=int, default=2)
    runner_parser.add_argument("--max-notional", type=float, default=10.0)
    runner_parser.add_argument("--iterations", type=int, default=3)
    runner_parser.add_argument("--interval", type=float, default=5.0)
    runner_parser.add_argument("--save", action="store_true")

    evaluate_parser = subparsers.add_parser("strategy-evaluate")
    evaluate_parser.add_argument("--symbol", required=True)
    evaluate_parser.add_argument("--currency", default="USDT")
    evaluate_parser.add_argument("--lookback", type=int, default=5)
    evaluate_parser.add_argument("--min-consensus", type=int, default=3)
    evaluate_parser.add_argument("--min-confidence", type=float, default=0.65)

    args = parser.parse_args(argv)
    mexc_settings = MexcSettings.from_env()
    risk_settings = RiskSettings.from_env()
    client = MexcFuturesClient(mexc_settings, risk_engine=RiskEngine(risk_settings))

    try:
        if args.command == "ping":
            print_json(client.ping())
        elif args.command == "contract":
            print_json(client.contract_detail(args.symbol))
        elif args.command == "nautilus-instrument":
            response = client.contract_detail(args.symbol)
            rows = extract_or_raise_contract_rows(response, args.symbol)
            try:
                specs = [contract_row_to_nautilus_spec(row).to_dict() for row in rows]
            except ValueError as exc:
                raise MexcApiError(str(exc)) from exc
            print_json(
                {
                    "symbol": args.symbol.upper(),
                    "source": "MEXC live contract detail",
                    "specs": specs,
                }
            )
        elif args.command == "nautilus-instruments":
            provider = MexcNautilusInstrumentProvider(client)
            symbols = normalize_symbols(args.symbols or [])
            report = (
                provider.load_symbols(
                    symbols,
                    api_tradable_only=not args.include_non_tradable,
                )
                if symbols
                else provider.load_all(api_tradable_only=not args.include_non_tradable)
            )
            if args.output:
                output_path = _write_json_output(args.output, report.to_dict(include_specs=True, include_symbols=True))
                payload = report.to_dict(include_specs=False, include_symbols=False)
                payload["output"] = str(output_path)
            else:
                payload = report.to_dict(include_specs=not args.summary_only, include_symbols=not args.summary_only)
            print_json(payload)
        elif args.command == "nautilus-adapter-check":
            full_payload = run_nautilus_adapter_check(
                client,
                mexc_settings,
                symbol=args.symbol,
                currency=args.currency,
                market_messages=args.market_messages,
                private_ws_messages=args.private_ws_messages,
                history_limit=args.history_limit,
                deals_limit=args.deals_limit,
                include_raw=args.include_raw,
            )
            payload = (
                summarize_nautilus_adapter_readiness_report(full_payload)
                if args.summary_only
                else full_payload
            )
            if args.output:
                output_path = _write_json_output(args.output, full_payload)
                payload = {**summarize_nautilus_adapter_readiness_report(full_payload), "output": str(output_path)}
            if args.save:
                payload = _save_payload(mexc_settings, "nautilus_adapter_check", payload)
            print_json(payload)
        elif args.command == "nautilus-adapter-manifest":
            payload = build_adapter_manifest(upstream_reference=_upstream_reference_status(Path.cwd()))
            if args.output:
                output_path = _write_json_output(args.output, payload)
                payload = {**payload, "output": str(output_path)}
            print_json(payload)
        elif args.command == "nautilus-runtime-harness":
            full_payload = run_nautilus_runtime_harness(
                client,
                mexc_settings,
                symbol=args.symbol,
                currency=args.currency,
                market_messages=args.market_messages,
                private_ws_messages=args.private_ws_messages,
                history_limit=args.history_limit,
                deals_limit=args.deals_limit,
                include_raw=args.include_raw,
            )
            payload = summarize_runtime_harness_report(full_payload) if args.summary_only else full_payload
            if args.output:
                output_path = _write_json_output(args.output, full_payload)
                payload = {**summarize_runtime_harness_report(full_payload), "output": str(output_path)}
            if args.save:
                payload = _save_payload(mexc_settings, "nautilus_runtime_harness", payload)
            print_json(payload)
        elif args.command == "nautilus-runtime-wire":
            full_payload = run_nautilus_runtime_wire(
                client,
                mexc_settings,
                symbols=normalize_symbols(args.symbol or ["BTC_USDT"]),
                include_raw=args.include_raw,
            )
            payload = summarize_runtime_wire_report(full_payload) if args.summary_only else full_payload
            if args.output:
                output_path = _write_json_output(args.output, full_payload)
                payload = {**summarize_runtime_wire_report(full_payload), "output": str(output_path)}
            if args.save:
                payload = _save_payload(mexc_settings, "nautilus_runtime_wire", payload)
            print_json(payload)
        elif args.command == "nautilus-market-wire":
            full_payload = run_nautilus_market_wire(
                mexc_settings,
                symbol=args.symbol,
                messages=args.messages,
                include_raw=args.include_raw,
            )
            payload = summarize_market_runtime_wire_report(full_payload) if args.summary_only else full_payload
            if args.output:
                output_path = _write_json_output(args.output, full_payload)
                payload = {**summarize_market_runtime_wire_report(full_payload), "output": str(output_path)}
            if args.save:
                payload = _save_payload(mexc_settings, "nautilus_market_wire", payload)
            print_json(payload)
        elif args.command == "nautilus-execution-wire":
            full_payload = run_nautilus_execution_wire(
                client,
                mexc_settings,
                symbol=args.symbol,
                currency=args.currency,
                history_limit=args.history_limit,
                deals_limit=args.deals_limit,
                include_raw=args.include_raw,
            )
            payload = summarize_execution_runtime_wire_report(full_payload) if args.summary_only else full_payload
            if args.output:
                output_path = _write_json_output(args.output, full_payload)
                payload = {**summarize_execution_runtime_wire_report(full_payload), "output": str(output_path)}
            if args.save:
                payload = _save_payload(mexc_settings, "nautilus_execution_wire", payload)
            print_json(payload)
        elif args.command == "nautilus-state-handoff":
            full_payload = run_nautilus_state_handoff(
                client,
                mexc_settings,
                symbol=args.symbol,
                currency=args.currency,
                market_messages=args.market_messages,
                history_limit=args.history_limit,
                deals_limit=args.deals_limit,
                leverage=args.leverage,
                max_notional_usdt=args.max_notional,
                include_raw=args.include_raw,
            )
            payload = summarize_nautilus_state_handoff_report(full_payload) if args.summary_only else full_payload
            if args.output:
                output_path = _write_json_output(args.output, full_payload)
                payload = {**summarize_nautilus_state_handoff_report(full_payload), "output": str(output_path)}
            if args.save:
                payload = _save_payload(mexc_settings, "nautilus_state_handoff", payload)
            print_json(payload)
        elif args.command == "nautilus-paper-decision":
            full_payload = run_nautilus_paper_decision(
                client,
                mexc_settings,
                symbol=args.symbol,
                currency=args.currency,
                market_messages=args.market_messages,
                history_limit=args.history_limit,
                deals_limit=args.deals_limit,
                leverage=args.leverage,
                max_notional_usdt=args.max_notional,
                min_confidence=args.min_confidence,
                max_margin_fraction=args.max_margin_fraction,
                paper_equity_usdt=args.paper_equity,
                min_depth_imbalance=args.min_depth_imbalance,
                max_spread_bps=args.max_spread_bps,
                max_abs_funding_rate=args.max_abs_funding_rate,
                max_market_age_seconds=args.max_market_age_seconds,
                quality_gate_lookback=args.quality_gate_lookback,
                quality_min_samples=args.quality_min_samples,
                quality_edge_horizon_samples=args.quality_edge_horizon_samples,
                quality_min_edge_evaluable=args.quality_min_edge_evaluable,
                quality_min_edge_win_rate=args.quality_min_edge_win_rate,
                quality_min_side_edge_evaluable=args.quality_min_side_edge_evaluable,
                quality_min_side_edge_win_rate=args.quality_min_side_edge_win_rate,
                quality_recovery_window_evaluable=args.quality_recovery_window_evaluable,
                quality_recovery_min_win_rate=args.quality_recovery_min_win_rate,
                quality_max_sample_age_seconds=args.quality_max_sample_age_seconds,
                quality_rolling_windows=args.quality_rolling_windows,
                trend_filter_enabled=args.trend_filter,
                trend_interval=args.trend_interval,
                trend_lookback=args.trend_lookback,
                trend_short_period=args.trend_short_period,
                trend_long_period=args.trend_long_period,
                trend_max_candle_age_seconds=args.trend_max_candle_age_seconds,
                volatility_filter_enabled=_volatility_filter_requested(args),
                volatility_interval=args.volatility_interval,
                volatility_lookback=args.volatility_lookback,
                min_avg_range_bps=args.min_avg_range_bps,
                max_avg_range_bps=args.max_avg_range_bps,
                min_latest_range_bps=args.min_latest_range_bps,
                max_latest_range_bps=args.max_latest_range_bps,
                volatility_max_candle_age_seconds=args.volatility_max_candle_age_seconds,
                include_raw=args.include_raw,
            )
            payload = summarize_paper_decision_report(full_payload) if args.summary_only else full_payload
            if args.output:
                output_path = _write_json_output(args.output, full_payload)
                payload = {**summarize_paper_decision_report(full_payload), "output": str(output_path)}
            if args.save:
                payload = _save_payload(mexc_settings, "nautilus_paper_decision", payload)
            print_json(payload)
        elif args.command == "nautilus-paper-loop":
            payload = run_nautilus_paper_loop(
                client,
                mexc_settings,
                symbol=args.symbol,
                currency=args.currency,
                market_messages=args.market_messages,
                history_limit=args.history_limit,
                deals_limit=args.deals_limit,
                leverage=args.leverage,
                max_notional_usdt=args.max_notional,
                min_confidence=args.min_confidence,
                max_margin_fraction=args.max_margin_fraction,
                paper_equity_usdt=args.paper_equity,
                min_depth_imbalance=args.min_depth_imbalance,
                max_spread_bps=args.max_spread_bps,
                max_abs_funding_rate=args.max_abs_funding_rate,
                max_market_age_seconds=args.max_market_age_seconds,
                quality_gate_lookback=args.quality_gate_lookback,
                quality_min_samples=args.quality_min_samples,
                quality_edge_horizon_samples=args.quality_edge_horizon_samples,
                quality_min_edge_evaluable=args.quality_min_edge_evaluable,
                quality_min_edge_win_rate=args.quality_min_edge_win_rate,
                quality_min_side_edge_evaluable=args.quality_min_side_edge_evaluable,
                quality_min_side_edge_win_rate=args.quality_min_side_edge_win_rate,
                quality_recovery_window_evaluable=args.quality_recovery_window_evaluable,
                quality_recovery_min_win_rate=args.quality_recovery_min_win_rate,
                quality_max_sample_age_seconds=args.quality_max_sample_age_seconds,
                quality_rolling_windows=args.quality_rolling_windows,
                trend_filter_enabled=args.trend_filter,
                trend_interval=args.trend_interval,
                trend_lookback=args.trend_lookback,
                trend_short_period=args.trend_short_period,
                trend_long_period=args.trend_long_period,
                trend_max_candle_age_seconds=args.trend_max_candle_age_seconds,
                volatility_filter_enabled=_volatility_filter_requested(args),
                volatility_interval=args.volatility_interval,
                volatility_lookback=args.volatility_lookback,
                min_avg_range_bps=args.min_avg_range_bps,
                max_avg_range_bps=args.max_avg_range_bps,
                min_latest_range_bps=args.min_latest_range_bps,
                max_latest_range_bps=args.max_latest_range_bps,
                volatility_max_candle_age_seconds=args.volatility_max_candle_age_seconds,
                iterations=args.iterations,
                interval=args.interval,
                target_samples=args.target_samples,
                target_closed_trades=args.target_closed_trades,
                include_raw=args.include_raw,
                save=args.save,
            )
            if args.readiness_after:
                readiness = run_paper_readiness(
                    mexc_settings,
                    risk_settings,
                    client,
                    symbol=args.symbol,
                    currency=args.currency,
                    lookback=max(args.quality_gate_lookback, args.target_samples or 100),
                    target_samples=args.target_samples or 100,
                    min_samples=args.quality_min_samples,
                    edge_horizon_samples=args.quality_edge_horizon_samples,
                    min_edge_evaluable=args.quality_min_edge_evaluable,
                    min_edge_win_rate=args.quality_min_edge_win_rate,
                    min_side_edge_evaluable=args.quality_min_side_edge_evaluable,
                    min_side_edge_win_rate=args.quality_min_side_edge_win_rate,
                    recovery_window_evaluable=args.quality_recovery_window_evaluable,
                    recovery_min_win_rate=args.quality_recovery_min_win_rate,
                    max_sample_age_seconds=args.quality_max_sample_age_seconds,
                    rolling_windows=args.quality_rolling_windows,
                    performance_initial_equity=args.readiness_initial_equity,
                    performance_horizon_samples=args.quality_edge_horizon_samples,
                    performance_include_probes=False,
                )
                if args.readiness_output:
                    readiness_output = _write_json_output(args.readiness_output, readiness)
                    readiness = {**readiness, "output": str(readiness_output)}
                payload = {**payload, "readinessAfter": summarize_paper_readiness_report(readiness)}
            if args.output:
                output_path = _write_json_output(args.output, payload)
                payload = {**payload, "output": str(output_path)}
            print_json(payload)
        elif args.command == "nautilus-paper-audit":
            if args.lookback <= 0:
                raise MexcApiError("lookback must be positive")
            if args.min_samples <= 0:
                raise MexcApiError("min-samples must be positive")
            if args.edge_horizon_samples <= 0:
                raise MexcApiError("edge-horizon-samples must be positive")
            if args.min_edge_evaluable <= 0:
                raise MexcApiError("min-edge-evaluable must be positive")
            if args.min_edge_win_rate < 0:
                raise MexcApiError("min-edge-win-rate must be non-negative")
            if args.min_edge_win_rate > 1:
                raise MexcApiError("min-edge-win-rate must be at most 1")
            if args.min_side_edge_evaluable <= 0:
                raise MexcApiError("min-side-edge-evaluable must be positive")
            if args.min_side_edge_win_rate < 0:
                raise MexcApiError("min-side-edge-win-rate must be non-negative")
            if args.min_side_edge_win_rate > 1:
                raise MexcApiError("min-side-edge-win-rate must be at most 1")
            if args.recovery_window_evaluable <= 0:
                raise MexcApiError("recovery-window-evaluable must be positive")
            if args.recovery_min_win_rate < 0:
                raise MexcApiError("recovery-min-win-rate must be non-negative")
            if args.recovery_min_win_rate > 1:
                raise MexcApiError("recovery-min-win-rate must be at most 1")
            if args.max_sample_age_seconds <= 0:
                raise MexcApiError("max-sample-age-seconds must be positive")
            store = StateStore(mexc_settings.state_db)
            events = store.latest_events(
                event_type="nautilus_paper_decision",
                limit=args.lookback,
                symbol=args.symbol,
                currency=args.currency,
            )
            candles, candle_meta = _price_simulation_candles(
                client,
                symbol=args.symbol,
                price_simulation=args.price_simulation,
                candle_interval=args.candle_interval,
                candle_lookback=args.candle_lookback,
            )
            payload = build_paper_audit_report(
                events,
                symbol=args.symbol,
                currency=args.currency,
                min_samples=args.min_samples,
                edge_horizon_samples=args.edge_horizon_samples,
                min_edge_evaluable=args.min_edge_evaluable,
                min_edge_win_rate=args.min_edge_win_rate,
                min_side_edge_evaluable=args.min_side_edge_evaluable,
                min_side_edge_win_rate=args.min_side_edge_win_rate,
                policy_allowed_sides=mexc_settings.strategy_allowed_sides,
                recovery_window_evaluable=args.recovery_window_evaluable,
                recovery_min_win_rate=args.recovery_min_win_rate,
                max_sample_age_seconds=args.max_sample_age_seconds,
                rolling_windows=args.rolling_windows,
                candles=candles,
                price_simulation=args.price_simulation,
                allow_sample_close_fallback=False
                if args.price_simulation == PRICE_SIMULATION_CANDLE_HIGH_LOW
                else not args.no_sample_close_fallback,
            )
            payload = {**payload, **candle_meta}
            if args.output:
                output_path = _write_json_output(args.output, payload)
                payload = {**payload, "output": str(output_path)}
            print_json(payload)
        elif args.command == "nautilus-paper-edge":
            if args.lookback <= 0:
                raise MexcApiError("lookback must be positive")
            if args.horizon_samples <= 0:
                raise MexcApiError("horizon-samples must be positive")
            if args.min_evaluable <= 0:
                raise MexcApiError("min-evaluable must be positive")
            store = StateStore(mexc_settings.state_db)
            events = store.latest_events(
                event_type="nautilus_paper_decision",
                limit=args.lookback,
                symbol=args.symbol,
                currency=args.currency,
            )
            candles, candle_meta = _price_simulation_candles(
                client,
                symbol=args.symbol,
                price_simulation=args.price_simulation,
                candle_interval=args.candle_interval,
                candle_lookback=args.candle_lookback,
            )
            payload = build_paper_edge_report(
                events,
                symbol=args.symbol,
                currency=args.currency,
                horizon_samples=args.horizon_samples,
                min_evaluable=args.min_evaluable,
                candles=candles,
                price_simulation=args.price_simulation,
                allow_sample_close_fallback=False
                if args.price_simulation == PRICE_SIMULATION_CANDLE_HIGH_LOW
                else not args.no_sample_close_fallback,
            )
            payload = {**payload, **candle_meta}
            if args.output:
                output_path = _write_json_output(args.output, payload)
                payload = {**payload, "output": str(output_path)}
            print_json(payload)
        elif args.command == "nautilus-paper-ledger":
            if args.lookback <= 0:
                raise MexcApiError("lookback must be positive")
            if args.horizon_samples <= 0:
                raise MexcApiError("horizon-samples must be positive")
            store = StateStore(mexc_settings.state_db)
            events = store.latest_events(
                event_type="nautilus_paper_decision",
                limit=args.lookback,
                symbol=args.symbol,
                currency=args.currency,
            )
            candles, candle_meta = _price_simulation_candles(
                client,
                symbol=args.symbol,
                price_simulation=args.price_simulation,
                candle_interval=args.candle_interval,
                candle_lookback=args.candle_lookback,
            )
            payload = build_paper_ledger_report(
                events,
                symbol=args.symbol,
                currency=args.currency,
                horizon_samples=args.horizon_samples,
                include_probes=args.include_probes,
                candles=candles,
                price_simulation=args.price_simulation,
                allow_sample_close_fallback=not args.no_sample_close_fallback,
            )
            payload = {**payload, **candle_meta}
            if args.output:
                output_path = _write_json_output(args.output, payload)
                payload = {**payload, "output": str(output_path)}
            if args.save:
                payload = _save_payload(mexc_settings, "nautilus_paper_ledger", payload)
            print_json(payload)
        elif args.command == "nautilus-paper-performance":
            if args.ledger:
                ledger_payload = json.loads(Path(args.ledger).read_text(encoding="utf-8"))
            else:
                if args.lookback <= 0:
                    raise MexcApiError("lookback must be positive")
                if args.horizon_samples <= 0:
                    raise MexcApiError("horizon-samples must be positive")
                store = StateStore(mexc_settings.state_db)
                events = store.latest_events(
                    event_type="nautilus_paper_decision",
                    limit=args.lookback,
                    symbol=args.symbol,
                    currency=args.currency,
                )
                candles, candle_meta = _price_simulation_candles(
                    client,
                    symbol=args.symbol,
                    price_simulation=args.price_simulation,
                    candle_interval=args.candle_interval,
                    candle_lookback=args.candle_lookback,
                )
                ledger_payload = build_paper_ledger_report(
                    events,
                    symbol=args.symbol,
                    currency=args.currency,
                    horizon_samples=args.horizon_samples,
                    include_probes=args.include_probes,
                    candles=candles,
                    price_simulation=args.price_simulation,
                    allow_sample_close_fallback=not args.no_sample_close_fallback,
                )
                ledger_payload = {**ledger_payload, **candle_meta}
            payload = build_paper_performance_report(
                ledger_payload,
                initial_equity=args.initial_equity,
            )
            if args.output:
                output_path = _write_json_output(args.output, payload)
                payload = {**payload, "output": str(output_path)}
            if args.save:
                payload = _save_payload(mexc_settings, "nautilus_paper_performance", payload)
            print_json(payload)
        elif args.command == "nautilus-profit-hunt":
            payload = run_nautilus_profit_hunt(
                mexc_settings,
                client,
                symbol=args.symbol,
                currency=args.currency,
                lookback=args.lookback,
                horizon_samples=args.horizon_samples,
                candle_interval=args.candle_interval,
                candle_lookback=args.candle_lookback,
                initial_equity=args.initial_equity,
                confidence_thresholds=_parse_confidence_thresholds(args.confidence_thresholds),
                entry_metric_sweeps={
                    "minDepthImbalanceTop10": _parse_float_sweep(
                        args.min_depth_imbalance_sweep,
                        label="min-depth-imbalance-sweep",
                    ),
                    "maxSpreadBps": _parse_float_sweep(args.max_spread_bps_sweep, label="max-spread-bps-sweep"),
                    "maxAbsFundingRate": _parse_float_sweep(
                        args.max_abs_funding_rate_sweep,
                        label="max-abs-funding-rate-sweep",
                    ),
                    "minAvgRangeBps": _parse_float_sweep(args.min_avg_range_bps_sweep, label="min-avg-range-bps-sweep"),
                    "maxAvgRangeBps": _parse_float_sweep(args.max_avg_range_bps_sweep, label="max-avg-range-bps-sweep"),
                    "minLatestRangeBps": _parse_float_sweep(
                        args.min_latest_range_bps_sweep,
                        label="min-latest-range-bps-sweep",
                    ),
                    "maxLatestRangeBps": _parse_float_sweep(
                        args.max_latest_range_bps_sweep,
                        label="max-latest-range-bps-sweep",
                    ),
                },
                min_closed_count=args.min_closed_count,
                min_win_rate=args.min_win_rate,
                min_profit_factor=args.min_profit_factor,
                max_drawdown_pct=args.max_drawdown_pct,
            )
            if args.output:
                output_path = _write_json_output(args.output, payload)
                payload = {**payload, "output": str(output_path)}
            if args.save:
                payload = _save_payload(mexc_settings, "nautilus_profit_hunt", payload)
            print_json(payload)
        elif args.command == "pairs":
            response = client.contract_detail()
            pairs = parse_contract_pairs(response)
            if args.api_tradable_only:
                pairs = [pair for pair in pairs if pair.api_tradable]
            print_json(pair_summary(pairs))
        elif args.command == "ticker":
            print_json(client.ticker(args.symbol))
        elif args.command == "depth":
            print_json(client.depth(args.symbol, limit=args.limit))
        elif args.command == "index-price":
            print_json(client.index_price(args.symbol))
        elif args.command == "fair-price":
            print_json(client.fair_price(args.symbol))
        elif args.command == "funding-rate":
            print_json(client.funding_rate(args.symbol))
        elif args.command == "klines":
            if args.lookback <= 0:
                raise MexcApiError("lookback must be positive")
            if (args.start_time_ms is None) != (args.end_time_ms is None):
                raise MexcApiError("start-time-ms and end-time-ms must be provided together")
            end_ms = args.end_time_ms if args.end_time_ms is not None else int(time.time() * 1000)
            start_ms = (
                args.start_time_ms
                if args.start_time_ms is not None
                else end_ms - candle_interval_ms(args.interval) * args.lookback
            )
            response = client.klines(
                args.symbol,
                args.interval,
                start_time_ms=start_ms,
                end_time_ms=end_ms,
            )
            candles = parse_rest_klines(response, symbol=args.symbol, interval=args.interval)
            payload = {
                "symbol": args.symbol.upper(),
                "interval": args.interval,
                "success": bool(response.get("success")),
                "requestedStartTimeMs": start_ms,
                "requestedEndTimeMs": end_ms,
                "count": len(candles),
                "first": candles[0].to_dict() if candles else None,
                "last": candles[-1].to_dict() if candles else None,
            }
            if not args.summary_only:
                payload["candles"] = [candle.to_dict() for candle in candles[-args.lookback :]]
            print_json(payload)
        elif args.command == "network-check":
            print_json(client.network_check())
        elif args.command == "dns-check":
            print_json(client.dns_check())
        elif args.command == "readiness":
            payload = run_paper_readiness(
                mexc_settings,
                risk_settings,
                client,
                symbol=args.symbol,
                currency=args.currency,
                lookback=args.lookback,
                target_samples=args.target_samples,
                min_samples=args.min_samples,
                edge_horizon_samples=args.edge_horizon_samples,
                min_edge_evaluable=args.min_edge_evaluable,
                min_edge_win_rate=args.min_edge_win_rate,
                min_side_edge_evaluable=args.min_side_edge_evaluable,
                min_side_edge_win_rate=args.min_side_edge_win_rate,
                recovery_window_evaluable=args.recovery_window_evaluable,
                recovery_min_win_rate=args.recovery_min_win_rate,
                max_sample_age_seconds=args.max_sample_age_seconds,
                rolling_windows=args.rolling_windows,
                price_simulation=args.price_simulation,
                candle_interval=args.candle_interval,
                candle_lookback=args.candle_lookback,
                allow_sample_close_fallback=False
                if args.price_simulation == PRICE_SIMULATION_CANDLE_HIGH_LOW
                else not args.no_sample_close_fallback,
                performance_initial_equity=args.performance_initial_equity,
                performance_horizon_samples=args.performance_horizon_samples,
                performance_include_probes=args.performance_include_probes,
                min_performance_closed_count=args.min_performance_closed_count,
                min_performance_win_rate=args.min_performance_win_rate,
                min_profit_factor=args.min_profit_factor,
                max_drawdown_pct=args.max_drawdown_pct,
                max_consecutive_losses=args.max_consecutive_losses,
            )
            if args.output:
                output_path = _write_json_output(args.output, payload)
                payload = {**payload, "output": str(output_path)}
            print_json(payload)
        elif args.command == "smoke-readonly":
            print_json(
                {
                    "ping": client.ping(),
                    "contract": client.contract_detail(args.symbol),
                    "asset": client.asset(args.currency),
                    "positions": client.open_positions(args.symbol),
                }
            )
        elif args.command == "asset":
            print_json(client.asset(args.currency))
        elif args.command == "assets":
            print_json(client.all_assets())
        elif args.command == "positions":
            print_json(client.open_positions(args.symbol))
        elif args.command == "open-orders":
            print_json(client.current_orders(page_num=args.page_num, page_size=args.page_size))
        elif args.command == "history-orders":
            print_json(
                client.historical_orders(
                    symbol=args.symbol,
                    page_num=args.page_num,
                    page_size=args.page_size,
                    states=args.states,
                )
            )
        elif args.command == "order-deals":
            print_json(client.order_deals(args.symbol, page_num=args.page_num, page_size=args.page_size))
        elif args.command == "reconcile":
            if args.summary_only:
                payload = client.reconcile_summary(symbol=args.symbol, currency=args.currency)
            else:
                payload = client.reconcile_snapshot(symbol=args.symbol, currency=args.currency)
            if args.save:
                payload = _save_payload(mexc_settings, "reconcile_summary" if args.summary_only else "reconcile", payload)
            print_json(payload)
        elif args.command == "reconcile-engine":
            full_payload = run_reconciliation_engine(
                client,
                mexc_settings,
                symbol=args.symbol,
                currency=args.currency,
                ws_messages=args.ws_messages,
                history_limit=args.history_limit,
                deals_limit=args.deals_limit,
                include_raw=args.include_raw,
            )
            payload = summarize_reconciliation_report(full_payload) if args.summary_only else full_payload
            if args.output:
                output_path = _write_json_output(args.output, full_payload)
                payload = {**summarize_reconciliation_report(full_payload), "output": str(output_path)}
            if args.save:
                payload = _save_payload(mexc_settings, "reconcile_engine", payload)
            print_json(payload)
        elif args.command == "execution-reports":
            payload = build_execution_report_bundle(
                asset_response=client.asset(args.currency),
                positions_response=client.open_positions(args.symbol),
                open_orders_response=client.current_orders(page_num=1, page_size=100),
                history_orders_response=client.historical_orders(
                    symbol=args.symbol,
                    page_num=1,
                    page_size=args.history_limit,
                ),
                order_deals_response=client.order_deals(args.symbol, page_num=1, page_size=args.deals_limit),
                symbol=args.symbol,
                currency=args.currency,
                include_raw=args.include_raw,
            )
            if args.summary_only:
                payload = summarize_execution_report_bundle(payload)
            if args.output:
                output_path = _write_json_output(args.output, payload)
                payload = {**summarize_execution_report_bundle(payload), "output": str(output_path)}
            if args.save:
                payload = _save_payload(mexc_settings, "execution_reports", payload)
            print_json(payload)
        elif args.command == "store":
            store = StateStore(mexc_settings.state_db)
            if args.action == "stats":
                print_json(store.stats(event_type=args.event_type, symbol=args.symbol, currency=args.currency))
            else:
                print_json(
                    store.latest_events(
                        event_type=args.event_type,
                        limit=args.limit,
                        symbol=args.symbol,
                        currency=args.currency,
                    )
                )
        elif args.command == "safety-status":
            kill_path = Path(risk_settings.kill_switch_file)
            print_json(
                {
                    "credentialsPresent": bool(mexc_settings.access_key and mexc_settings.secret_key),
                    "baseUrl": mexc_settings.base_url,
                    "liveTradingEnabled": mexc_settings.live_trading_enabled,
                    "liveConfirmPresent": bool(mexc_settings.live_confirm),
                    "liveConfirmValid": mexc_settings.live_confirm == "I_UNDERSTAND_LIVE_MEXC_FUTURES_RISK",
                    "liveMutationPhaseEnabled": mexc_settings.live_mutation_phase_enabled,
                    "allowedSymbols": sorted(risk_settings.allowed_symbols),
                    "maxLeverage": risk_settings.max_leverage,
                    "maxOrderVol": risk_settings.max_order_vol,
                    "maxNotionalUsdt": risk_settings.max_notional_usdt,
                    "requireStopLoss": risk_settings.require_stop_loss,
                    "strategyAllowedSides": sorted(mexc_settings.strategy_allowed_sides or []),
                    "killSwitchFile": str(kill_path),
                    "killSwitchActive": kill_path.exists(),
                }
            )
        elif args.command == "audit-safety":
            print_json(audit_safety(mexc_settings, risk_settings, client))
        elif args.command == "kill-switch":
            kill_path = Path(risk_settings.kill_switch_file)
            if args.action == "on":
                kill_path.write_text("active\n", encoding="utf-8")
                print_json({"killSwitchActive": True, "killSwitchFile": str(kill_path)})
            elif args.action == "off":
                kill_path.unlink(missing_ok=True)
                print_json({"killSwitchActive": False, "killSwitchFile": str(kill_path)})
            else:
                print_json({"killSwitchActive": kill_path.exists(), "killSwitchFile": str(kill_path)})
        elif args.command == "ws-public":
            subscriptions = {
                "ticker": ticker_subscription,
                "deal": deal_subscription,
                "depth": depth_subscription,
            }
            ws_client = MexcWebSocketClient(mexc_settings)
            for message in ws_client.stream_public(subscriptions[args.channel](args.symbol), messages=args.messages):
                print_json(message)
        elif args.command == "ws-bridge":
            payload = run_ws_bridge(
                mexc_settings,
                channel=args.channel,
                symbol=args.symbol,
                messages=args.messages,
                include_raw=args.include_raw,
            )
            if args.save:
                payload = _save_payload(mexc_settings, "market_data_bridge", payload)
            print_json(payload)
        elif args.command == "ws-private":
            ws_client = MexcWebSocketClient(mexc_settings)
            for message in ws_client.stream_private(messages=args.messages):
                print_json(message)
        elif args.command == "ws-private-bridge":
            payload = run_ws_private_bridge(
                mexc_settings,
                messages=args.messages,
                include_raw=args.include_raw,
            )
            if args.save:
                payload = _save_payload(mexc_settings, "private_ws_bridge", payload)
            print_json(payload)
        elif args.command == "dry-run-order":
            order = OrderRequest(
                symbol=args.symbol,
                side=SIDE_MAP[args.side],
                order_type=ORDER_TYPE_MAP[args.order_type],
                open_type=OPEN_TYPE_MAP[args.open_type],
                price=args.price,
                vol=args.vol,
                contract_size=args.contract_size,
                leverage=args.leverage,
                external_oid=args.external_oid,
                stop_loss_price=args.stop_loss_price,
                take_profit_price=args.take_profit_price,
            )
            preflight = client.order_preflight(order, currency=args.currency)
            print_json(
                {
                    **preflight,
                    "dryRun": True,
                    "endpoint": "/api/v1/private/order/create",
                    "wouldSubmitLive": False,
                    "liveOrderSubmitted": False,
                    "note": "dry-run-order is read-only and never calls private/order/create",
                }
            )
        elif args.command == "preflight-order":
            order = OrderRequest(
                symbol=args.symbol,
                side=SIDE_MAP[args.side],
                order_type=ORDER_TYPE_MAP[args.order_type],
                open_type=OPEN_TYPE_MAP[args.open_type],
                price=args.price,
                vol=args.vol,
                leverage=args.leverage,
                stop_loss_price=args.stop_loss_price,
                take_profit_price=args.take_profit_price,
            )
            payload = client.order_preflight(order, currency=args.currency)
            if args.save:
                payload = _save_payload(mexc_settings, "preflight_order", payload)
            print_json(payload)
        elif args.command == "strategy-signal":
            payload = client.strategy_signal(
                symbol=args.symbol,
                currency=args.currency,
                leverage=args.leverage,
                max_notional_usdt=args.max_notional,
            )
            if args.save:
                payload = _save_payload(mexc_settings, "strategy_signal", payload)
            print_json(payload)
        elif args.command == "strategy-run":
            payload = run_strategy_loop(
                client,
                mexc_settings,
                symbol=args.symbol,
                currency=args.currency,
                leverage=args.leverage,
                max_notional_usdt=args.max_notional,
                iterations=args.iterations,
                interval=args.interval,
                save=args.save,
            )
            print_json(payload)
        elif args.command == "strategy-evaluate":
            if args.lookback <= 0:
                raise MexcApiError("lookback must be positive")
            store = StateStore(mexc_settings.state_db)
            events = store.latest_events(event_type="strategy_signal", limit=args.lookback)
            print_json(
                evaluate_strategy_events(
                    events,
                    symbol=args.symbol,
                    currency=args.currency,
                    min_consensus=args.min_consensus,
                    min_confidence=args.min_confidence,
                )
            )
    except (MexcApiError, RiskRejected, MexcWebSocketError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


def extract_or_raise_contract_rows(response: dict[str, object], symbol: str) -> list[dict[str, object]]:
    data = response.get("data")
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list) and data:
        return [row for row in data if isinstance(row, dict)]
    raise MexcApiError(f"contract not found for {symbol.upper()}")


def _write_json_output(path: str, payload: dict[str, object]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    output_path.chmod(0o600)
    return output_path


def audit_safety(
    mexc_settings: MexcSettings,
    risk_settings: RiskSettings,
    client: MexcFuturesClient,
) -> dict[str, object]:
    root = Path.cwd()
    env_file = root / ".env"
    env_mode = env_file.stat().st_mode & 0o777 if env_file.exists() else None
    kill_path = Path(risk_settings.kill_switch_file)
    network = client.network_check()
    checks_by_name = {check.get("name"): check for check in network["checks"]}
    secret_leaks = _scan_for_secret_leaks(
        root,
        secrets=[mexc_settings.access_key, mexc_settings.secret_key],
    )
    credentials_present = bool(mexc_settings.access_key and mexc_settings.secret_key)
    private_auth_probe = _private_readonly_auth_probe(
        client,
        currency="USDT",
        credentials_present=credentials_present,
    )

    findings: list[str] = []
    if not env_file.exists():
        findings.append(".env is missing")
    elif env_mode is not None and env_mode & 0o077:
        findings.append(".env permissions are too open")
    if not _gitignore_contains(root / ".gitignore", ".env"):
        findings.append(".gitignore does not explicitly ignore .env")
    if secret_leaks:
        findings.append("API credential appears outside .env")
    if credentials_present and not private_auth_probe["ok"]:
        findings.append("private read-only auth probe failed")
    if not mexc_settings.strategy_allowed_sides:
        findings.append("strategy allowed sides policy is empty or invalid")
    if mexc_settings.live_trading_enabled and mexc_settings.live_confirm != "I_UNDERSTAND_LIVE_MEXC_FUTURES_RISK":
        findings.append("live trading enabled without valid confirmation phrase")
    if (
        mexc_settings.live_trading_enabled
        and mexc_settings.live_confirm == "I_UNDERSTAND_LIVE_MEXC_FUTURES_RISK"
        and not mexc_settings.live_mutation_phase_enabled
    ):
        findings.append("live mutation phase is disabled")
    state_db = Path(mexc_settings.state_db)
    state_db_mode = state_db.stat().st_mode & 0o777 if state_db.exists() else None
    state_dir = state_db.parent
    state_dir_mode = state_dir.stat().st_mode & 0o777 if state_dir.exists() else None
    if state_db_mode is not None and state_db_mode & 0o077:
        findings.append("state DB permissions are too open")
    if state_dir_mode is not None and state_dir_mode & 0o077:
        findings.append("state DB directory permissions are too open")

    return {
        "ok": not findings,
        "findings": findings,
        "envFile": {
            "exists": env_file.exists(),
            "mode": oct(env_mode) if env_mode is not None else None,
            "private": bool(env_mode is not None and not env_mode & 0o077),
        },
        "gitignoreProtectsEnv": _gitignore_contains(root / ".gitignore", ".env"),
        "secretLeakPaths": secret_leaks,
        "credentialsPresent": credentials_present,
        "privateReadonlyAuth": private_auth_probe,
        "liveTradingEnabled": mexc_settings.live_trading_enabled,
        "liveConfirmValid": mexc_settings.live_confirm == "I_UNDERSTAND_LIVE_MEXC_FUTURES_RISK",
        "liveMutationPhaseEnabled": mexc_settings.live_mutation_phase_enabled,
        "killSwitchActive": kill_path.exists(),
        "useDohDns": mexc_settings.use_doh_dns,
        "strategyAllowedSides": sorted(mexc_settings.strategy_allowed_sides or []),
        "stateDb": mexc_settings.state_db,
        "stateDbFile": {
            "exists": state_db.exists(),
            "mode": oct(state_db_mode) if state_db_mode is not None else None,
            "private": bool(state_db_mode is not None and not state_db_mode & 0o077),
        },
        "stateDbDir": {
            "exists": state_dir.exists(),
            "mode": oct(state_dir_mode) if state_dir_mode is not None else None,
            "private": bool(state_dir_mode is not None and not state_dir_mode & 0o077),
        },
        "readyForReadonly": bool(checks_by_name.get("ping", {}).get("ok"))
        and credentials_present
        and bool(private_auth_probe["ok"]),
        "liveMutationFlagsArmed": (
            bool(checks_by_name.get("ping", {}).get("ok"))
            and credentials_present
            and bool(private_auth_probe["ok"])
            and mexc_settings.live_trading_enabled
            and mexc_settings.live_confirm == "I_UNDERSTAND_LIVE_MEXC_FUTURES_RISK"
            and mexc_settings.live_mutation_phase_enabled
            and not kill_path.exists()
        ),
        "readyForLive": False,
    }


def _private_readonly_auth_probe(
    client: MexcFuturesClient,
    *,
    currency: str,
    credentials_present: bool,
) -> dict[str, object]:
    if not credentials_present:
        return {
            "ok": False,
            "skipped": True,
            "endpoint": "GET /api/v1/private/account/asset/{currency}",
            "currency": currency.upper(),
            "reason": "credentials missing",
        }

    try:
        response = client.asset(currency)
    except Exception as exc:
        return {
            "ok": False,
            "skipped": False,
            "endpoint": "GET /api/v1/private/account/asset/{currency}",
            "currency": currency.upper(),
            "errorType": type(exc).__name__,
            "error": str(exc),
        }

    return {
        "ok": bool(response.get("success")),
        "skipped": False,
        "endpoint": "GET /api/v1/private/account/asset/{currency}",
        "currency": currency.upper(),
        "success": bool(response.get("success")),
        "code": response.get("code"),
        "message": response.get("message"),
    }


def run_paper_readiness(
    mexc_settings: MexcSettings,
    risk_settings: RiskSettings,
    client: MexcFuturesClient,
    *,
    symbol: str,
    currency: str,
    lookback: int,
    target_samples: int,
    min_samples: int,
    edge_horizon_samples: int,
    min_edge_evaluable: int,
    min_edge_win_rate: float,
    min_side_edge_evaluable: int,
    min_side_edge_win_rate: float,
    recovery_window_evaluable: int,
    recovery_min_win_rate: float,
    max_sample_age_seconds: int,
    rolling_windows: tuple[int, ...],
    price_simulation: str = PRICE_SIMULATION_SAMPLE_CLOSE,
    candle_interval: str = "1m",
    candle_lookback: int = 120,
    allow_sample_close_fallback: bool = True,
    performance_initial_equity: str | None = None,
    performance_horizon_samples: int | None = None,
    performance_include_probes: bool = False,
    min_performance_closed_count: int = 50,
    min_performance_win_rate: float = 0.55,
    min_profit_factor: float = 1.25,
    max_drawdown_pct: float = 0.02,
    max_consecutive_losses: int = 3,
) -> dict[str, object]:
    if lookback <= 0:
        raise MexcApiError("lookback must be positive")
    if target_samples <= 0:
        raise MexcApiError("target-samples must be positive")
    if min_samples <= 0:
        raise MexcApiError("min-samples must be positive")
    if edge_horizon_samples <= 0:
        raise MexcApiError("edge-horizon-samples must be positive")
    if min_edge_evaluable <= 0:
        raise MexcApiError("min-edge-evaluable must be positive")
    if not 0 <= min_edge_win_rate <= 1:
        raise MexcApiError("min-edge-win-rate must be between 0 and 1")
    if min_side_edge_evaluable <= 0:
        raise MexcApiError("min-side-edge-evaluable must be positive")
    if not 0 <= min_side_edge_win_rate <= 1:
        raise MexcApiError("min-side-edge-win-rate must be between 0 and 1")
    if recovery_window_evaluable <= 0:
        raise MexcApiError("recovery-window-evaluable must be positive")
    if not 0 <= recovery_min_win_rate <= 1:
        raise MexcApiError("recovery-min-win-rate must be between 0 and 1")
    if max_sample_age_seconds <= 0:
        raise MexcApiError("max-sample-age-seconds must be positive")
    if price_simulation not in {PRICE_SIMULATION_SAMPLE_CLOSE, PRICE_SIMULATION_CANDLE_HIGH_LOW}:
        raise MexcApiError("price-simulation is invalid")
    if candle_lookback <= 0:
        raise MexcApiError("candle-lookback must be positive")
    if performance_horizon_samples is not None and performance_horizon_samples <= 0:
        raise MexcApiError("performance-horizon-samples must be positive")
    if min_performance_closed_count <= 0:
        raise MexcApiError("min-performance-closed-count must be positive")
    if not 0 <= min_performance_win_rate <= 1:
        raise MexcApiError("min-performance-win-rate must be between 0 and 1")
    if min_profit_factor <= 0:
        raise MexcApiError("min-profit-factor must be positive")
    if max_drawdown_pct < 0:
        raise MexcApiError("max-drawdown-pct must be non-negative")
    if max_consecutive_losses < 0:
        raise MexcApiError("max-consecutive-losses must be non-negative")

    effective_min_edge_evaluable = max(min_edge_evaluable, 3)
    effective_min_edge_win_rate = max(min_edge_win_rate, 0.55)
    effective_min_side_edge_evaluable = max(min_side_edge_evaluable, 2)
    effective_min_side_edge_win_rate = max(min_side_edge_win_rate, 0.55)
    effective_recovery_window_evaluable = max(recovery_window_evaluable, 3)
    effective_recovery_min_win_rate = max(recovery_min_win_rate, 0.55)
    effective_edge_horizon_samples = max(edge_horizon_samples, 3)
    effective_performance_horizon_samples = max(
        performance_horizon_samples or effective_edge_horizon_samples,
        effective_edge_horizon_samples,
    )
    effective_max_sample_age_seconds = min(max_sample_age_seconds, 3600)
    effective_rolling_windows = tuple(sorted(set(rolling_windows) | set(DEFAULT_ROLLING_WINDOWS)))
    effective_price_simulation = PRICE_SIMULATION_CANDLE_HIGH_LOW
    effective_candle_lookback = max(candle_lookback, 240)
    effective_allow_sample_close_fallback = False

    safety = audit_safety(mexc_settings, risk_settings, client)
    store = StateStore(mexc_settings.state_db)
    events = store.latest_events(
        event_type="nautilus_paper_decision",
        limit=lookback,
        symbol=symbol,
        currency=currency,
    )
    candles, candle_meta = _price_simulation_candles(
        client,
        symbol=symbol,
        price_simulation=effective_price_simulation,
        candle_interval=candle_interval,
        candle_lookback=effective_candle_lookback,
    )
    audit = build_paper_audit_report(
        events,
        symbol=symbol,
        currency=currency,
        min_samples=min_samples,
        edge_horizon_samples=effective_edge_horizon_samples,
        min_edge_evaluable=effective_min_edge_evaluable,
        min_edge_win_rate=effective_min_edge_win_rate,
        min_side_edge_evaluable=effective_min_side_edge_evaluable,
        min_side_edge_win_rate=effective_min_side_edge_win_rate,
        policy_allowed_sides=mexc_settings.strategy_allowed_sides,
        recovery_window_evaluable=effective_recovery_window_evaluable,
        recovery_min_win_rate=effective_recovery_min_win_rate,
        max_sample_age_seconds=effective_max_sample_age_seconds,
        rolling_windows=effective_rolling_windows,
        candles=candles,
        price_simulation=effective_price_simulation,
        allow_sample_close_fallback=effective_allow_sample_close_fallback,
    )
    ledger = build_paper_ledger_report(
        events,
        symbol=symbol,
        currency=currency,
        horizon_samples=effective_performance_horizon_samples,
        include_probes=performance_include_probes,
        candles=candles,
        price_simulation=effective_price_simulation,
        allow_sample_close_fallback=effective_allow_sample_close_fallback,
    )
    performance = build_paper_performance_report(
        ledger,
        initial_equity=performance_initial_equity,
    )
    readiness = build_paper_readiness_report(
        audit_report=audit,
        safety_report=safety,
        target_sample_count=target_samples,
        performance_report=performance,
        min_performance_closed_count=min_performance_closed_count,
        min_performance_win_rate=min_performance_win_rate,
        min_profit_factor=min_profit_factor,
        max_drawdown_pct=max_drawdown_pct,
        max_consecutive_losses=max_consecutive_losses,
    )
    return {
        **readiness,
        "lookback": lookback,
        "strictReadinessConfig": {
            "configuredPriceSimulation": price_simulation,
            "effectivePriceSimulation": effective_price_simulation,
            "configuredCandleLookback": candle_lookback,
            "effectiveCandleLookback": effective_candle_lookback,
            "configuredAllowSampleCloseFallback": allow_sample_close_fallback,
            "effectiveAllowSampleCloseFallback": effective_allow_sample_close_fallback,
            "configuredEdgeHorizonSamples": edge_horizon_samples,
            "effectiveEdgeHorizonSamples": effective_edge_horizon_samples,
            "configuredPerformanceHorizonSamples": performance_horizon_samples,
            "effectivePerformanceHorizonSamples": effective_performance_horizon_samples,
            "effectivePerformanceIncludeProbes": performance_include_probes,
            "configuredMaxSampleAgeSeconds": max_sample_age_seconds,
            "effectiveMaxSampleAgeSeconds": effective_max_sample_age_seconds,
            "configuredMinEdgeEvaluable": min_edge_evaluable,
            "effectiveMinEdgeEvaluable": effective_min_edge_evaluable,
            "configuredMinEdgeWinRate": min_edge_win_rate,
            "effectiveMinEdgeWinRate": effective_min_edge_win_rate,
            "configuredMinSideEdgeEvaluable": min_side_edge_evaluable,
            "effectiveMinSideEdgeEvaluable": effective_min_side_edge_evaluable,
            "configuredMinSideEdgeWinRate": min_side_edge_win_rate,
            "effectiveMinSideEdgeWinRate": effective_min_side_edge_win_rate,
            "configuredRecoveryWindowEvaluable": recovery_window_evaluable,
            "effectiveRecoveryWindowEvaluable": effective_recovery_window_evaluable,
            "configuredRecoveryMinWinRate": recovery_min_win_rate,
            "effectiveRecoveryMinWinRate": effective_recovery_min_win_rate,
            "configuredRollingWindows": list(rolling_windows),
            "effectiveRollingWindows": list(effective_rolling_windows),
        },
        **candle_meta,
        "paperAudit": audit,
        "paperLedger": ledger,
        "paperPerformance": performance,
    }


def run_nautilus_profit_hunt(
    settings: MexcSettings,
    client: MexcFuturesClient,
    *,
    symbol: str,
    currency: str,
    lookback: int,
    horizon_samples: int,
    candle_interval: str,
    candle_lookback: int,
    initial_equity: str | None,
    confidence_thresholds: tuple[float, ...],
    entry_metric_sweeps: dict[str, tuple[float, ...]] | None,
    min_closed_count: int,
    min_win_rate: float,
    min_profit_factor: float,
    max_drawdown_pct: float,
) -> dict[str, object]:
    if lookback <= 0:
        raise MexcApiError("lookback must be positive")
    if horizon_samples <= 0:
        raise MexcApiError("horizon-samples must be positive")
    if candle_lookback <= 0:
        raise MexcApiError("candle-lookback must be positive")
    if min_closed_count <= 0:
        raise MexcApiError("min-closed-count must be positive")
    if min_win_rate < 0 or min_win_rate > 1:
        raise MexcApiError("min-win-rate must be between 0 and 1")
    if min_profit_factor <= 0:
        raise MexcApiError("min-profit-factor must be positive")
    if max_drawdown_pct < 0:
        raise MexcApiError("max-drawdown-pct must be non-negative")

    store = StateStore(settings.state_db)
    events = store.latest_events(
        event_type="nautilus_paper_decision",
        limit=lookback,
        symbol=symbol,
        currency=currency,
    )
    candles, candle_meta = _price_simulation_candles(
        client,
        symbol=symbol,
        price_simulation=PRICE_SIMULATION_CANDLE_HIGH_LOW,
        candle_interval=candle_interval,
        candle_lookback=max(candle_lookback, 240),
    )
    ledger = build_paper_ledger_report(
        events,
        symbol=symbol,
        currency=currency,
        horizon_samples=max(horizon_samples, 3),
        include_probes=False,
        candles=candles,
        price_simulation=PRICE_SIMULATION_CANDLE_HIGH_LOW,
        allow_sample_close_fallback=False,
    )
    report = build_profit_hunt_report(
        {**ledger, **candle_meta},
        initial_equity=initial_equity,
        confidence_thresholds=confidence_thresholds,
        entry_metric_sweeps=entry_metric_sweeps,
        min_closed_count=min_closed_count,
        min_win_rate=min_win_rate,
        min_profit_factor=min_profit_factor,
        max_drawdown_pct=max_drawdown_pct,
    )
    return {
        **report,
        "lookback": lookback,
        "horizonSamples": max(horizon_samples, 3),
        "sampleCount": ledger.get("sampleCount"),
        "ledgerOrderCount": ledger.get("orderCount"),
        "pricedClosedCount": ledger.get("pricedClosedCount"),
        "unpricedClosedCount": ledger.get("unpricedClosedCount"),
        "liveOrderSubmitted": False,
        **candle_meta,
    }


def _gitignore_contains(path: Path, pattern: str) -> bool:
    if not path.exists():
        return False
    return any(line.strip() == pattern for line in path.read_text(encoding="utf-8").splitlines())


def _scan_for_secret_leaks(root: Path, secrets: list[str]) -> list[str]:
    needles = [secret for secret in secrets if secret]
    if not needles:
        return []

    skip_dirs = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".venv",
        ".venv-nautilus",
        "venv",
    }
    skip_files = {".env"}
    leak_paths: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        if path.name in skip_files:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(needle in text for needle in needles):
            leak_paths.append(str(path.relative_to(root)))
    return leak_paths


def _save_payload(settings: MexcSettings, event_type: str, payload: dict[str, object]) -> dict[str, object]:
    store = StateStore(settings.state_db)
    event_id = store.save_event(event_type, payload)
    return {"savedEventId": event_id, "stateDb": settings.state_db, **payload}


def run_strategy_loop(
    client: MexcFuturesClient,
    settings: MexcSettings,
    *,
    symbol: str,
    currency: str,
    leverage: int,
    max_notional_usdt: float,
    iterations: int,
    interval: float,
    save: bool,
) -> dict[str, object]:
    if iterations <= 0:
        raise MexcApiError("iterations must be positive")
    if interval < 0:
        raise MexcApiError("interval must be non-negative")

    results: list[dict[str, object]] = []
    for index in range(iterations):
        payload = client.strategy_signal(
            symbol=symbol,
            currency=currency,
            leverage=leverage,
            max_notional_usdt=max_notional_usdt,
        )
        saved_event_id = None
        if save:
            saved = _save_payload(settings, "strategy_signal", payload)
            saved_event_id = saved["savedEventId"]
        signal = payload["signal"]["signal"]
        preflight = payload.get("preflight") or {}
        results.append(
            {
                "iteration": index + 1,
                "timestamp": payload["timestamp"],
                "symbol": payload["symbol"],
                "currency": payload["currency"],
                "side": signal["side"],
                "confidence": signal["confidence"],
                "preflightAllowed": preflight.get("preflightAllowed"),
                "savedEventId": saved_event_id,
            }
        )
        if index < iterations - 1:
            time.sleep(interval)

    return {
        "symbol": symbol.upper(),
        "currency": currency.upper(),
        "iterations": iterations,
        "interval": interval,
        "saved": save,
        "results": results,
    }


def run_ws_bridge(
    settings: MexcSettings,
    *,
    channel: str,
    symbol: str,
    messages: int,
    include_raw: bool,
) -> dict[str, object]:
    if messages <= 0:
        raise MexcApiError("messages must be positive")

    subscriptions = {
        "ticker": ticker_subscription,
        "deal": deal_subscription,
        "depth": depth_subscription,
    }
    ws_client = MexcWebSocketClient(settings)
    raw_messages: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    parser = MarketDataParser()

    for message in ws_client.stream_public(subscriptions[channel](symbol), messages=messages):
        raw_messages.append(message)
        events.extend(event.to_dict() for event in parser.parse_public_ws_message(message))

    event_counts: dict[str, int] = {}
    for event in events:
        event_type = str(event.get("eventType"))
        event_counts[event_type] = event_counts.get(event_type, 0) + 1

    payload: dict[str, object] = {
        "timestamp": int(time.time() * 1000),
        "symbol": symbol.upper(),
        "channel": channel,
        "requestedMessages": messages,
        "rawMessageCount": len(raw_messages),
        "eventCount": len(events),
        "eventCounts": event_counts,
        "events": events,
    }
    if include_raw:
        payload["rawMessages"] = raw_messages
    return payload


def run_ws_private_bridge(
    settings: MexcSettings,
    *,
    messages: int,
    include_raw: bool,
) -> dict[str, object]:
    if messages <= 0:
        raise MexcApiError("messages must be positive")

    ws_client = MexcWebSocketClient(settings)
    raw_messages: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    for message in ws_client.stream_private(messages=messages):
        raw_messages.append(message)
        events.append(parse_private_ws_message(message).to_dict(include_raw=include_raw))

    event_counts: dict[str, int] = {}
    for event in events:
        event_type = str(event.get("eventType"))
        event_counts[event_type] = event_counts.get(event_type, 0) + 1

    return {
        "timestamp": int(time.time() * 1000),
        "requestedMessages": messages,
        "rawMessageCount": len(raw_messages),
        "eventCount": len(events),
        "eventCounts": event_counts,
        "events": events,
    }


def run_reconciliation_engine(
    client: MexcFuturesClient,
    settings: MexcSettings,
    *,
    symbol: str,
    currency: str,
    ws_messages: int,
    history_limit: int,
    deals_limit: int,
    include_raw: bool,
) -> dict[str, object]:
    if ws_messages <= 0:
        raise MexcApiError("ws-messages must be positive")
    if history_limit <= 0:
        raise MexcApiError("history-limit must be positive")
    if deals_limit <= 0:
        raise MexcApiError("deals-limit must be positive")

    rest_snapshot = _build_readonly_rest_snapshot(
        client,
        symbol=symbol,
        currency=currency,
        history_limit=history_limit,
    )
    execution_bundle = build_execution_report_bundle(
        asset_response=rest_snapshot["singleAsset"],
        positions_response=rest_snapshot["positions"],
        open_orders_response=rest_snapshot["openOrders"],
        history_orders_response=rest_snapshot["recentOrders"],
        order_deals_response=client.order_deals(symbol, page_num=1, page_size=deals_limit),
        symbol=symbol,
        currency=currency,
        include_raw=include_raw,
    )
    private_ws_payload = run_ws_private_bridge(settings, messages=ws_messages, include_raw=include_raw)

    return build_reconciliation_report(
        rest_snapshot=rest_snapshot,
        execution_bundle=execution_bundle,
        private_ws_payload=private_ws_payload,
        symbol=symbol,
        currency=currency,
        include_raw=include_raw,
    )


def run_nautilus_adapter_check(
    client: MexcFuturesClient,
    settings: MexcSettings,
    *,
    symbol: str,
    currency: str,
    market_messages: int,
    private_ws_messages: int,
    history_limit: int,
    deals_limit: int,
    include_raw: bool,
) -> dict[str, object]:
    if market_messages <= 0:
        raise MexcApiError("market-messages must be positive")
    if private_ws_messages <= 0:
        raise MexcApiError("private-ws-messages must be positive")
    if history_limit <= 0:
        raise MexcApiError("history-limit must be positive")
    if deals_limit <= 0:
        raise MexcApiError("deals-limit must be positive")

    provider = MexcFuturesInstrumentProviderBoundary(client)
    data_boundary = MexcFuturesDataClientBoundary(settings)
    execution_boundary = MexcFuturesExecutionClientBoundary(client, settings)
    instrument_report = provider.load_symbols([symbol]).to_dict(
        include_specs=include_raw,
        include_symbols=True,
    )
    market_data_payloads = {
        channel: data_boundary.stream_public(
            channel=channel,
            symbol=symbol,
            messages=market_messages,
            include_raw=include_raw,
        )
        for channel in ("ticker", "deal", "depth")
    }
    reconciliation_report = execution_boundary.reconcile_startup(
        symbol=symbol,
        currency=currency,
        private_ws_messages=private_ws_messages,
        history_limit=history_limit,
        deals_limit=deals_limit,
        include_raw=include_raw,
    )

    return build_nautilus_adapter_readiness_report(
        instrument_report=instrument_report,
        market_data_payloads=market_data_payloads,
        reconciliation_report=reconciliation_report,
        upstream_reference=_upstream_reference_status(Path.cwd()),
        symbol=symbol,
        currency=currency,
        live_trading_enabled=settings.live_trading_enabled,
        include_raw=include_raw,
    )


def run_nautilus_runtime_harness(
    client: MexcFuturesClient,
    settings: MexcSettings,
    *,
    symbol: str,
    currency: str,
    market_messages: int,
    private_ws_messages: int,
    history_limit: int,
    deals_limit: int,
    include_raw: bool,
) -> dict[str, object]:
    if market_messages <= 0:
        raise MexcApiError("market-messages must be positive")
    if private_ws_messages <= 0:
        raise MexcApiError("private-ws-messages must be positive")
    if history_limit <= 0:
        raise MexcApiError("history-limit must be positive")
    if deals_limit <= 0:
        raise MexcApiError("deals-limit must be positive")

    root = Path.cwd()
    adapter_manifest = build_adapter_manifest(upstream_reference=_upstream_reference_status(root))
    adapter_check_report = run_nautilus_adapter_check(
        client,
        settings,
        symbol=symbol,
        currency=currency,
        market_messages=market_messages,
        private_ws_messages=private_ws_messages,
        history_limit=history_limit,
        deals_limit=deals_limit,
        include_raw=include_raw,
    )

    return build_runtime_harness_report(
        adapter_manifest=adapter_manifest,
        adapter_check_report=adapter_check_report,
        upstream_probe=probe_nautilus_runtime(root),
        sandbox_probe=probe_sandbox_nautilus_runtime(root),
        template_files=collect_template_files(root),
        boundary_methods=inspect_boundary_methods(),
        symbol=symbol,
        currency=currency,
        live_trading_enabled=settings.live_trading_enabled,
        include_raw=include_raw,
    )


def run_nautilus_runtime_wire(
    client: MexcFuturesClient,
    settings: MexcSettings,
    *,
    symbols: list[str],
    include_raw: bool,
) -> dict[str, object]:
    if not symbols:
        raise MexcApiError("at least one symbol is required")

    provider = MexcFuturesInstrumentProviderBoundary(client)
    instrument_report = provider.load_symbols(symbols).to_dict(
        include_specs=True,
        include_symbols=True,
    )
    specs = instrument_report.get("specs") if isinstance(instrument_report.get("specs"), list) else []
    sandbox_wire = wire_instrument_specs_to_sandbox(specs, Path.cwd())
    return build_runtime_wire_report(
        instrument_report=instrument_report,
        sandbox_wire=sandbox_wire,
        symbols=symbols,
        live_trading_enabled=settings.live_trading_enabled,
        include_raw=include_raw,
    )


def run_nautilus_market_wire(
    settings: MexcSettings,
    *,
    symbol: str,
    messages: int,
    include_raw: bool,
) -> dict[str, object]:
    if messages <= 0:
        raise MexcApiError("messages must be positive")

    data_boundary = MexcFuturesDataClientBoundary(settings)
    market_data_payloads = {
        channel: data_boundary.stream_public(
            channel=channel,
            symbol=symbol,
            messages=messages,
            include_raw=include_raw,
        )
        for channel in ("ticker", "deal", "depth")
    }
    sandbox_wire = wire_market_data_payloads_to_sandbox(market_data_payloads, Path.cwd())
    return build_market_runtime_wire_report(
        market_data_payloads=market_data_payloads,
        sandbox_wire=sandbox_wire,
        symbol=symbol,
        live_trading_enabled=settings.live_trading_enabled,
        include_raw=include_raw,
    )


def run_nautilus_execution_wire(
    client: MexcFuturesClient,
    settings: MexcSettings,
    *,
    symbol: str,
    currency: str,
    history_limit: int,
    deals_limit: int,
    include_raw: bool,
) -> dict[str, object]:
    if history_limit <= 0:
        raise MexcApiError("history-limit must be positive")
    if deals_limit <= 0:
        raise MexcApiError("deals-limit must be positive")

    execution_boundary = MexcFuturesExecutionClientBoundary(client, settings)
    execution_bundle = execution_boundary.generate_execution_reports(
        symbol=symbol,
        currency=currency,
        history_limit=history_limit,
        deals_limit=deals_limit,
        include_raw=include_raw,
    )
    sandbox_wire = wire_execution_reports_to_sandbox(execution_bundle, Path.cwd())
    return build_execution_runtime_wire_report(
        execution_bundle=execution_bundle,
        sandbox_wire=sandbox_wire,
        symbol=symbol,
        currency=currency,
        live_trading_enabled=settings.live_trading_enabled,
        include_raw=include_raw,
    )


def run_nautilus_state_handoff(
    client: MexcFuturesClient,
    settings: MexcSettings,
    *,
    symbol: str,
    currency: str,
    market_messages: int,
    history_limit: int,
    deals_limit: int,
    leverage: int,
    max_notional_usdt: float,
    include_raw: bool,
) -> dict[str, object]:
    if market_messages <= 0:
        raise MexcApiError("market-messages must be positive")
    if history_limit <= 0:
        raise MexcApiError("history-limit must be positive")
    if deals_limit <= 0:
        raise MexcApiError("deals-limit must be positive")
    if leverage <= 0:
        raise MexcApiError("leverage must be positive")
    if max_notional_usdt <= 0:
        raise MexcApiError("max-notional must be positive")

    instrument_wire = run_nautilus_runtime_wire(
        client,
        settings,
        symbols=normalize_symbols([symbol]),
        include_raw=include_raw,
    )
    market_wire = run_nautilus_market_wire(
        settings,
        symbol=symbol,
        messages=market_messages,
        include_raw=include_raw,
    )
    execution_wire = run_nautilus_execution_wire(
        client,
        settings,
        symbol=symbol,
        currency=currency,
        history_limit=history_limit,
        deals_limit=deals_limit,
        include_raw=include_raw,
    )
    strategy_signal = client.strategy_signal(
        symbol=symbol,
        currency=currency,
        leverage=leverage,
        max_notional_usdt=max_notional_usdt,
    )
    return build_nautilus_state_handoff_report(
        instrument_wire=instrument_wire,
        market_wire=market_wire,
        execution_wire=execution_wire,
        strategy_signal=strategy_signal,
        symbol=symbol,
        currency=currency,
        live_trading_enabled=settings.live_trading_enabled,
        include_raw=include_raw,
    )


def run_nautilus_paper_decision(
    client: MexcFuturesClient,
    settings: MexcSettings,
    *,
    symbol: str,
    currency: str,
    market_messages: int,
    history_limit: int,
    deals_limit: int,
    leverage: int,
    max_notional_usdt: float,
    min_confidence: float,
    max_margin_fraction: float,
    paper_equity_usdt: str | None,
    min_depth_imbalance: float,
    max_spread_bps: float,
    max_abs_funding_rate: float,
    max_market_age_seconds: int,
    quality_gate_lookback: int,
    quality_min_samples: int,
    quality_edge_horizon_samples: int,
    quality_min_edge_evaluable: int,
    quality_min_edge_win_rate: float,
    quality_min_side_edge_evaluable: int,
    quality_min_side_edge_win_rate: float,
    quality_recovery_window_evaluable: int,
    quality_recovery_min_win_rate: float,
    quality_max_sample_age_seconds: int,
    quality_rolling_windows: tuple[int, ...],
    trend_filter_enabled: bool,
    trend_interval: str,
    trend_lookback: int,
    trend_short_period: int,
    trend_long_period: int,
    trend_max_candle_age_seconds: int,
    volatility_filter_enabled: bool,
    volatility_interval: str,
    volatility_lookback: int,
    min_avg_range_bps: float | None,
    max_avg_range_bps: float | None,
    min_latest_range_bps: float | None,
    max_latest_range_bps: float | None,
    volatility_max_candle_age_seconds: int,
    include_raw: bool,
) -> dict[str, object]:
    if min_confidence < 0:
        raise MexcApiError("min-confidence must be non-negative")
    if min_confidence > 1:
        raise MexcApiError("min-confidence must be at most 1")
    if max_margin_fraction < 0:
        raise MexcApiError("max-margin-fraction must be non-negative")
    if max_margin_fraction > 1:
        raise MexcApiError("max-margin-fraction must be at most 1")
    paper_equity = _cli_decimal_or_none(paper_equity_usdt)
    if paper_equity_usdt is not None and paper_equity is None:
        raise MexcApiError("paper-equity must be numeric")
    if paper_equity_usdt is not None and paper_equity is not None and paper_equity <= 0:
        raise MexcApiError("paper-equity must be positive")
    if min_depth_imbalance < 0:
        raise MexcApiError("min-depth-imbalance must be non-negative")
    if max_spread_bps < 0:
        raise MexcApiError("max-spread-bps must be non-negative")
    if max_abs_funding_rate < 0:
        raise MexcApiError("max-abs-funding-rate must be non-negative")
    if max_market_age_seconds <= 0:
        raise MexcApiError("max-market-age-seconds must be positive")
    if quality_gate_lookback < 0:
        raise MexcApiError("quality-gate-lookback must be non-negative")
    if quality_min_samples <= 0:
        raise MexcApiError("quality-min-samples must be positive")
    if quality_edge_horizon_samples <= 0:
        raise MexcApiError("quality-edge-horizon-samples must be positive")
    if quality_min_edge_evaluable <= 0:
        raise MexcApiError("quality-min-edge-evaluable must be positive")
    if quality_min_edge_win_rate < 0:
        raise MexcApiError("quality-min-edge-win-rate must be non-negative")
    if quality_min_edge_win_rate > 1:
        raise MexcApiError("quality-min-edge-win-rate must be at most 1")
    if quality_min_side_edge_evaluable <= 0:
        raise MexcApiError("quality-min-side-edge-evaluable must be positive")
    if quality_min_side_edge_win_rate < 0:
        raise MexcApiError("quality-min-side-edge-win-rate must be non-negative")
    if quality_min_side_edge_win_rate > 1:
        raise MexcApiError("quality-min-side-edge-win-rate must be at most 1")
    if quality_recovery_window_evaluable <= 0:
        raise MexcApiError("quality-recovery-window-evaluable must be positive")
    if quality_recovery_min_win_rate < 0:
        raise MexcApiError("quality-recovery-min-win-rate must be non-negative")
    if quality_recovery_min_win_rate > 1:
        raise MexcApiError("quality-recovery-min-win-rate must be at most 1")
    if quality_max_sample_age_seconds <= 0:
        raise MexcApiError("quality-max-sample-age-seconds must be positive")
    if trend_filter_enabled:
        if trend_lookback <= 0:
            raise MexcApiError("trend-lookback must be positive")
        if trend_short_period <= 0:
            raise MexcApiError("trend-short-period must be positive")
        if trend_long_period <= 0:
            raise MexcApiError("trend-long-period must be positive")
        if trend_short_period >= trend_long_period:
            raise MexcApiError("trend-short-period must be less than trend-long-period")
        if trend_lookback < trend_long_period:
            raise MexcApiError("trend-lookback must be at least trend-long-period")
        if trend_max_candle_age_seconds <= 0:
            raise MexcApiError("trend-max-candle-age-seconds must be positive")
    if volatility_filter_enabled:
        _validate_volatility_filter_args(
            volatility_lookback=volatility_lookback,
            min_avg_range_bps=min_avg_range_bps,
            max_avg_range_bps=max_avg_range_bps,
            min_latest_range_bps=min_latest_range_bps,
            max_latest_range_bps=max_latest_range_bps,
            volatility_max_candle_age_seconds=volatility_max_candle_age_seconds,
        )

    state_handoff = run_nautilus_state_handoff(
        client,
        settings,
        symbol=symbol,
        currency=currency,
        market_messages=market_messages,
        history_limit=history_limit,
        deals_limit=deals_limit,
        leverage=leverage,
        max_notional_usdt=max_notional_usdt,
        include_raw=include_raw,
    )
    trend_report = None
    if trend_filter_enabled:
        trend_report = _build_rest_candle_trend_report(
            client,
            symbol=symbol,
            interval=trend_interval,
            lookback=trend_lookback,
            short_period=trend_short_period,
            long_period=trend_long_period,
            max_candle_age_seconds=trend_max_candle_age_seconds,
        )
    volatility_report = None
    if volatility_filter_enabled:
        volatility_report = _build_rest_candle_volatility_report(
            client,
            symbol=symbol,
            interval=volatility_interval,
            lookback=volatility_lookback,
            min_avg_range_bps=min_avg_range_bps,
            max_avg_range_bps=max_avg_range_bps,
            min_latest_range_bps=min_latest_range_bps,
            max_latest_range_bps=max_latest_range_bps,
            max_candle_age_seconds=volatility_max_candle_age_seconds,
        )
    report = build_paper_decision_report(
        state_handoff=state_handoff,
        min_confidence=min_confidence,
        max_margin_fraction=max_margin_fraction,
        min_depth_imbalance=min_depth_imbalance,
        max_spread_bps=max_spread_bps,
        max_abs_funding_rate=max_abs_funding_rate,
        max_market_age_seconds=max_market_age_seconds,
        trend_filter=trend_report,
        volatility_filter=volatility_report,
        paper_equity_usdt=paper_equity_usdt,
        include_raw=include_raw,
    )
    if quality_gate_lookback > 0:
        store = StateStore(settings.state_db)
        events = store.latest_events(
            event_type="nautilus_paper_decision",
            limit=quality_gate_lookback,
            symbol=symbol,
            currency=currency,
        )
        quality_candles, _quality_candle_meta = _price_simulation_candles(
            client,
            symbol=symbol,
            price_simulation=PRICE_SIMULATION_CANDLE_HIGH_LOW,
            candle_interval="1m",
            candle_lookback=240,
        )
        audit = build_paper_audit_report(
            events,
            symbol=symbol,
            currency=currency,
            min_samples=quality_min_samples,
            edge_horizon_samples=quality_edge_horizon_samples,
            min_edge_evaluable=quality_min_edge_evaluable,
            min_edge_win_rate=quality_min_edge_win_rate,
            min_side_edge_evaluable=quality_min_side_edge_evaluable,
            min_side_edge_win_rate=quality_min_side_edge_win_rate,
            policy_allowed_sides=settings.strategy_allowed_sides,
            recovery_window_evaluable=quality_recovery_window_evaluable,
            recovery_min_win_rate=quality_recovery_min_win_rate,
            max_sample_age_seconds=quality_max_sample_age_seconds,
            rolling_windows=quality_rolling_windows,
            candles=quality_candles,
            price_simulation=PRICE_SIMULATION_CANDLE_HIGH_LOW,
            allow_sample_close_fallback=False,
        )
        return apply_paper_side_quality_governor(report, audit)
    report["paperQualityGovernor"] = {"enabled": False, "reason": "quality-gate-lookback is 0"}
    return report


def _paper_loop_collection_progress(
    client: MexcFuturesClient,
    settings: MexcSettings,
    *,
    symbol: str,
    currency: str,
    target_samples: int | None,
    target_closed_trades: int | None,
    horizon_samples: int,
) -> dict[str, object]:
    store = StateStore(settings.state_db)
    raw_event_count = store.count_events(
        event_type="nautilus_paper_decision",
        symbol=symbol,
        currency=currency,
    )
    events = store.latest_events(
        event_type="nautilus_paper_decision",
        limit=max(raw_event_count, target_samples or 0, 1),
        symbol=symbol,
        currency=currency,
    )
    snapshot = build_paper_collection_snapshot(
        events,
        symbol=symbol,
        currency=currency,
        horizon_samples=horizon_samples,
        include_probes=True,
    )
    ledger: dict[str, object] = {}
    if target_closed_trades is not None:
        candles, _candle_meta = _price_simulation_candles(
            client,
            symbol=symbol,
            price_simulation=PRICE_SIMULATION_CANDLE_HIGH_LOW,
            candle_interval="1m",
            candle_lookback=240,
        )
        ledger = build_paper_ledger_report(
            events,
            symbol=symbol,
            currency=currency,
            horizon_samples=max(horizon_samples, 3),
            include_probes=False,
            candles=candles,
            price_simulation=PRICE_SIMULATION_CANDLE_HIGH_LOW,
            allow_sample_close_fallback=False,
        )
    current_count = int(snapshot["sampleCount"])
    closed_virtual_count = int(
        ledger.get("closedVirtualEntryCount", snapshot["closedVirtualEntryCount"])
    )
    open_virtual_count = int(ledger.get("openCount", snapshot["openVirtualEntryCount"]))
    unpriced_closed_count = int(ledger.get("unpricedClosedCount", 0))
    remaining_samples = max((target_samples or 0) - current_count, 0)
    remaining_closed = max((target_closed_trades or 0) - closed_virtual_count, 0)
    samples_ready = target_samples is None or current_count >= target_samples
    closed_ready = target_closed_trades is None or closed_virtual_count >= target_closed_trades
    no_open_entries = target_closed_trades is None or open_virtual_count == 0
    no_unpriced_entries = target_closed_trades is None or unpriced_closed_count == 0
    target_reached = samples_ready and closed_ready and no_open_entries and no_unpriced_entries
    return {
        "eventType": "nautilus_paper_decision",
        "currentCount": current_count,
        "beforeCount": current_count,
        "afterCount": current_count,
        "rawEventCount": raw_event_count,
        "rawBeforeCount": raw_event_count,
        "rawAfterCount": raw_event_count,
        "invalidEventCount": int(snapshot["invalidEventCount"]),
        "invalidBeforeCount": int(snapshot["invalidEventCount"]),
        "invalidAfterCount": int(snapshot["invalidEventCount"]),
        "targetSamples": target_samples,
        "targetClosedTrades": target_closed_trades,
        "closedVirtualEntryCount": closed_virtual_count,
        "closedVirtualEntryCountBefore": closed_virtual_count,
        "closedVirtualEntryCountAfter": closed_virtual_count,
        "openVirtualEntryCount": open_virtual_count,
        "openVirtualEntryCountBefore": open_virtual_count,
        "openVirtualEntryCountAfter": open_virtual_count,
        "closedProbeCount": int(snapshot["closedProbeCount"]),
        "closedProbeCountBefore": int(snapshot["closedProbeCount"]),
        "closedProbeCountAfter": int(snapshot["closedProbeCount"]),
        "openProbeCount": int(snapshot["openProbeCount"]),
        "openProbeCountBefore": int(snapshot["openProbeCount"]),
        "openProbeCountAfter": int(snapshot["openProbeCount"]),
        "unpricedClosedCount": unpriced_closed_count,
        "unpricedClosedCountBefore": unpriced_closed_count,
        "unpricedClosedCountAfter": unpriced_closed_count,
        "remainingSamples": remaining_samples,
        "remainingBefore": remaining_samples,
        "remainingAfter": remaining_samples,
        "remainingClosedTrades": remaining_closed,
        "remainingClosedTradesBefore": remaining_closed,
        "remainingClosedTradesAfter": remaining_closed,
        "targetReached": target_reached,
        "collectionSnapshot": snapshot,
        "collectionSnapshotBefore": snapshot,
        "collectionSnapshotAfter": snapshot,
        "paperLedger": ledger,
    }


def run_nautilus_paper_loop(
    client: MexcFuturesClient,
    settings: MexcSettings,
    *,
    symbol: str,
    currency: str,
    market_messages: int,
    history_limit: int,
    deals_limit: int,
    leverage: int,
    max_notional_usdt: float,
    min_confidence: float,
    max_margin_fraction: float,
    paper_equity_usdt: str | None,
    min_depth_imbalance: float,
    max_spread_bps: float,
    max_abs_funding_rate: float,
    max_market_age_seconds: int,
    quality_gate_lookback: int,
    quality_min_samples: int,
    quality_edge_horizon_samples: int,
    quality_min_edge_evaluable: int,
    quality_min_edge_win_rate: float,
    quality_min_side_edge_evaluable: int,
    quality_min_side_edge_win_rate: float,
    quality_recovery_window_evaluable: int,
    quality_recovery_min_win_rate: float,
    quality_max_sample_age_seconds: int,
    quality_rolling_windows: tuple[int, ...],
    trend_filter_enabled: bool,
    trend_interval: str,
    trend_lookback: int,
    trend_short_period: int,
    trend_long_period: int,
    trend_max_candle_age_seconds: int,
    volatility_filter_enabled: bool,
    volatility_interval: str,
    volatility_lookback: int,
    min_avg_range_bps: float | None,
    max_avg_range_bps: float | None,
    min_latest_range_bps: float | None,
    max_latest_range_bps: float | None,
    volatility_max_candle_age_seconds: int,
    iterations: int,
    interval: float,
    target_samples: int | None,
    target_closed_trades: int | None,
    include_raw: bool,
    save: bool,
) -> dict[str, object]:
    if iterations <= 0:
        raise MexcApiError("iterations must be positive")
    if interval < 0:
        raise MexcApiError("interval must be non-negative")
    if target_samples is not None and target_samples <= 0:
        raise MexcApiError("target-samples must be positive")
    if target_closed_trades is not None and target_closed_trades <= 0:
        raise MexcApiError("target-closed-trades must be positive")
    if (target_samples is not None or target_closed_trades is not None) and not save:
        raise MexcApiError("target collection requires --save so local progress can advance")

    requested_iterations = iterations
    sample_progress: dict[str, object] | None = None
    if target_samples is not None or target_closed_trades is not None:
        before_progress = _paper_loop_collection_progress(
            client,
            settings,
            symbol=symbol,
            currency=currency,
            target_samples=target_samples,
            target_closed_trades=target_closed_trades,
            horizon_samples=quality_edge_horizon_samples,
        )
        sample_progress = before_progress
        if before_progress["targetReached"]:
            iterations = 0
        elif target_closed_trades is None and target_samples is not None:
            iterations = min(iterations, int(before_progress["remainingSamples"]))

    results: list[dict[str, object]] = []
    for index in range(iterations):
        decision = run_nautilus_paper_decision(
            client,
            settings,
            symbol=symbol,
            currency=currency,
            market_messages=market_messages,
            history_limit=history_limit,
            deals_limit=deals_limit,
            leverage=leverage,
            max_notional_usdt=max_notional_usdt,
            min_confidence=min_confidence,
            max_margin_fraction=max_margin_fraction,
            paper_equity_usdt=paper_equity_usdt,
            min_depth_imbalance=min_depth_imbalance,
            max_spread_bps=max_spread_bps,
            max_abs_funding_rate=max_abs_funding_rate,
            max_market_age_seconds=max_market_age_seconds,
            quality_gate_lookback=quality_gate_lookback,
            quality_min_samples=quality_min_samples,
            quality_edge_horizon_samples=quality_edge_horizon_samples,
            quality_min_edge_evaluable=quality_min_edge_evaluable,
            quality_min_edge_win_rate=quality_min_edge_win_rate,
            quality_min_side_edge_evaluable=quality_min_side_edge_evaluable,
            quality_min_side_edge_win_rate=quality_min_side_edge_win_rate,
            quality_recovery_window_evaluable=quality_recovery_window_evaluable,
            quality_recovery_min_win_rate=quality_recovery_min_win_rate,
            quality_max_sample_age_seconds=quality_max_sample_age_seconds,
            quality_rolling_windows=quality_rolling_windows,
            trend_filter_enabled=trend_filter_enabled,
            trend_interval=trend_interval,
            trend_lookback=trend_lookback,
            trend_short_period=trend_short_period,
            trend_long_period=trend_long_period,
            trend_max_candle_age_seconds=trend_max_candle_age_seconds,
            volatility_filter_enabled=volatility_filter_enabled,
            volatility_interval=volatility_interval,
            volatility_lookback=volatility_lookback,
            min_avg_range_bps=min_avg_range_bps,
            max_avg_range_bps=max_avg_range_bps,
            min_latest_range_bps=min_latest_range_bps,
            max_latest_range_bps=max_latest_range_bps,
            volatility_max_candle_age_seconds=volatility_max_candle_age_seconds,
            include_raw=include_raw,
        )
        saved_event_id = None
        if save:
            saved = _save_payload(settings, "nautilus_paper_decision", decision)
            saved_event_id = saved["savedEventId"]
        results.append(
            {
                "iteration": index + 1,
                "timestamp": decision["timestamp"],
                "symbol": decision["symbol"],
                "currency": decision["currency"],
                "action": decision["action"],
                "wouldOpen": decision["wouldOpen"],
                "side": decision["side"],
                "confidence": decision["confidence"],
                "blockerCount": len(decision.get("blockers", [])),
                "volatilityFilter": decision.get("volatilityFilter", {}),
                "regimeFilter": decision.get("regimeFilter", {}),
                "qualityGovernorAction": (
                    decision.get("paperQualityGovernor", {}).get("action")
                    if isinstance(decision.get("paperQualityGovernor"), dict)
                    else None
                ),
                "savedEventId": saved_event_id,
            }
        )
        if index < iterations - 1:
            time.sleep(interval)

    if sample_progress is not None:
        after_progress = _paper_loop_collection_progress(
            client,
            settings,
            symbol=symbol,
            currency=currency,
            target_samples=target_samples,
            target_closed_trades=target_closed_trades,
            horizon_samples=quality_edge_horizon_samples,
        )
        sample_progress = {
            **sample_progress,
            "afterCount": after_progress["currentCount"],
            "rawAfterCount": after_progress["rawEventCount"],
            "invalidAfterCount": after_progress["invalidEventCount"],
            "closedVirtualEntryCountAfter": after_progress["closedVirtualEntryCount"],
            "openVirtualEntryCountAfter": after_progress["openVirtualEntryCount"],
            "closedProbeCountAfter": after_progress["closedProbeCount"],
            "openProbeCountAfter": after_progress["openProbeCount"],
            "unpricedClosedCountAfter": after_progress["unpricedClosedCount"],
            "remainingAfter": after_progress["remainingSamples"],
            "remainingClosedTradesAfter": after_progress["remainingClosedTrades"],
            "targetReached": after_progress["targetReached"],
            "collectionSnapshotAfter": after_progress["collectionSnapshot"],
        }

    return {
        "timestamp": int(time.time() * 1000),
        "mode": "paper-loop-read-only",
        "symbol": symbol.upper(),
        "currency": currency.upper(),
        "iterations": iterations,
        "requestedIterations": requested_iterations,
        "interval": interval,
        "targetSamples": target_samples,
        "targetClosedTrades": target_closed_trades,
        "sampleProgress": sample_progress,
        "saved": save,
        "liveOrderSubmitted": False,
        "wouldOpenCount": sum(1 for result in results if result["wouldOpen"]),
        "results": results,
    }


def _build_rest_candle_trend_report(
    client: MexcFuturesClient,
    *,
    symbol: str,
    interval: str,
    lookback: int,
    short_period: int,
    long_period: int,
    max_candle_age_seconds: int,
) -> dict[str, object]:
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - candle_interval_ms(interval) * lookback
    response = client.klines(symbol, interval, start_time_ms=start_ms, end_time_ms=end_ms)
    candles = parse_rest_klines(response, symbol=symbol, interval=interval)
    report = build_candle_trend_report(
        candles[-lookback:],
        short_period=short_period,
        long_period=long_period,
        max_candle_age_seconds=max_candle_age_seconds,
        now_ms=end_ms,
    )
    return {
        **report,
        "interval": interval,
        "lookback": lookback,
        "restSuccess": bool(response.get("success")),
        "requestedStartTimeMs": start_ms,
        "requestedEndTimeMs": end_ms,
    }


def _build_rest_candle_volatility_report(
    client: MexcFuturesClient,
    *,
    symbol: str,
    interval: str,
    lookback: int,
    min_avg_range_bps: float | None,
    max_avg_range_bps: float | None,
    min_latest_range_bps: float | None,
    max_latest_range_bps: float | None,
    max_candle_age_seconds: int,
) -> dict[str, object]:
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - candle_interval_ms(interval) * lookback
    response = client.klines(symbol, interval, start_time_ms=start_ms, end_time_ms=end_ms)
    candles = parse_rest_klines(response, symbol=symbol, interval=interval)
    report = build_candle_volatility_report(
        candles[-lookback:],
        min_avg_range_bps=min_avg_range_bps,
        max_avg_range_bps=max_avg_range_bps,
        min_latest_range_bps=min_latest_range_bps,
        max_latest_range_bps=max_latest_range_bps,
        max_candle_age_seconds=max_candle_age_seconds,
        now_ms=end_ms,
    )
    return {
        **report,
        "interval": interval,
        "lookback": lookback,
        "restSuccess": bool(response.get("success")),
        "requestedStartTimeMs": start_ms,
        "requestedEndTimeMs": end_ms,
    }


def _volatility_filter_requested(args: argparse.Namespace) -> bool:
    return bool(
        args.volatility_filter
        or args.min_avg_range_bps is not None
        or args.max_avg_range_bps is not None
        or args.min_latest_range_bps is not None
        or args.max_latest_range_bps is not None
    )


def _validate_volatility_filter_args(
    *,
    volatility_lookback: int,
    min_avg_range_bps: float | None,
    max_avg_range_bps: float | None,
    min_latest_range_bps: float | None,
    max_latest_range_bps: float | None,
    volatility_max_candle_age_seconds: int,
) -> None:
    if volatility_lookback <= 0:
        raise MexcApiError("volatility-lookback must be positive")
    if volatility_max_candle_age_seconds <= 0:
        raise MexcApiError("volatility-max-candle-age-seconds must be positive")
    for name, value in (
        ("min-avg-range-bps", min_avg_range_bps),
        ("max-avg-range-bps", max_avg_range_bps),
        ("min-latest-range-bps", min_latest_range_bps),
        ("max-latest-range-bps", max_latest_range_bps),
    ):
        if value is not None and value < 0:
            raise MexcApiError(f"{name} must be non-negative")
    if min_avg_range_bps is not None and max_avg_range_bps is not None and min_avg_range_bps > max_avg_range_bps:
        raise MexcApiError("min-avg-range-bps must be at most max-avg-range-bps")
    if (
        min_latest_range_bps is not None
        and max_latest_range_bps is not None
        and min_latest_range_bps > max_latest_range_bps
    ):
        raise MexcApiError("min-latest-range-bps must be at most max-latest-range-bps")


def _price_simulation_candles(
    client: MexcFuturesClient,
    *,
    symbol: str,
    price_simulation: str,
    candle_interval: str,
    candle_lookback: int,
) -> tuple[list[object], dict[str, object]]:
    if price_simulation != PRICE_SIMULATION_CANDLE_HIGH_LOW:
        return [], {}
    if candle_lookback <= 0:
        raise MexcApiError("candle-lookback must be positive")

    end_ms = int(time.time() * 1000)
    start_ms = end_ms - candle_interval_ms(candle_interval) * candle_lookback
    response = client.klines(symbol, candle_interval, start_time_ms=start_ms, end_time_ms=end_ms)
    candles = parse_rest_klines(response, symbol=symbol, interval=candle_interval)
    selected = candles[-candle_lookback:]
    return selected, {
        "requestedCandleStartTimeMs": start_ms,
        "requestedCandleEndTimeMs": end_ms,
        "restCandleSuccess": bool(response.get("success")),
    }


def _build_readonly_rest_snapshot(
    client: MexcFuturesClient,
    *,
    symbol: str,
    currency: str,
    history_limit: int,
) -> dict[str, object]:
    assets = client.all_assets()
    single_asset = client.asset(currency)
    global_positions = client.open_positions()
    positions = client.open_positions(symbol)
    open_orders = client.current_orders(page_num=1, page_size=100)
    historical_orders = client.historical_orders(symbol=symbol, page_num=1, page_size=history_limit)

    asset_rows = _mexc_rows(assets)
    global_position_rows = _mexc_rows(global_positions)
    position_rows = _mexc_rows(positions)
    open_order_rows = _mexc_rows(open_orders)
    target_open_order_rows = [row for row in open_order_rows if str(row.get("symbol") or "").upper() == symbol.upper()]
    recent_rows = _mexc_rows(historical_orders)

    return {
        "timestamp": int(time.time() * 1000),
        "symbol": symbol.upper(),
        "currency": currency.upper(),
        "summary": {
            "assetCount": len(asset_rows),
            "openPositionCount": len(position_rows),
            "openOrderCount": len(open_order_rows),
            "targetOpenPositionCount": len(position_rows),
            "targetOpenOrderCount": len(target_open_order_rows),
            "globalOpenPositionCount": len(global_position_rows),
            "globalOpenOrderCount": len(open_order_rows),
            "recentOrderCount": len(recent_rows),
            "singleAssetSuccess": bool(single_asset.get("success")),
        },
        "assets": assets,
        "singleAsset": single_asset,
        "globalPositions": global_positions,
        "positions": positions,
        "openOrders": open_orders,
        "recentOrders": historical_orders,
    }


def _mexc_rows(response: dict[str, object]) -> list[dict[str, object]]:
    data = response.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict) and isinstance(data.get("resultList"), list):
        return [row for row in data["resultList"] if isinstance(row, dict)]
    return []


def _cli_decimal_or_none(value: object) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _upstream_reference_status(root: Path) -> dict[str, object]:
    return {
        "nautilusTrader": _repo_reference(root / "upstream" / "nautilus_trader"),
        "hummingbot": _repo_reference(root / "upstream" / "hummingbot"),
    }


def _repo_reference(path: Path) -> dict[str, object]:
    exists = path.exists()
    return {
        "path": str(path),
        "exists": exists,
        "revision": _git_short_revision(path) if exists else None,
    }


def _git_short_revision(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    revision = result.stdout.strip()
    return revision or None


if __name__ == "__main__":
    raise SystemExit(main())
