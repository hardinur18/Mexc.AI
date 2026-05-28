from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from itertools import product
import time
from typing import Any, Iterable

from .performance import build_paper_performance_report


DEFAULT_CONFIDENCE_THRESHOLDS = (0.0, 0.65, 0.7, 0.75, 0.8)
PROFIT_HUNT_SIDES = ("all", "open-long", "open-short")
ENTRY_METRIC_SWEEP_KEYS = (
    "minDepthImbalanceTop10",
    "maxSpreadBps",
    "maxAbsFundingRate",
    "minAvgRangeBps",
    "maxAvgRangeBps",
    "minLatestRangeBps",
    "maxLatestRangeBps",
)
ENTRY_METRIC_REQUIRED_FIELDS = {
    "minDepthImbalanceTop10": "depthImbalanceTop10",
    "maxSpreadBps": "spreadBps",
    "maxAbsFundingRate": "fundingRate",
    "minAvgRangeBps": "avgRangeBps",
    "maxAvgRangeBps": "avgRangeBps",
    "minLatestRangeBps": "latestRangeBps",
    "maxLatestRangeBps": "latestRangeBps",
}


def build_profit_hunt_report(
    ledger_report: dict[str, Any],
    *,
    initial_equity: Any | None = None,
    confidence_thresholds: Iterable[float] = DEFAULT_CONFIDENCE_THRESHOLDS,
    min_closed_count: int = 50,
    min_win_rate: float = 0.55,
    min_profit_factor: float = 1.25,
    max_drawdown_pct: float = 0.02,
    entry_metric_sweeps: dict[str, Iterable[Any]] | None = None,
) -> dict[str, Any]:
    if min_closed_count <= 0:
        raise ValueError("min_closed_count must be positive")
    if not 0 <= min_win_rate <= 1:
        raise ValueError("min_win_rate must be between 0 and 1")
    if min_profit_factor <= 0:
        raise ValueError("min_profit_factor must be positive")
    if max_drawdown_pct < 0:
        raise ValueError("max_drawdown_pct must be non-negative")

    thresholds = _normalized_thresholds(confidence_thresholds)
    normalized_entry_metric_sweeps = _normalized_entry_metric_sweeps(entry_metric_sweeps)
    entry_metric_filters = _entry_metric_filter_variants(normalized_entry_metric_sweeps)
    candidates = []
    for entry_metrics_filter in entry_metric_filters:
        for side in PROFIT_HUNT_SIDES:
            for threshold in thresholds:
                candidate_ledger = _candidate_ledger(
                    ledger_report,
                    side=side,
                    min_confidence=threshold,
                    entry_metrics_filter=entry_metrics_filter,
                )
                performance = build_paper_performance_report(
                    candidate_ledger,
                    initial_equity=initial_equity,
                )
                candidates.append(
                    _candidate_report(
                        performance,
                        side=side,
                        min_confidence=threshold,
                        entry_metrics_filter=entry_metrics_filter,
                        filter_stats=candidate_ledger.get("profitHuntFilterStats"),
                        min_closed_count=min_closed_count,
                        min_win_rate=min_win_rate,
                        min_profit_factor=min_profit_factor,
                        max_drawdown_pct=max_drawdown_pct,
                    )
                )

    ranked = sorted(candidates, key=_candidate_rank_key, reverse=True)
    best = ranked[0] if ranked else None
    passing = [candidate for candidate in ranked if candidate["readyForPromotion"]]
    return {
        "timestamp": int(time.time() * 1000),
        "mode": "paper-profit-hunt-read-only",
        "symbol": ledger_report.get("symbol"),
        "currency": ledger_report.get("currency"),
        "inputLedgerMode": ledger_report.get("mode"),
        "priceSimulation": ledger_report.get("priceSimulation"),
        "priceSimulationFallback": ledger_report.get("priceSimulationFallback"),
        "candidateCount": len(ranked),
        "passingCandidateCount": len(passing),
        "readyForPromotion": bool(passing),
        "bestCandidate": best,
        "topCandidates": ranked[:5],
        "thresholds": {
            "confidenceThresholds": thresholds,
            "entryMetricSweeps": normalized_entry_metric_sweeps,
            "entryMetricFilterVariantCount": len(entry_metric_filters),
            "minClosedCount": min_closed_count,
            "minWinRate": min_win_rate,
            "minProfitFactor": min_profit_factor,
            "maxDrawdownPct": max_drawdown_pct,
            "requireEndingEquityAboveInitial": True,
            "requirePositiveExpectancy": True,
            "requireRecentEquityImproving": True,
            "requireNoOpenOrders": True,
            "requireNoUnpricedOrSkipped": True,
        },
        "recommendation": _profit_hunt_recommendation(best, passing),
        "liveOrderSubmitted": False,
    }


def _candidate_ledger(
    ledger_report: dict[str, Any],
    *,
    side: str,
    min_confidence: float,
    entry_metrics_filter: dict[str, float] | None = None,
) -> dict[str, Any]:
    active_entry_metrics_filter = entry_metrics_filter or {}
    orders = ledger_report.get("orders") if isinstance(ledger_report.get("orders"), list) else []
    source_orders = [
        order
        for order in orders
        if isinstance(order, dict) and str(order.get("sourceType") or "virtual-entry") == "virtual-entry"
    ]
    side_confidence_eligible = []
    selected = []
    missing_entry_metric_count = 0
    for order in source_orders:
        if side != "all" and str(order.get("side") or "") != side:
            continue
        if not _confidence_passes(order, min_confidence):
            continue
        side_confidence_eligible.append(order)
        passed_entry_metrics, missing_entry_metrics = _entry_metrics_passes(
            order,
            entry_metrics_filter=active_entry_metrics_filter,
        )
        if missing_entry_metrics:
            missing_entry_metric_count += 1
        if passed_entry_metrics:
            selected.append(deepcopy(order))

    filter_payload: dict[str, Any] = {
        "side": side,
        "minConfidence": min_confidence,
    }
    if active_entry_metrics_filter:
        filter_payload["entryMetrics"] = _serialize_entry_metrics_filter(active_entry_metrics_filter)

    return {
        **ledger_report,
        "orders": selected,
        "orderCount": len(selected),
        "sourceLedgerOrderCount": len(orders),
        "profitHuntFilter": filter_payload,
        "profitHuntFilterStats": {
            "sourceLedgerOrderCount": len(orders),
            "sourceVirtualEntryCount": len(source_orders),
            "sourceOpenCount": _order_open_count(source_orders),
            "sideConfidenceEligibleCount": len(side_confidence_eligible),
            "selectedOrderCount": len(selected),
            "selectedOpenCount": _order_open_count(selected),
            "filteredOutOpenCount": max(_order_open_count(source_orders) - _order_open_count(selected), 0),
            "entryMetricFilterEnabled": bool(active_entry_metrics_filter),
            "missingEntryMetricCount": missing_entry_metric_count,
        },
        "liveOrderSubmitted": False,
    }


def _candidate_report(
    performance: dict[str, Any],
    *,
    side: str,
    min_confidence: float,
    entry_metrics_filter: dict[str, float] | None,
    filter_stats: dict[str, Any] | None,
    min_closed_count: int,
    min_win_rate: float,
    min_profit_factor: float,
    max_drawdown_pct: float,
) -> dict[str, Any]:
    closed_count = _as_int(performance.get("closedCount")) or 0
    open_count = _as_int(performance.get("openCount")) or 0
    unpriced_count = _as_int(performance.get("unpricedClosedCount")) or 0
    skipped_count = _as_int(performance.get("skippedClosedCount")) or 0
    initial_equity = _decimal_or_none(performance.get("initialEquity"))
    ending_equity = _decimal_or_none(performance.get("endingEquity"))
    net_pnl = _decimal_or_none(performance.get("netPnlUsdt"))
    win_rate = _decimal_or_none(performance.get("winRate"))
    profit_factor = _decimal_or_none(performance.get("profitFactor"))
    max_drawdown = _decimal_or_none(performance.get("maxDrawdownPct"))
    expectancy = _decimal_or_none(performance.get("expectancy"))
    trend = performance.get("equityTrend") if isinstance(performance.get("equityTrend"), dict) else {}
    filter_payload: dict[str, Any] = {
        "side": side,
        "minConfidence": min_confidence,
    }
    if entry_metrics_filter:
        filter_payload["entryMetrics"] = _serialize_entry_metrics_filter(entry_metrics_filter)

    blockers = []
    passed_gates = 0
    total_gates = 9
    if closed_count >= min_closed_count:
        passed_gates += 1
    else:
        blockers.append(f"closed count {closed_count} below gate {min_closed_count}")
    if open_count == 0:
        passed_gates += 1
    else:
        blockers.append(f"open count {open_count} must be zero")
    if unpriced_count == 0 and skipped_count == 0:
        passed_gates += 1
    else:
        blockers.append(f"unpriced/skipped closed count {unpriced_count}/{skipped_count} must be zero")
    if initial_equity is not None and ending_equity is not None and ending_equity > initial_equity:
        passed_gates += 1
    else:
        blockers.append("ending equity is not above initial equity")
    if expectancy is not None and expectancy > 0:
        passed_gates += 1
    else:
        blockers.append("expectancy is not positive")
    if win_rate is not None and win_rate >= Decimal(str(min_win_rate)):
        passed_gates += 1
    else:
        blockers.append(f"win rate {performance.get('winRate')} below gate {min_win_rate}")
    no_loss_profit_factor = (
        profit_factor is None
        and closed_count > 0
        and net_pnl is not None
        and net_pnl > 0
        and win_rate == Decimal("1")
    )
    if no_loss_profit_factor or (profit_factor is not None and profit_factor >= Decimal(str(min_profit_factor))):
        passed_gates += 1
    else:
        blockers.append(f"profit factor {performance.get('profitFactor')} below gate {min_profit_factor}")
    if max_drawdown is not None and max_drawdown <= Decimal(str(max_drawdown_pct)):
        passed_gates += 1
    else:
        blockers.append(f"max drawdown pct {performance.get('maxDrawdownPct')} above gate {max_drawdown_pct}")
    if trend.get("recentEquityImproving") is True:
        passed_gates += 1
    else:
        blockers.append("recent equity trend is not improving")

    return {
        "filter": filter_payload,
        "source": filter_stats if isinstance(filter_stats, dict) else {},
        "readyForPromotion": not blockers,
        "passedGateCount": passed_gates,
        "totalGateCount": total_gates,
        "blockers": blockers,
        "score": _candidate_score(
            passed_gates=passed_gates,
            net_pnl=net_pnl,
            expectancy=expectancy,
            win_rate=win_rate,
            profit_factor=Decimal("5") if no_loss_profit_factor else profit_factor,
            max_drawdown=max_drawdown,
        ),
        "performance": {
            "closedCount": closed_count,
            "openCount": open_count,
            "unpricedClosedCount": unpriced_count,
            "skippedClosedCount": skipped_count,
            "initialEquity": performance.get("initialEquity"),
            "endingEquity": performance.get("endingEquity"),
            "netPnlUsdt": performance.get("netPnlUsdt"),
            "winRate": performance.get("winRate"),
            "profitFactor": performance.get("profitFactor"),
            "profitFactorNoLosses": no_loss_profit_factor,
            "maxDrawdownPct": performance.get("maxDrawdownPct"),
            "expectancy": performance.get("expectancy"),
            "consecutiveLosses": performance.get("consecutiveLosses"),
            "equityTrend": trend,
        },
        "liveOrderSubmitted": False,
    }


def _candidate_score(
    *,
    passed_gates: int,
    net_pnl: Decimal | None,
    expectancy: Decimal | None,
    win_rate: Decimal | None,
    profit_factor: Decimal | None,
    max_drawdown: Decimal | None,
) -> float:
    pnl_score = float(net_pnl or Decimal("0"))
    expectancy_score = float(expectancy or Decimal("0")) * 10
    win_score = float(win_rate or Decimal("0"))
    pf_score = min(float(profit_factor or Decimal("0")), 5.0) / 5
    drawdown_penalty = float(max_drawdown or Decimal("0"))
    return round(passed_gates + pnl_score + expectancy_score + win_score + pf_score - drawdown_penalty, 8)


def _candidate_rank_key(candidate: dict[str, Any]) -> tuple[float, float, float, float]:
    performance = candidate["performance"]
    return (
        1.0 if candidate["readyForPromotion"] else 0.0,
        float(candidate["score"]),
        float(_decimal_or_none(performance.get("netPnlUsdt")) or Decimal("0")),
        float(_decimal_or_none(performance.get("winRate")) or Decimal("0")),
    )


def _profit_hunt_recommendation(best: dict[str, Any] | None, passing: list[dict[str, Any]]) -> str:
    if not best:
        return "collect more paper samples before choosing a strategy variant"
    if passing:
        side = best["filter"]["side"]
        confidence = best["filter"]["minConfidence"]
        parts = [f"side={side}", f"minConfidence={confidence}"]
        entry_metrics = best["filter"].get("entryMetrics")
        if entry_metrics:
            parts.append(f"entryMetrics={entry_metrics}")
        return f"candidate passed local promotion gates: {', '.join(parts)}"
    return "no variant passed promotion gates; keep paper-only and collect/tune before changing live policy"


def _confidence_passes(order: dict[str, Any], threshold: float) -> bool:
    if threshold <= 0:
        return True
    confidence = _decimal_or_none(order.get("confidence"))
    return confidence is not None and confidence >= Decimal(str(threshold))


def _entry_metrics_passes(
    order: dict[str, Any],
    *,
    entry_metrics_filter: dict[str, float],
) -> tuple[bool, bool]:
    if not entry_metrics_filter:
        return True, False

    missing = _missing_entry_metrics(order, entry_metrics_filter)
    if missing:
        return False, True

    metrics = order.get("entryMetrics") if isinstance(order.get("entryMetrics"), dict) else {}
    side = str(order.get("side") or "")
    depth = _decimal_or_none(metrics.get("depthImbalanceTop10"))
    spread = _decimal_or_none(metrics.get("spreadBps"))
    funding = _decimal_or_none(metrics.get("fundingRate"))
    avg_range = _decimal_or_none(metrics.get("avgRangeBps"))
    latest_range = _decimal_or_none(metrics.get("latestRangeBps"))

    min_depth = _decimal_or_none(entry_metrics_filter.get("minDepthImbalanceTop10"))
    if min_depth is not None and not _depth_imbalance_passes(depth, side=side, threshold=min_depth):
        return False, False
    max_spread = _decimal_or_none(entry_metrics_filter.get("maxSpreadBps"))
    if max_spread is not None and (spread is None or spread > max_spread):
        return False, False
    max_abs_funding = _decimal_or_none(entry_metrics_filter.get("maxAbsFundingRate"))
    if max_abs_funding is not None and (funding is None or abs(funding) > max_abs_funding):
        return False, False
    min_avg_range = _decimal_or_none(entry_metrics_filter.get("minAvgRangeBps"))
    if min_avg_range is not None and (avg_range is None or avg_range < min_avg_range):
        return False, False
    max_avg_range = _decimal_or_none(entry_metrics_filter.get("maxAvgRangeBps"))
    if max_avg_range is not None and (avg_range is None or avg_range > max_avg_range):
        return False, False
    min_latest_range = _decimal_or_none(entry_metrics_filter.get("minLatestRangeBps"))
    if min_latest_range is not None and (latest_range is None or latest_range < min_latest_range):
        return False, False
    max_latest_range = _decimal_or_none(entry_metrics_filter.get("maxLatestRangeBps"))
    if max_latest_range is not None and (latest_range is None or latest_range > max_latest_range):
        return False, False
    return True, False


def _missing_entry_metrics(order: dict[str, Any], entry_metrics_filter: dict[str, float]) -> list[str]:
    metrics = order.get("entryMetrics") if isinstance(order.get("entryMetrics"), dict) else {}
    missing = []
    for filter_key, metric_key in ENTRY_METRIC_REQUIRED_FIELDS.items():
        if filter_key in entry_metrics_filter and _decimal_or_none(metrics.get(metric_key)) is None:
            missing.append(metric_key)
    return sorted(set(missing))


def _depth_imbalance_passes(depth: Decimal | None, *, side: str, threshold: Decimal) -> bool:
    if depth is None:
        return False
    if side == "open-long":
        return depth >= threshold
    if side == "open-short":
        return depth <= -threshold
    return abs(depth) >= threshold


def _order_open_count(orders: list[dict[str, Any]]) -> int:
    return sum(1 for order in orders if str(order.get("status") or "").upper() == "OPEN")


def _normalized_entry_metric_sweeps(
    entry_metric_sweeps: dict[str, Iterable[Any]] | None,
) -> dict[str, list[float]]:
    if not entry_metric_sweeps:
        return {}
    normalized: dict[str, list[float]] = {}
    for key in ENTRY_METRIC_SWEEP_KEYS:
        values = entry_metric_sweeps.get(key)
        numbers = _normalized_nonnegative_numbers(values)
        if numbers:
            normalized[key] = numbers
    unknown_keys = sorted(set(entry_metric_sweeps) - set(ENTRY_METRIC_SWEEP_KEYS))
    if unknown_keys:
        raise ValueError(f"unknown entry metric sweep keys: {', '.join(unknown_keys)}")
    return normalized


def _entry_metric_filter_variants(normalized_sweeps: dict[str, list[float]]) -> list[dict[str, float]]:
    if not normalized_sweeps:
        return [{}]
    keys = [key for key in ENTRY_METRIC_SWEEP_KEYS if key in normalized_sweeps]
    values = [normalized_sweeps[key] for key in keys]
    return [dict(zip(keys, combo)) for combo in product(*values)]


def _normalized_nonnegative_numbers(values: Iterable[Any] | None) -> list[float]:
    if values is None:
        return []
    raw_values = values.split(",") if isinstance(values, str) else list(values)
    normalized = []
    for raw in raw_values:
        if raw is None or str(raw).strip() == "":
            continue
        value = _decimal_or_none(raw)
        if value is None:
            raise ValueError("entry metric sweep values must be numbers")
        if value < 0:
            raise ValueError("entry metric sweep values must be non-negative")
        normalized.append(float(value))
    return sorted(set(normalized))


def _serialize_entry_metrics_filter(entry_metrics_filter: dict[str, float]) -> dict[str, float]:
    return {key: entry_metrics_filter[key] for key in ENTRY_METRIC_SWEEP_KEYS if key in entry_metrics_filter}


def _normalized_thresholds(values: Iterable[float]) -> list[float]:
    normalized = sorted({float(value) for value in values})
    return [value for value in normalized if 0 <= value <= 1]


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "DEFAULT_CONFIDENCE_THRESHOLDS",
    "ENTRY_METRIC_SWEEP_KEYS",
    "build_profit_hunt_report",
]
