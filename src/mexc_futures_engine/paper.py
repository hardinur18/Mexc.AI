from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import time
from typing import Any, Iterable


OPEN_SIDES = {"open-long", "open-short"}
DEFAULT_ROLLING_WINDOWS = (5, 10, 25, 50)
PRICE_SIMULATION_SAMPLE_CLOSE = "sample-close"
PRICE_SIMULATION_CANDLE_HIGH_LOW = "candle-high-low"
PRICE_SIMULATIONS = {PRICE_SIMULATION_SAMPLE_CLOSE, PRICE_SIMULATION_CANDLE_HIGH_LOW}


def build_paper_decision_report(
    *,
    state_handoff: dict[str, Any],
    min_confidence: float = 0.65,
    max_margin_fraction: float = 0.75,
    min_depth_imbalance: float = 0.12,
    max_spread_bps: float = 2.5,
    max_abs_funding_rate: float = 0.0005,
    max_market_age_seconds: int | None = None,
    trend_filter: dict[str, Any] | None = None,
    volatility_filter: dict[str, Any] | None = None,
    paper_equity_usdt: Any | None = None,
    include_raw: bool = False,
) -> dict[str, Any]:
    symbol = str(state_handoff.get("symbol") or "").upper()
    currency = str(state_handoff.get("currency") or "USDT").upper()
    state_cache = state_handoff.get("stateCache") if isinstance(state_handoff.get("stateCache"), dict) else {}
    strategy_handoff = (
        state_handoff.get("strategyHandoff") if isinstance(state_handoff.get("strategyHandoff"), dict) else {}
    )
    preview = (
        strategy_handoff.get("strategyPreview")
        if isinstance(strategy_handoff.get("strategyPreview"), dict)
        else {}
    )
    candidate = preview.get("candidateOrder") if isinstance(preview.get("candidateOrder"), dict) else {}
    metrics = preview.get("metrics") if isinstance(preview.get("metrics"), dict) else {}
    account = state_cache.get("account") if isinstance(state_cache.get("account"), dict) else {}
    balance = account.get("balance") if isinstance(account.get("balance"), dict) else {}
    instrument = state_cache.get("instrument") if isinstance(state_cache.get("instrument"), dict) else {}
    market = state_cache.get("market") if isinstance(state_cache.get("market"), dict) else {}

    blockers: list[str] = []
    warnings: list[str] = []
    if state_handoff.get("ok") is not True:
        blockers.append("state handoff is not ok")
        blockers.extend(str(reason) for reason in state_handoff.get("blockers") or [])
    if strategy_handoff.get("safeToEvaluateSignals") is not True:
        blockers.append("strategy handoff is not safe to evaluate")
    if strategy_handoff.get("safeToOpenNewPositionPreflight") is not True:
        blockers.append("strategy handoff is not safe for new-position preflight")
    if state_handoff.get("readyForLiveRuntime") is True:
        blockers.append("live runtime readiness unexpectedly true during paper audit")

    side = str(preview.get("side") or "hold")
    confidence = _decimal_or_none(preview.get("confidence"))
    if side not in OPEN_SIDES:
        blockers.append(f"strategy side is not actionable: {side}")
    if confidence is None:
        blockers.append("strategy confidence is missing")
    elif confidence < Decimal(str(min_confidence)):
        blockers.append(f"strategy confidence {confidence} is below {min_confidence}")
    preflight_reasons = [str(reason) for reason in preview.get("preflightReasons") or []]
    paper_equity = _decimal_or_none(paper_equity_usdt)
    paper_equity_enabled = paper_equity_usdt is not None
    if paper_equity_enabled and (paper_equity is None or paper_equity <= 0):
        blockers.append("paper equity is missing or non-positive")
    live_free_balance = _decimal_or_none(balance.get("free"))
    paper_free_balance = paper_equity if paper_equity_enabled else live_free_balance
    blocking_preflight_reasons = preflight_reasons
    if paper_equity_enabled:
        blocking_preflight_reasons = [
            reason for reason in preflight_reasons if not _is_balance_only_preflight_reason(reason)
        ]
        ignored_balance_reasons = [
            reason for reason in preflight_reasons if _is_balance_only_preflight_reason(reason)
        ]
        if ignored_balance_reasons:
            warnings.extend(
                f"live-balance preflight reason isolated from paper equity: {reason}"
                for reason in ignored_balance_reasons
            )
    if preview.get("preflightAllowed") is not True and blocking_preflight_reasons:
        blockers.append("strategy preflight is not allowed")
        blockers.extend(f"preflight: {reason}" for reason in blocking_preflight_reasons)
    elif preview.get("preflightAllowed") is not True and not paper_equity_enabled:
        blockers.append("strategy preflight is not allowed")

    paper_gates = _paper_gate_snapshot(
        metrics=metrics,
        side=side,
        min_depth_imbalance=min_depth_imbalance,
        max_spread_bps=max_spread_bps,
        max_abs_funding_rate=max_abs_funding_rate,
    )
    blockers.extend(paper_gates["blockers"])
    warnings.extend(paper_gates["warnings"])
    market_freshness = _market_freshness_snapshot(
        market=market,
        max_market_age_seconds=max_market_age_seconds,
        now_ms=int(time.time() * 1000),
    )
    blockers.extend(market_freshness["blockers"])
    warnings.extend(market_freshness["warnings"])
    trend_gate = _trend_gate_snapshot(trend_filter=trend_filter, side=side)
    blockers.extend(trend_gate["blockers"])
    warnings.extend(trend_gate["warnings"])
    volatility_gate = _volatility_gate_snapshot(volatility_filter=volatility_filter)
    blockers.extend(volatility_gate["blockers"])
    warnings.extend(volatility_gate["warnings"])

    price = _decimal_or_none(candidate.get("price"))
    vol = _decimal_or_none(candidate.get("vol"))
    contract_size = _decimal_or_none(candidate.get("contractSize") or instrument.get("multiplier"))
    leverage = _decimal_or_none(candidate.get("leverage"))
    taker_fee_rate = _decimal_or_none(instrument.get("takerFee")) or Decimal("0")
    if price is None or price <= 0:
        blockers.append("candidate price is missing or invalid")
    if vol is None or vol <= 0:
        blockers.append("candidate volume is missing or invalid")
    if contract_size is None or contract_size <= 0:
        blockers.append("contract size is missing or invalid")
    if leverage is None or leverage <= 0:
        blockers.append("candidate leverage is missing or invalid")
    if paper_free_balance is None:
        blockers.append("paper free balance is missing")

    notional = (price or Decimal("0")) * (vol or Decimal("0")) * (contract_size or Decimal("0"))
    required_margin = notional / leverage if leverage and leverage > 0 else Decimal("0")
    estimated_taker_fee = notional * taker_fee_rate
    max_margin = (paper_free_balance or Decimal("0")) * Decimal(str(max_margin_fraction))
    if paper_free_balance is not None and required_margin + estimated_taker_fee > paper_free_balance:
        blockers.append("paper required margin plus fee exceeds free balance")
    if max_margin_fraction > 0 and paper_free_balance is not None and required_margin > max_margin:
        blockers.append(f"paper required margin exceeds max margin fraction {max_margin_fraction}")

    open_position_count = _as_int(account.get("openPositionCount")) or 0
    active_order_count = _as_int(account.get("activeOrderCount")) or 0
    if open_position_count:
        blockers.append(f"existing open position count is {open_position_count}")
    if active_order_count:
        blockers.append(f"existing active order count is {active_order_count}")

    would_open = not blockers
    action = f"paper-{side}" if would_open else "hold"
    if not would_open:
        warnings.append("paper decision held; no virtual entry recorded")

    report: dict[str, Any] = {
        "timestamp": int(time.time() * 1000),
        "mode": "paper-trading-read-only",
        "symbol": symbol,
        "currency": currency,
        "ok": True,
        "wouldOpen": would_open,
        "action": action,
        "side": side,
        "confidence": _decimal_text(confidence),
        "minConfidence": min_confidence,
        "maxMarginFraction": max_margin_fraction,
        "paperGates": paper_gates,
        "liveOrderSubmitted": False,
        "virtualOrder": {
            "symbol": symbol,
            "side": side,
            "entryPrice": _decimal_text(price),
            "vol": _decimal_text(vol),
            "contractSize": _decimal_text(contract_size),
            "leverage": _decimal_text(leverage),
            "stopLossPrice": _decimal_text(_decimal_or_none(candidate.get("stopLossPrice"))),
            "takeProfitPrice": _decimal_text(_decimal_or_none(candidate.get("takeProfitPrice"))),
            "notional": _decimal_text(notional),
            "requiredMargin": _decimal_text(required_margin),
            "estimatedTakerFee": _decimal_text(estimated_taker_fee),
        }
        if would_open
        else None,
        "account": {
            "freeBalance": _decimal_text(paper_free_balance),
            "paperFreeBalance": _decimal_text(paper_free_balance),
            "liveFreeBalance": _decimal_text(live_free_balance),
            "paperEquityOverrideEnabled": paper_equity_enabled,
            "openPositionCount": open_position_count,
            "activeOrderCount": active_order_count,
        },
        "market": _market_snapshot(market),
        "marketFreshness": market_freshness,
        "trendFilter": trend_gate,
        "volatilityFilter": volatility_gate,
        "regimeFilter": _regime_gate_snapshot(volatility_gate),
        "blockers": blockers,
        "warnings": warnings,
        "nextPhase": "collect-paper-loop-samples-and-review-edge",
    }
    if include_raw:
        report["inputs"] = {"stateHandoff": state_handoff}
    return report


def summarize_paper_decision_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": report["timestamp"],
        "mode": report["mode"],
        "symbol": report["symbol"],
        "currency": report["currency"],
        "ok": report["ok"],
        "wouldOpen": report["wouldOpen"],
        "action": report["action"],
        "side": report["side"],
        "confidence": report["confidence"],
        "liveOrderSubmitted": report["liveOrderSubmitted"],
        "virtualOrder": report["virtualOrder"],
        "account": report["account"],
        "market": report["market"],
        "paperGates": report.get("paperGates", {}),
        "marketFreshness": report.get("marketFreshness", {}),
        "trendFilter": report.get("trendFilter", {}),
        "volatilityFilter": report.get("volatilityFilter", {}),
        "regimeFilter": report.get("regimeFilter", {}),
        "paperQualityGovernor": report.get("paperQualityGovernor", {}),
        "paperProbe": report.get("paperProbe"),
        "blockers": report["blockers"],
        "warnings": report["warnings"],
        "nextPhase": report["nextPhase"],
    }


def _is_balance_only_preflight_reason(reason: str) -> bool:
    normalized = reason.lower()
    return "available balance" in normalized and "below estimated margin" in normalized


def build_paper_readiness_report(
    *,
    audit_report: dict[str, Any],
    safety_report: dict[str, Any],
    performance_report: dict[str, Any] | None = None,
    target_sample_count: int = 100,
    min_performance_closed_count: int = 50,
    min_performance_win_rate: float = 0.55,
    min_profit_factor: float = 1.25,
    max_drawdown_pct: float = 0.02,
    max_consecutive_losses: int = 3,
) -> dict[str, Any]:
    if target_sample_count <= 0:
        raise ValueError("target_sample_count must be positive")
    if min_performance_closed_count <= 0:
        raise ValueError("min_performance_closed_count must be positive")
    if not 0 <= min_performance_win_rate <= 1:
        raise ValueError("min_performance_win_rate must be between 0 and 1")
    if min_profit_factor <= 0:
        raise ValueError("min_profit_factor must be positive")
    if max_drawdown_pct < 0:
        raise ValueError("max_drawdown_pct must be non-negative")
    if max_consecutive_losses < 0:
        raise ValueError("max_consecutive_losses must be non-negative")
    effective_target_sample_count = max(target_sample_count, 100)
    effective_min_performance_closed_count = max(min_performance_closed_count, 50)
    effective_min_performance_win_rate = max(min_performance_win_rate, 0.55)
    effective_min_profit_factor = max(min_profit_factor, 1.25)
    effective_max_drawdown_pct = min(max_drawdown_pct, 0.02)
    effective_max_consecutive_losses = min(max_consecutive_losses, 3)

    quality_gate = (
        audit_report.get("paperQualityGate")
        if isinstance(audit_report.get("paperQualityGate"), dict)
        else {}
    )
    policy_gate = (
        quality_gate.get("strategyPolicyQualityGate")
        if isinstance(quality_gate.get("strategyPolicyQualityGate"), dict)
        else {}
    )
    rolling_windows = (
        audit_report.get("rollingWindows")
        if isinstance(audit_report.get("rollingWindows"), dict)
        else {}
    )
    sample_count = _as_int(audit_report.get("sampleCount")) or 0
    sample_fraction = min(Decimal(sample_count) / Decimal(effective_target_sample_count), Decimal("1"))
    latest_age = _as_int(audit_report.get("latestSampleAgeSeconds"))
    max_age = _as_int(audit_report.get("maxSampleAgeSeconds"))
    sample_fresh = max_age is None or (latest_age is not None and latest_age <= max_age)
    performance_gate = _paper_performance_gate(
        performance_report,
        min_closed_count=effective_min_performance_closed_count,
        min_win_rate=effective_min_performance_win_rate,
        min_profit_factor=effective_min_profit_factor,
        max_drawdown_pct=effective_max_drawdown_pct,
        max_consecutive_losses=effective_max_consecutive_losses,
    )
    strict_quality_blockers = _strict_readiness_quality_blockers(quality_gate)
    strict_rolling_blockers = _strict_readiness_rolling_blockers(rolling_windows)
    paper_review_blockers = (
        audit_report.get("warnings") if isinstance(audit_report.get("warnings"), list) else []
    )
    price_simulation_quality = (
        quality_gate.get("priceSimulation") == PRICE_SIMULATION_CANDLE_HIGH_LOW
        and quality_gate.get("priceSimulationFallback") is None
    )
    if not price_simulation_quality:
        paper_review_blockers = [
            *paper_review_blockers,
            "strict readiness requires candle-high-low price simulation without sample-close fallback",
        ]
    live_lock_blockers = _paper_live_lock_blockers(safety_report)

    components = [
        _readiness_component(
            "readonly-safety",
            15,
            bool(safety_report.get("ok")) and bool(safety_report.get("readyForReadonly")),
            blockers=safety_report.get("findings") if isinstance(safety_report.get("findings"), list) else [],
        ),
        _readiness_component(
            "paper-live-lock",
            10,
            not live_lock_blockers,
            blockers=live_lock_blockers,
        ),
        _readiness_component(
            "paper-sample-volume",
            15,
            sample_count >= effective_target_sample_count,
            earned=Decimal("15") * sample_fraction,
            blockers=[f"sample count {sample_count} below target {effective_target_sample_count}"],
        ),
        _readiness_component(
            "paper-sample-freshness",
            10,
            sample_fresh,
            blockers=[f"latest sample age {latest_age}s above gate {max_age}s"],
        ),
        _readiness_component(
            "paper-reviewable",
            10,
            audit_report.get("readyForPaperReview") is True and price_simulation_quality,
            blockers=paper_review_blockers,
        ),
        _readiness_component(
            "global-edge-quality",
            10,
            quality_gate.get("readyForLiveCandidate") is True and not strict_quality_blockers,
            blockers=[
                *(quality_gate.get("blockers") if isinstance(quality_gate.get("blockers"), list) else []),
                *strict_quality_blockers,
            ],
        ),
        _readiness_component(
            "policy-side-quality",
            10,
            policy_gate.get("readyForCurrentStrategyLiveCandidate") is True,
            blockers=policy_gate.get("liveBlockers") if isinstance(policy_gate.get("liveBlockers"), list) else [],
        ),
        _readiness_component(
            "rolling-recent-quality",
            10,
            rolling_windows.get("readyForRecentQuality") is True and not strict_rolling_blockers,
            blockers=[
                *(rolling_windows.get("blockers") if isinstance(rolling_windows.get("blockers"), list) else []),
                *strict_rolling_blockers,
            ],
        ),
        _readiness_component(
            "paper-performance-quality",
            10,
            performance_gate.get("readyForLocalPaperPerformance") is True,
            blockers=performance_gate.get("blockers") if isinstance(performance_gate.get("blockers"), list) else [],
        ),
    ]
    score = sum((_decimal_or_none(component.get("earned")) or Decimal("0")) for component in components)
    blocking_components = [component for component in components if component["passed"] is not True]
    next_actions = _paper_readiness_next_actions(blocking_components)
    collection_progress = _paper_collection_progress(
        audit_report=audit_report,
        quality_gate=quality_gate,
        performance_gate=performance_gate,
        target_sample_count=effective_target_sample_count,
        target_closed_count=effective_min_performance_closed_count,
    )

    return {
        "timestamp": int(time.time() * 1000),
        "mode": "paper-local-readiness-read-only",
        "symbol": audit_report.get("symbol"),
        "currency": audit_report.get("currency"),
        "localPaperReadinessPercent": float(score.quantize(Decimal("0.01"))),
        "readinessProfile": "strict-local-paper",
        "targetSampleCount": effective_target_sample_count,
        "configuredTargetSampleCount": target_sample_count,
        "sampleCount": sample_count,
        "readyForLocalPaperStrategy": not blocking_components,
        "readyForLive": False,
        "liveOrderSubmitted": False,
        "components": components,
        "nextActions": next_actions,
        "collectionProgress": collection_progress,
        "auditSummary": {
            "readyForPaperReview": audit_report.get("readyForPaperReview"),
            "readyForLiveCandidate": quality_gate.get("readyForLiveCandidate"),
            "readyForCurrentStrategyLiveCandidate": policy_gate.get("readyForCurrentStrategyLiveCandidate"),
            "readyForRecentQuality": rolling_windows.get("readyForRecentQuality"),
            "edgeWinRate": quality_gate.get("edgeWinRate"),
            "edgeTotalRoughNetPnlUsdt": quality_gate.get("edgeTotalRoughNetPnlUsdt"),
            "policyAllowedSides": audit_report.get("policyAllowedSides"),
            "latestSampleAgeSeconds": audit_report.get("latestSampleAgeSeconds"),
        },
        "performanceSummary": performance_gate,
        "safetySummary": {
            "ok": safety_report.get("ok"),
            "readyForReadonly": safety_report.get("readyForReadonly"),
            "readyForLive": safety_report.get("readyForLive"),
            "liveTradingEnabled": safety_report.get("liveTradingEnabled"),
            "liveMutationPhaseEnabled": safety_report.get("liveMutationPhaseEnabled"),
            "liveMutationFlagsArmed": safety_report.get("liveMutationFlagsArmed"),
            "killSwitchActive": safety_report.get("killSwitchActive"),
            "strategyAllowedSides": safety_report.get("strategyAllowedSides"),
        },
    }


def build_paper_audit_report(
    events: list[dict[str, Any]],
    *,
    symbol: str,
    currency: str = "USDT",
    min_samples: int = 3,
    edge_horizon_samples: int = 1,
    min_edge_evaluable: int = 3,
    min_edge_win_rate: float = 0.55,
    min_side_edge_evaluable: int = 2,
    min_side_edge_win_rate: float | None = None,
    policy_allowed_sides: set[str] | None = None,
    recovery_window_evaluable: int = 3,
    recovery_min_win_rate: float | None = None,
    max_sample_age_seconds: int | None = None,
    rolling_windows: tuple[int, ...] | None = DEFAULT_ROLLING_WINDOWS,
    candles: list[Any] | None = None,
    price_simulation: str = PRICE_SIMULATION_SAMPLE_CLOSE,
    allow_sample_close_fallback: bool = True,
) -> dict[str, Any]:
    side_win_rate = min_edge_win_rate if min_side_edge_win_rate is None else min_side_edge_win_rate
    recovery_win_rate = side_win_rate if recovery_min_win_rate is None else recovery_min_win_rate
    if edge_horizon_samples <= 0:
        raise ValueError("edge_horizon_samples must be positive")
    if min_side_edge_evaluable <= 0:
        raise ValueError("min_side_edge_evaluable must be positive")
    if recovery_window_evaluable <= 0:
        raise ValueError("recovery_window_evaluable must be positive")
    if not 0 <= min_edge_win_rate <= 1:
        raise ValueError("min_edge_win_rate must be between 0 and 1")
    if not 0 <= side_win_rate <= 1:
        raise ValueError("min_side_edge_win_rate must be between 0 and 1")
    if not 0 <= recovery_win_rate <= 1:
        raise ValueError("recovery_min_win_rate must be between 0 and 1")
    if max_sample_age_seconds is not None and max_sample_age_seconds <= 0:
        raise ValueError("max_sample_age_seconds must be positive when set")
    if price_simulation not in PRICE_SIMULATIONS:
        raise ValueError(f"price_simulation must be one of: {', '.join(sorted(PRICE_SIMULATIONS))}")

    symbol = symbol.upper()
    currency = currency.upper()
    normalized_candles = _normalize_candles(candles)
    policy_sides = _normalize_policy_sides(policy_allowed_sides)
    normalized_rolling_windows = _normalize_rolling_windows(rolling_windows)
    samples: list[dict[str, Any]] = []
    for event in events:
        sample = _event_sample(event)
        if sample is None:
            continue
        if sample["symbol"] == symbol and sample["currency"] == currency:
            samples.append(sample)
    samples = _sort_samples_latest_first(samples)
    action_counts: dict[str, int] = {}
    blocker_counts: dict[str, int] = {}
    for sample in samples:
        action = str(sample.get("action") or "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1
        for blocker in sample.get("blockers") or []:
            blocker_counts[str(blocker)] = blocker_counts.get(str(blocker), 0) + 1

    latest = samples[0] if samples else None
    consecutive_would_open = 0
    consecutive_side = latest.get("side") if latest and latest.get("wouldOpen") else None
    for sample in samples:
        if not sample.get("wouldOpen") or sample.get("side") != consecutive_side:
            break
        consecutive_would_open += 1

    warnings: list[str] = []
    now_ms = int(time.time() * 1000)
    latest_sample_age_seconds = _sample_age_seconds(latest, now_ms=now_ms) if latest else None
    freshness_blockers = _freshness_blockers(
        latest,
        latest_sample_age_seconds=latest_sample_age_seconds,
        max_sample_age_seconds=max_sample_age_seconds,
    )
    if len(samples) < min_samples:
        warnings.append(f"only {len(samples)} paper sample(s); need {min_samples} for a useful audit")
    if latest and latest.get("wouldOpen"):
        warnings.append("latest paper sample would open virtually; review before any live work")
    warnings.extend(freshness_blockers)
    edge_preview = _edge_preview(
        samples,
        horizon_samples=edge_horizon_samples,
        candles=normalized_candles,
        price_simulation=price_simulation,
        allow_sample_close_fallback=allow_sample_close_fallback,
    )
    quality_gate = _paper_quality_gate(
        samples,
        symbol=symbol,
        currency=currency,
        edge_horizon_samples=edge_horizon_samples,
        min_samples=min_samples,
        min_edge_evaluable=min_edge_evaluable,
        min_edge_win_rate=min_edge_win_rate,
        min_side_edge_evaluable=min_side_edge_evaluable,
        min_side_edge_win_rate=side_win_rate,
        policy_allowed_sides=policy_sides,
        recovery_window_evaluable=recovery_window_evaluable,
        recovery_min_win_rate=recovery_win_rate,
        candles=normalized_candles,
        price_simulation=price_simulation,
        allow_sample_close_fallback=allow_sample_close_fallback,
    )
    _apply_quality_gate_external_blockers(quality_gate, freshness_blockers, label="paper audit freshness")
    rolling_window_reports = _rolling_quality_windows(
        samples,
        symbol=symbol,
        currency=currency,
        edge_horizon_samples=edge_horizon_samples,
        min_samples=min_samples,
        min_edge_evaluable=min_edge_evaluable,
        min_edge_win_rate=min_edge_win_rate,
        min_side_edge_evaluable=min_side_edge_evaluable,
        min_side_edge_win_rate=side_win_rate,
        policy_allowed_sides=policy_sides,
        recovery_window_evaluable=recovery_window_evaluable,
        recovery_min_win_rate=recovery_win_rate,
        rolling_windows=normalized_rolling_windows,
        external_blockers=freshness_blockers,
        candles=normalized_candles,
        price_simulation=price_simulation,
        allow_sample_close_fallback=allow_sample_close_fallback,
    )
    _apply_quality_gate_external_blockers(
        quality_gate,
        [str(reason) for reason in rolling_window_reports.get("blockers") or []],
        label="rolling quality",
    )

    return {
        "timestamp": int(time.time() * 1000),
        "mode": "paper-trading-audit-read-only",
        "symbol": symbol,
        "currency": currency,
        "sampleCount": len(samples),
        "minSamples": min_samples,
        "edgeHorizonSamples": edge_horizon_samples,
        "priceSimulation": price_simulation,
        "priceSimulationFallback": PRICE_SIMULATION_SAMPLE_CLOSE
        if price_simulation == PRICE_SIMULATION_CANDLE_HIGH_LOW and allow_sample_close_fallback
        else None,
        "candleCount": len(normalized_candles),
        "policyAllowedSides": sorted(policy_sides),
        "recoveryWindowEvaluable": recovery_window_evaluable,
        "maxSampleAgeSeconds": max_sample_age_seconds,
        "latestSampleAgeSeconds": latest_sample_age_seconds,
        "readyForPaperReview": len(samples) >= min_samples,
        "wouldOpenCount": sum(1 for sample in samples if sample.get("wouldOpen")),
        "holdCount": sum(1 for sample in samples if not sample.get("wouldOpen")),
        "actionCounts": action_counts,
        "blockerCounts": blocker_counts,
        "latestSample": latest,
        "consecutiveWouldOpen": consecutive_would_open,
        "consecutiveSide": consecutive_side,
        "edgePreview": edge_preview,
        "paperQualityGate": quality_gate,
        "rollingWindows": rolling_window_reports,
        "liveOrderSubmitted": False,
        "warnings": warnings,
        "nextPhase": "collect-more-paper-samples-and-tighten-signal-quality-gates",
    }


def apply_paper_side_quality_governor(
    decision_report: dict[str, Any],
    audit_report: dict[str, Any],
) -> dict[str, Any]:
    report = deepcopy(decision_report)
    side = str(report.get("side") or "")
    governor: dict[str, Any] = {
        "enabled": True,
        "auditTimestamp": audit_report.get("timestamp"),
        "side": side,
        "action": "not-applicable",
        "paused": False,
        "reasons": [],
    }
    if report.get("wouldOpen") is not True or side not in OPEN_SIDES:
        report["paperQualityGovernor"] = governor
        return report

    quality_gate = audit_report.get("paperQualityGate") if isinstance(audit_report.get("paperQualityGate"), dict) else {}
    governor["priceSimulation"] = quality_gate.get("priceSimulation")
    governor["priceSimulationFallback"] = quality_gate.get("priceSimulationFallback")
    governor["candleCount"] = quality_gate.get("candleCount")
    side_gates = quality_gate.get("sideGates") if isinstance(quality_gate.get("sideGates"), dict) else {}
    side_gate = side_gates.get(side) if isinstance(side_gates.get(side), dict) else None
    if side_gate is None:
        governor["action"] = "allow-missing-side-gate"
        governor["reasons"] = [f"no side quality gate found for {side}"]
        report.setdefault("warnings", []).append(f"paper side quality governor has no side gate for {side}")
        report["paperQualityGovernor"] = governor
        return report

    original_virtual_order = deepcopy(report.get("virtualOrder")) if isinstance(report.get("virtualOrder"), dict) else None
    policy_gate = (
        quality_gate.get("strategyPolicyQualityGate")
        if isinstance(quality_gate.get("strategyPolicyQualityGate"), dict)
        else {}
    )

    if side_gate.get("pauseNewPaperEntries") is not True:
        policy_allowed_sides = (
            policy_gate.get("allowedSides") if isinstance(policy_gate.get("allowedSides"), list) else []
        )
        if side in policy_allowed_sides and policy_gate.get("readyForCurrentStrategyPaperCandidate") is not True:
            pause_reasons = [str(reason) for reason in policy_gate.get("blockers") or []]
            governor.update(
                {
                    "action": "pause-policy",
                    "paused": True,
                    "reasons": pause_reasons,
                    "sideGate": side_gate,
                    "policyGate": policy_gate,
                }
            )
            report["wouldOpen"] = False
            report["action"] = "hold"
            report["virtualOrder"] = None
            report["paperProbe"] = _paper_probe(
                side=side,
                virtual_order=original_virtual_order,
                reason="paper policy quality governor paused candidate",
            )
            report.setdefault("blockers", []).extend(
                f"paper policy quality paused {side}: {reason}" for reason in pause_reasons
            )
            report.setdefault("warnings", []).append(
                f"paper policy quality governor paused {side}; no virtual entry recorded"
            )
            report["paperQualityGovernor"] = governor
            report["liveOrderSubmitted"] = False
            return report
        governor["action"] = "allow"
        governor["sideGate"] = side_gate
        governor["policyGate"] = policy_gate
        report["paperQualityGovernor"] = governor
        return report

    pause_reasons = [str(reason) for reason in side_gate.get("paperPauseReasons") or []]
    governor.update(
        {
            "action": "pause-side",
            "paused": True,
            "reasons": pause_reasons,
            "sideGate": side_gate,
        }
    )
    report["wouldOpen"] = False
    report["action"] = "hold"
    report["virtualOrder"] = None
    report["paperProbe"] = _paper_probe(
        side=side,
        virtual_order=original_virtual_order,
        reason="paper side quality governor paused candidate",
    )
    report.setdefault("blockers", []).extend(f"paper side quality paused {side}: {reason}" for reason in pause_reasons)
    report.setdefault("warnings", []).append(f"paper side quality governor paused {side}; no virtual entry recorded")
    report["paperQualityGovernor"] = governor
    report["liveOrderSubmitted"] = False
    return report


def _paper_probe(*, side: str, virtual_order: dict[str, Any] | None, reason: str) -> dict[str, Any] | None:
    if not virtual_order:
        return None
    return {
        "enabled": True,
        "side": side,
        "reason": reason,
        "eligibleForRecoveryStats": True,
        "virtualOrder": virtual_order,
        "liveOrderSubmitted": False,
    }


def build_paper_edge_report(
    events: list[dict[str, Any]],
    *,
    symbol: str,
    currency: str = "USDT",
    horizon_samples: int = 1,
    min_evaluable: int = 3,
    candles: list[Any] | None = None,
    price_simulation: str = PRICE_SIMULATION_SAMPLE_CLOSE,
    allow_sample_close_fallback: bool = True,
) -> dict[str, Any]:
    if horizon_samples <= 0:
        raise ValueError("horizon_samples must be positive")
    if min_evaluable <= 0:
        raise ValueError("min_evaluable must be positive")
    if price_simulation not in PRICE_SIMULATIONS:
        raise ValueError(f"price_simulation must be one of: {', '.join(sorted(PRICE_SIMULATIONS))}")

    symbol = symbol.upper()
    currency = currency.upper()
    normalized_candles = _normalize_candles(candles)
    samples = []
    for event in events:
        sample = _event_sample(event)
        if sample is None:
            continue
        if sample["symbol"] == symbol and sample["currency"] == currency:
            samples.append(sample)
    chronological = _sort_samples_chronological(samples)

    evaluations: list[dict[str, Any]] = []
    pending = 0
    skipped = 0
    for index, sample in enumerate(chronological):
        if not sample.get("wouldOpen"):
            continue
        future_samples = chronological[index + 1 : index + 1 + horizon_samples]
        if len(future_samples) < horizon_samples:
            pending += 1
            continue
        evaluation = _evaluate_edge(
            sample,
            future_samples,
            candles=normalized_candles,
            price_simulation=price_simulation,
            allow_sample_close_fallback=allow_sample_close_fallback,
        )
        if evaluation is None:
            skipped += 1
            continue
        evaluations.append(evaluation)

    wins = sum(1 for item in evaluations if item["outcome"] == "win")
    losses = sum(1 for item in evaluations if item["outcome"] == "loss")
    flats = sum(1 for item in evaluations if item["outcome"] == "flat")
    net_values = [_decimal_or_none(item.get("roughNetPnlUsdt")) or Decimal("0") for item in evaluations]
    bps_values = [_decimal_or_none(item.get("moveBps")) or Decimal("0") for item in evaluations]
    warnings: list[str] = []
    if len(evaluations) < min_evaluable:
        warnings.append(f"only {len(evaluations)} evaluable paper entry sample(s); need {min_evaluable}")
    if pending:
        warnings.append(f"{pending} paper entry sample(s) still waiting for future market sample")
    if skipped:
        warnings.append(f"{skipped} paper entry sample(s) skipped due missing market/virtual order fields")

    return {
        "timestamp": int(time.time() * 1000),
        "mode": "paper-edge-review-read-only",
        "symbol": symbol,
        "currency": currency,
        "horizonSamples": horizon_samples,
        "priceSimulation": price_simulation,
        "priceSimulationFallback": PRICE_SIMULATION_SAMPLE_CLOSE
        if price_simulation == PRICE_SIMULATION_CANDLE_HIGH_LOW and allow_sample_close_fallback
        else None,
        "candleCount": len(normalized_candles),
        "sampleCount": len(samples),
        "evaluableCount": len(evaluations),
        "pendingCount": pending,
        "skippedCount": skipped,
        "minEvaluable": min_evaluable,
        "readyForEdgeReview": len(evaluations) >= min_evaluable,
        "winCount": wins,
        "lossCount": losses,
        "flatCount": flats,
        "winRate": round(wins / len(evaluations), 6) if evaluations else None,
        "avgMoveBps": _decimal_text(sum(bps_values, Decimal("0")) / len(bps_values)) if bps_values else None,
        "totalRoughNetPnlUsdt": _decimal_text(sum(net_values, Decimal("0"))) if net_values else "0",
        "sideStats": _edge_side_stats(evaluations),
        "evaluations": evaluations,
        "liveOrderSubmitted": False,
        "warnings": warnings,
        "nextPhase": "collect-more-paper-samples-or-tighten-signal-gates",
    }


def build_paper_ledger_report(
    events: list[dict[str, Any]],
    *,
    symbol: str,
    currency: str = "USDT",
    horizon_samples: int = 3,
    include_probes: bool = False,
    candles: list[Any] | None = None,
    price_simulation: str = PRICE_SIMULATION_SAMPLE_CLOSE,
    allow_sample_close_fallback: bool = True,
) -> dict[str, Any]:
    if horizon_samples <= 0:
        raise ValueError("horizon_samples must be positive")
    if price_simulation not in PRICE_SIMULATIONS:
        raise ValueError(f"price_simulation must be one of: {', '.join(sorted(PRICE_SIMULATIONS))}")

    symbol = symbol.upper()
    currency = currency.upper()
    normalized_candles = _normalize_candles(candles)
    samples: list[dict[str, Any]] = []
    for event in events:
        sample = _event_sample(event)
        if sample is None:
            continue
        if sample["symbol"] == symbol and sample["currency"] == currency:
            samples.append(sample)
    chronological = _sort_samples_chronological(samples)

    orders: list[dict[str, Any]] = []
    for index, sample in enumerate(chronological):
        entry_sample = _ledger_entry_sample(sample, include_probes=include_probes)
        if entry_sample is None:
            continue
        future_samples = chronological[index + 1 : index + 1 + horizon_samples]
        orders.append(
            _ledger_order(
                entry_sample,
                future_samples=future_samples,
                horizon_samples=horizon_samples,
                candles=normalized_candles,
                price_simulation=price_simulation,
                allow_sample_close_fallback=allow_sample_close_fallback,
            )
        )

    status_counts = _count_by_key(orders, "status")
    source_counts = _count_by_key(orders, "sourceType")
    priced_closed_orders = [order for order in orders if _is_priced_closed_order(order)]
    unpriced_closed_orders = [order for order in orders if _is_unpriced_closed_order(order)]
    pnl_values = [_order_priced_pnl(order) for order in priced_closed_orders]
    return {
        "timestamp": int(time.time() * 1000),
        "mode": "paper-execution-ledger-read-only",
        "symbol": symbol,
        "currency": currency,
        "horizonSamples": horizon_samples,
        "includeProbes": include_probes,
        "priceSimulation": price_simulation,
        "priceSimulationFallback": PRICE_SIMULATION_SAMPLE_CLOSE
        if price_simulation == PRICE_SIMULATION_CANDLE_HIGH_LOW and allow_sample_close_fallback
        else None,
        "candleCount": len(normalized_candles),
        "candleInterval": _candle_interval_summary(normalized_candles),
        "candleSource": _candle_source_summary(normalized_candles),
        "sampleCount": len(samples),
        "orderCount": len(orders),
        "statusCounts": status_counts,
        "sourceCounts": source_counts,
        "openCount": status_counts.get("OPEN", 0),
        "closedCount": len(orders) - status_counts.get("OPEN", 0),
        "pricedClosedCount": len(priced_closed_orders),
        "evaluableClosedCount": len(priced_closed_orders),
        "unpricedClosedCount": len(unpriced_closed_orders),
        "closedVirtualEntryCount": sum(
            1 for order in priced_closed_orders if order.get("sourceType") == "virtual-entry"
        ),
        "closedProbeCount": sum(
            1 for order in priced_closed_orders if order.get("sourceType") == "paper-probe"
        ),
        "totalRoughNetPnlUsdt": _decimal_text(sum(pnl_values, Decimal("0"))),
        "orders": orders,
        "liveOrderSubmitted": False,
        "warnings": _paper_ledger_warnings(
            price_simulation=price_simulation,
            candle_count=len(normalized_candles),
            allow_sample_close_fallback=allow_sample_close_fallback,
        ),
        "nextPhase": "collect-more-paper-samples-and-validate-price-simulation",
    }


def build_paper_collection_snapshot(
    events: Iterable[dict[str, Any]],
    *,
    symbol: str,
    currency: str = "USDT",
    horizon_samples: int = 3,
    include_probes: bool = False,
) -> dict[str, Any]:
    if horizon_samples <= 0:
        raise ValueError("horizon_samples must be positive")

    raw_events = list(events)
    wanted_symbol = symbol.upper()
    wanted_currency = currency.upper()
    samples = [
        sample
        for event in raw_events
        if (sample := _event_sample(event)) is not None
        and sample.get("symbol") == wanted_symbol
        and sample.get("currency") == wanted_currency
    ]
    chronological = _sort_samples_chronological(samples)
    latest = _sort_samples_latest_first(samples)
    entries: list[dict[str, Any]] = []
    closed_entries: list[dict[str, Any]] = []
    open_entries: list[dict[str, Any]] = []

    for index, sample in enumerate(chronological):
        entry = _ledger_entry_sample(sample, include_probes=include_probes)
        if entry is None:
            continue
        entry_summary = {
            "eventId": entry.get("eventId"),
            "timestamp": entry.get("timestamp"),
            "sourceType": entry.get("sourceType"),
            "side": entry.get("side"),
            "futureSampleCount": len(chronological[index + 1 : index + 1 + horizon_samples]),
            "horizonSamples": horizon_samples,
        }
        entries.append(entry_summary)
        if entry_summary["futureSampleCount"] >= horizon_samples:
            closed_entries.append(entry_summary)
        else:
            open_entries.append(entry_summary)

    source_counts = _count_by_key(entries, "sourceType")
    closed_source_counts = _count_by_key(closed_entries, "sourceType")
    open_source_counts = _count_by_key(open_entries, "sourceType")
    latest_sample = latest[0] if latest else {}
    return {
        "mode": "paper-collection-snapshot-read-only",
        "symbol": wanted_symbol,
        "currency": wanted_currency,
        "rawEventCount": len(raw_events),
        "sampleCount": len(samples),
        "invalidEventCount": max(len(raw_events) - len(samples), 0),
        "horizonSamples": horizon_samples,
        "includeProbes": include_probes,
        "entryCount": len(entries),
        "closedEntryCount": len(closed_entries),
        "openEntryCount": len(open_entries),
        "virtualEntryCount": source_counts.get("virtual-entry", 0),
        "closedVirtualEntryCount": closed_source_counts.get("virtual-entry", 0),
        "openVirtualEntryCount": open_source_counts.get("virtual-entry", 0),
        "probeEntryCount": source_counts.get("paper-probe", 0),
        "closedProbeCount": closed_source_counts.get("paper-probe", 0),
        "openProbeCount": open_source_counts.get("paper-probe", 0),
        "latestSample": {
            "eventId": latest_sample.get("eventId"),
            "timestamp": latest_sample.get("timestamp"),
            "action": latest_sample.get("action"),
            "side": latest_sample.get("side"),
            "wouldOpen": latest_sample.get("wouldOpen"),
        },
        "liveOrderSubmitted": False,
    }


def _event_sample(event: dict[str, Any]) -> dict[str, Any] | None:
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None
    if payload.get("mode") != "paper-trading-read-only":
        return None
    return {
        "eventId": event.get("id"),
        "timestamp": payload.get("timestamp") or event.get("ts"),
        "symbol": str(payload.get("symbol") or "").upper(),
        "currency": str(payload.get("currency") or "USDT").upper(),
        "wouldOpen": bool(payload.get("wouldOpen")),
        "action": payload.get("action"),
        "side": payload.get("side"),
        "confidence": payload.get("confidence"),
        "virtualOrder": payload.get("virtualOrder"),
        "paperProbe": payload.get("paperProbe") if isinstance(payload.get("paperProbe"), dict) else None,
        "market": payload.get("market") if isinstance(payload.get("market"), dict) else None,
        "paperGates": payload.get("paperGates") if isinstance(payload.get("paperGates"), dict) else None,
        "volatilityFilter": payload.get("volatilityFilter")
        if isinstance(payload.get("volatilityFilter"), dict)
        else None,
        "regimeFilter": payload.get("regimeFilter") if isinstance(payload.get("regimeFilter"), dict) else None,
        "blockers": payload.get("blockers") if isinstance(payload.get("blockers"), list) else [],
    }


def _ledger_entry_sample(sample: dict[str, Any], *, include_probes: bool) -> dict[str, Any] | None:
    if sample.get("wouldOpen") and isinstance(sample.get("virtualOrder"), dict):
        entry = deepcopy(sample)
        entry["sourceType"] = "virtual-entry"
        return entry
    if not include_probes:
        return None
    probe = sample.get("paperProbe") if isinstance(sample.get("paperProbe"), dict) else {}
    probe_order = probe.get("virtualOrder") if isinstance(probe.get("virtualOrder"), dict) else None
    if probe.get("eligibleForRecoveryStats") is not True or not probe_order:
        return None
    entry = deepcopy(sample)
    entry["wouldOpen"] = True
    entry["virtualOrder"] = probe_order
    entry["sourceType"] = "paper-probe"
    entry["action"] = f"probe-{probe.get('side') or sample.get('side')}"
    return entry


def _ledger_order(
    entry_sample: dict[str, Any],
    *,
    future_samples: list[dict[str, Any]],
    horizon_samples: int,
    candles: list[dict[str, Any]],
    price_simulation: str,
    allow_sample_close_fallback: bool,
) -> dict[str, Any]:
    order = entry_sample.get("virtualOrder") if isinstance(entry_sample.get("virtualOrder"), dict) else {}
    source_type = str(entry_sample.get("sourceType") or "virtual-entry")
    source_event_id = entry_sample.get("eventId")
    evaluation = None
    status = "OPEN"
    pricing_status = "pending"
    lifecycle = ["NEW", "OPEN"]
    exit_detail = None
    rough_net = None

    if len(future_samples) >= horizon_samples:
        evaluation = _evaluate_edge(
            entry_sample,
            future_samples,
            candles=candles,
            price_simulation=price_simulation,
            allow_sample_close_fallback=allow_sample_close_fallback,
        )
        if evaluation is None:
            status = "EXPIRED"
            pricing_status = "unpriced"
            lifecycle = ["NEW", "FILLED", "EXPIRED"]
        else:
            pricing_status = "priced"
            exit_reason = str(evaluation.get("exitReason") or "")
            if exit_reason == "stop-loss":
                status = "STOPPED"
            elif exit_reason == "take-profit":
                status = "TAKE_PROFIT"
            else:
                status = "EXPIRED"
            lifecycle = ["NEW", "FILLED", status]
            exit_detail = {
                "exitEventId": evaluation.get("exitEventId"),
                "exitTimestamp": evaluation.get("exitTimestamp"),
                "exitPrice": evaluation.get("exitPrice"),
                "exitReason": evaluation.get("exitReason"),
                "moveBps": evaluation.get("moveBps"),
                "grossPnlUsdt": evaluation.get("grossPnlUsdt"),
                "roughNetPnlUsdt": evaluation.get("roughNetPnlUsdt"),
                "outcome": evaluation.get("outcome"),
                "exitSource": evaluation.get("exitSource"),
                "priceSimulation": evaluation.get("priceSimulation"),
                "fallbackUsed": evaluation.get("fallbackUsed"),
                "intraCandleAmbiguous": evaluation.get("intraCandleAmbiguous"),
                "ambiguityPolicy": evaluation.get("ambiguityPolicy"),
                "exitCandle": evaluation.get("exitCandle"),
            }
            rough_net = evaluation.get("roughNetPnlUsdt")

    estimated_fee = _decimal_or_none(order.get("estimatedTakerFee")) or Decimal("0")
    return {
        "orderId": f"{source_type}-{source_event_id}",
        "sourceType": source_type,
        "sourceEventId": source_event_id,
        "createdTimestamp": entry_sample.get("timestamp"),
        "symbol": entry_sample.get("symbol"),
        "currency": entry_sample.get("currency"),
        "side": entry_sample.get("side"),
        "confidence": entry_sample.get("confidence"),
        "entryMetrics": _ledger_entry_metrics(entry_sample),
        "status": status,
        "pricingStatus": pricing_status,
        "evaluable": pricing_status == "priced",
        "entryStatus": "OPEN" if status == "OPEN" else "FILLED",
        "lifecycle": lifecycle,
        "entryPrice": order.get("entryPrice"),
        "vol": order.get("vol"),
        "contractSize": order.get("contractSize"),
        "notional": order.get("notional"),
        "requiredMargin": order.get("requiredMargin"),
        "stopLossPrice": order.get("stopLossPrice"),
        "takeProfitPrice": order.get("takeProfitPrice"),
        "feeModel": "double-taker-estimate-from-paper-decision",
        "estimatedEntryFeeUsdt": _decimal_text(estimated_fee),
        "estimatedRoundTripFeeUsdt": _decimal_text(estimated_fee * Decimal("2")),
        "futureSampleCount": len(future_samples),
        "horizonSamples": horizon_samples,
        "exit": exit_detail,
        "roughNetPnlUsdt": rough_net,
        "liveOrderSubmitted": False,
    }


def _ledger_entry_metrics(entry_sample: dict[str, Any]) -> dict[str, Any]:
    paper_gates = entry_sample.get("paperGates") if isinstance(entry_sample.get("paperGates"), dict) else {}
    paper_observed = paper_gates.get("observed") if isinstance(paper_gates.get("observed"), dict) else {}
    volatility_filter = (
        entry_sample.get("volatilityFilter") if isinstance(entry_sample.get("volatilityFilter"), dict) else {}
    )
    regime_filter = entry_sample.get("regimeFilter") if isinstance(entry_sample.get("regimeFilter"), dict) else {}
    volatility_observed = (
        volatility_filter.get("observed")
        if isinstance(volatility_filter.get("observed"), dict)
        else regime_filter.get("observed")
        if isinstance(regime_filter.get("observed"), dict)
        else {}
    )

    metrics: dict[str, Any] = {}
    _copy_decimal_metric(metrics, paper_observed, "depthImbalanceTop10")
    _copy_decimal_metric(metrics, paper_observed, "spreadBps")
    _copy_decimal_metric(metrics, paper_observed, "fundingRate")
    _copy_decimal_metric(metrics, volatility_observed, "avgRangeBps")
    _copy_decimal_metric(metrics, volatility_observed, "latestRangeBps")
    return metrics


def _copy_decimal_metric(target: dict[str, Any], source: dict[str, Any], key: str) -> None:
    if key not in source:
        return
    value = _decimal_or_none(source.get(key))
    if value is not None:
        target[key] = _decimal_text(value)


def _order_priced_pnl(order: dict[str, Any]) -> Decimal | None:
    pnl = _decimal_or_none(order.get("roughNetPnlUsdt"))
    if pnl is not None:
        return pnl
    exit_detail = order.get("exit") if isinstance(order.get("exit"), dict) else {}
    return _decimal_or_none(exit_detail.get("roughNetPnlUsdt"))


def _is_closed_order(order: dict[str, Any]) -> bool:
    return str(order.get("status") or "").upper() != "OPEN"


def _is_priced_closed_order(order: dict[str, Any]) -> bool:
    return _is_closed_order(order) and _order_priced_pnl(order) is not None


def _is_unpriced_closed_order(order: dict[str, Any]) -> bool:
    return _is_closed_order(order) and _order_priced_pnl(order) is None


def _sort_samples_latest_first(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(samples, key=_sample_order_key, reverse=True)


def _sort_samples_chronological(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(samples, key=_sample_order_key)


def _sample_order_key(sample: dict[str, Any]) -> tuple[int, int]:
    return (_as_int(sample.get("timestamp")) or 0, _as_int(sample.get("eventId")) or 0)


def _sample_age_seconds(sample: dict[str, Any], *, now_ms: int) -> int | None:
    timestamp_ms = _as_int(sample.get("timestamp"))
    if timestamp_ms is None:
        return None
    return max(0, (now_ms - timestamp_ms) // 1000)


def _age_seconds_from_timestamp(value: Any, *, now_ms: int) -> int | None:
    timestamp_ms = _timestamp_to_ms(value)
    if timestamp_ms is None:
        return None
    return max(0, (now_ms - timestamp_ms) // 1000)


def _timestamp_to_ms(value: Any) -> int | None:
    timestamp = _as_int(value)
    if timestamp is None or timestamp <= 0:
        return None
    if timestamp >= 10**15:
        return timestamp // 1_000_000
    if timestamp >= 10**12:
        return timestamp
    if timestamp >= 10**9:
        return timestamp * 1000
    return timestamp


def _freshness_blockers(
    latest: dict[str, Any] | None,
    *,
    latest_sample_age_seconds: int | None,
    max_sample_age_seconds: int | None,
) -> list[str]:
    if max_sample_age_seconds is None:
        return []
    if latest is None:
        return ["latest paper sample is missing"]
    if latest_sample_age_seconds is None:
        return ["latest paper sample timestamp is missing"]
    if latest_sample_age_seconds > max_sample_age_seconds:
        return [
            f"latest paper sample age {latest_sample_age_seconds}s above gate {max_sample_age_seconds}s"
        ]
    return []


def _market_snapshot(market: dict[str, Any]) -> dict[str, Any]:
    last_trade = market.get("lastTrade") if isinstance(market.get("lastTrade"), dict) else {}
    book = market.get("bookDeltas") if isinstance(market.get("bookDeltas"), dict) else {}
    return {
        "lastTradePrice": _decimal_text(_decimal_or_none(last_trade.get("price"))),
        "lastTradeSize": _decimal_text(_decimal_or_none(last_trade.get("size"))),
        "lastTradeId": last_trade.get("tradeId"),
        "lastTradeTsEvent": last_trade.get("tsEvent"),
        "lastTradeTsInit": last_trade.get("tsInit"),
        "bookSequence": book.get("sequence"),
        "bookDeltaCount": book.get("deltaCount"),
        "bookTsEvent": book.get("tsEvent"),
        "bookTsInit": book.get("tsInit"),
    }


def _market_freshness_snapshot(
    *,
    market: dict[str, Any],
    max_market_age_seconds: int | None,
    now_ms: int,
) -> dict[str, Any]:
    last_trade = market.get("lastTrade") if isinstance(market.get("lastTrade"), dict) else {}
    book = market.get("bookDeltas") if isinstance(market.get("bookDeltas"), dict) else {}
    trade_age = _age_seconds_from_timestamp(last_trade.get("tsEvent"), now_ms=now_ms)
    book_age = _age_seconds_from_timestamp(book.get("tsEvent"), now_ms=now_ms)
    blockers: list[str] = []
    warnings: list[str] = []
    if max_market_age_seconds is not None:
        if trade_age is None:
            blockers.append("last trade market timestamp is missing")
        elif trade_age > max_market_age_seconds:
            blockers.append(f"last trade market age {trade_age}s above gate {max_market_age_seconds}s")
        if book_age is None:
            blockers.append("order book market timestamp is missing")
        elif book_age > max_market_age_seconds:
            blockers.append(f"order book market age {book_age}s above gate {max_market_age_seconds}s")
    else:
        if trade_age is None:
            warnings.append("market freshness skipped last trade age; timestamp missing")
        if book_age is None:
            warnings.append("market freshness skipped order book age; timestamp missing")

    return {
        "thresholds": {"maxMarketAgeSeconds": max_market_age_seconds},
        "observed": {
            "lastTradeAgeSeconds": trade_age,
            "bookAgeSeconds": book_age,
            "lastTradeTsEvent": last_trade.get("tsEvent"),
            "bookTsEvent": book.get("tsEvent"),
        },
        "blockers": blockers,
        "warnings": warnings,
    }


def _paper_gate_snapshot(
    *,
    metrics: dict[str, Any],
    side: str,
    min_depth_imbalance: float,
    max_spread_bps: float,
    max_abs_funding_rate: float,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    depth_imbalance = _decimal_or_none(metrics.get("depthImbalanceTop10"))
    bid = _decimal_or_none(metrics.get("bid"))
    ask = _decimal_or_none(metrics.get("ask"))
    spread = _decimal_or_none(metrics.get("spread"))
    funding_rate = _decimal_or_none(metrics.get("fundingRate"))
    spread_bps = _spread_bps(bid=bid, ask=ask, spread=spread) or _decimal_or_none(metrics.get("spreadBps"))

    min_depth = Decimal(str(min_depth_imbalance))
    if side in OPEN_SIDES:
        if depth_imbalance is None:
            blockers.append("depth imbalance gate missing strategy metric")
        elif side == "open-long" and depth_imbalance < min_depth:
            blockers.append(f"depth imbalance {depth_imbalance} below long gate {min_depth}")
        elif side == "open-short" and depth_imbalance > -min_depth:
            blockers.append(f"depth imbalance {depth_imbalance} above short gate {-min_depth}")

    if max_spread_bps > 0:
        max_spread = Decimal(str(max_spread_bps))
        if spread_bps is None:
            blockers.append("spread bps gate missing strategy metric")
        elif spread_bps > max_spread:
            blockers.append(f"spread {spread_bps} bps above gate {max_spread}")

    if max_abs_funding_rate > 0:
        max_funding = Decimal(str(max_abs_funding_rate))
        if funding_rate is None:
            blockers.append("funding rate gate missing strategy metric")
        elif abs(funding_rate) > max_funding:
            blockers.append(f"absolute funding rate {abs(funding_rate)} above gate {max_funding}")

    return {
        "thresholds": {
            "minDepthImbalance": min_depth_imbalance,
            "maxSpreadBps": max_spread_bps,
            "maxAbsFundingRate": max_abs_funding_rate,
        },
        "observed": {
            "depthImbalanceTop10": _decimal_text(depth_imbalance),
            "spreadBps": _decimal_text(spread_bps),
            "fundingRate": _decimal_text(funding_rate),
        },
        "blockers": blockers,
        "warnings": warnings,
    }


def _trend_gate_snapshot(*, trend_filter: dict[str, Any] | None, side: str) -> dict[str, Any]:
    if trend_filter is None:
        return {
            "enabled": False,
            "blockers": [],
            "warnings": [],
        }

    blockers: list[str] = []
    warnings = [str(warning) for warning in trend_filter.get("warnings") or []]
    if trend_filter.get("ok") is not True:
        reasons = [str(reason) for reason in trend_filter.get("blockers") or ["trend filter is not ready"]]
        blockers.extend(f"trend filter not ready: {reason}" for reason in reasons)

    trend = str(trend_filter.get("trend") or "unknown")
    if side == "open-long" and trend != "bullish":
        blockers.append(f"trend filter blocks long: trend is {trend}")
    elif side == "open-short" and trend != "bearish":
        blockers.append(f"trend filter blocks short: trend is {trend}")

    return {
        "enabled": True,
        "trend": trend,
        "source": trend_filter.get("source"),
        "candleCount": trend_filter.get("candleCount"),
        "shortPeriod": trend_filter.get("shortPeriod"),
        "longPeriod": trend_filter.get("longPeriod"),
        "latestCandleAgeSeconds": trend_filter.get("latestCandleAgeSeconds"),
        "observed": trend_filter.get("observed") if isinstance(trend_filter.get("observed"), dict) else {},
        "blockers": blockers,
        "warnings": warnings,
    }


def _volatility_gate_snapshot(*, volatility_filter: dict[str, Any] | None) -> dict[str, Any]:
    if volatility_filter is None:
        return {
            "enabled": False,
            "blockers": [],
            "warnings": [],
        }

    blockers: list[str] = []
    warnings = [str(warning) for warning in volatility_filter.get("warnings") or []]
    if volatility_filter.get("ok") is not True:
        reasons = [str(reason) for reason in volatility_filter.get("blockers") or ["volatility filter is not ready"]]
        blockers.extend(f"volatility filter not ready: {reason}" for reason in reasons)

    return {
        "enabled": True,
        "regime": volatility_filter.get("regime"),
        "source": volatility_filter.get("source"),
        "candleCount": volatility_filter.get("candleCount"),
        "validCandleRangeCount": volatility_filter.get("validCandleRangeCount"),
        "latestCandleAgeSeconds": volatility_filter.get("latestCandleAgeSeconds"),
        "thresholds": (
            volatility_filter.get("thresholds") if isinstance(volatility_filter.get("thresholds"), dict) else {}
        ),
        "observed": volatility_filter.get("observed") if isinstance(volatility_filter.get("observed"), dict) else {},
        "blockers": blockers,
        "warnings": warnings,
    }


def _regime_gate_snapshot(volatility_gate: dict[str, Any]) -> dict[str, Any]:
    if volatility_gate.get("enabled") is not True:
        return {
            "enabled": False,
            "blockers": [],
            "warnings": [],
        }
    return {
        "enabled": True,
        "regime": volatility_gate.get("regime"),
        "source": volatility_gate.get("source"),
        "candleCount": volatility_gate.get("candleCount"),
        "observed": volatility_gate.get("observed") if isinstance(volatility_gate.get("observed"), dict) else {},
        "blockers": volatility_gate.get("blockers", []),
        "warnings": volatility_gate.get("warnings", []),
    }


def _spread_bps(
    *,
    bid: Decimal | None,
    ask: Decimal | None,
    spread: Decimal | None,
) -> Decimal | None:
    if bid is None or ask is None or bid <= 0 or ask <= 0:
        return None
    effective_spread = spread if spread is not None else ask - bid
    mid = (bid + ask) / Decimal("2")
    if mid <= 0:
        return None
    return effective_spread / mid * Decimal("10000")


def _edge_preview(
    samples: list[dict[str, Any]],
    *,
    horizon_samples: int,
    candles: list[dict[str, Any]],
    price_simulation: str,
    allow_sample_close_fallback: bool,
) -> dict[str, Any]:
    edge = build_paper_edge_report(
        _samples_to_edge_events(samples),
        symbol=samples[0]["symbol"] if samples else "",
        currency=samples[0]["currency"] if samples else "USDT",
        horizon_samples=horizon_samples,
        min_evaluable=1,
        candles=candles,
        price_simulation=price_simulation,
        allow_sample_close_fallback=allow_sample_close_fallback,
    )
    return {
        "horizonSamples": edge["horizonSamples"],
        "evaluableCount": edge["evaluableCount"],
        "pendingCount": edge["pendingCount"],
        "winCount": edge["winCount"],
        "lossCount": edge["lossCount"],
        "winRate": edge["winRate"],
        "totalRoughNetPnlUsdt": edge["totalRoughNetPnlUsdt"],
    }


def _paper_quality_gate(
    samples: list[dict[str, Any]],
    *,
    symbol: str,
    currency: str,
    edge_horizon_samples: int,
    min_samples: int,
    min_edge_evaluable: int,
    min_edge_win_rate: float,
    min_side_edge_evaluable: int,
    min_side_edge_win_rate: float,
    policy_allowed_sides: set[str],
    recovery_window_evaluable: int,
    recovery_min_win_rate: float,
    candles: list[dict[str, Any]],
    price_simulation: str,
    allow_sample_close_fallback: bool,
) -> dict[str, Any]:
    blockers: list[str] = []
    if len(samples) < min_samples:
        blockers.append(f"sample count {len(samples)} below gate {min_samples}")

    edge = build_paper_edge_report(
        _samples_to_edge_events(samples),
        symbol=symbol,
        currency=currency,
        horizon_samples=edge_horizon_samples,
        min_evaluable=min_edge_evaluable,
        candles=candles,
        price_simulation=price_simulation,
        allow_sample_close_fallback=allow_sample_close_fallback,
    )
    if edge["evaluableCount"] < min_edge_evaluable:
        blockers.append(f"edge evaluable count {edge['evaluableCount']} below gate {min_edge_evaluable}")

    win_rate = edge["winRate"]
    min_win_rate = Decimal(str(min_edge_win_rate))
    win_rate_decimal = _decimal_or_none(win_rate)
    if win_rate_decimal is None:
        blockers.append("edge win rate is not available")
    elif win_rate_decimal < min_win_rate:
        blockers.append(f"edge win rate {win_rate_decimal} below gate {min_win_rate}")

    total_pnl = _decimal_or_none(edge["totalRoughNetPnlUsdt"])
    if total_pnl is None or total_pnl <= 0:
        blockers.append(f"edge rough net pnl {edge['totalRoughNetPnlUsdt']} is not positive")

    recovery_edge = build_paper_edge_report(
        _samples_to_edge_events(samples, include_probes=True),
        symbol=symbol,
        currency=currency,
        horizon_samples=edge_horizon_samples,
        min_evaluable=1,
        candles=candles,
        price_simulation=price_simulation,
        allow_sample_close_fallback=allow_sample_close_fallback,
    )
    side_gates = _side_quality_gates(
        edge.get("sideStats") if isinstance(edge.get("sideStats"), dict) else {},
        recovery_edge.get("evaluations") if isinstance(recovery_edge.get("evaluations"), list) else [],
        min_side_edge_evaluable=min_side_edge_evaluable,
        min_side_edge_win_rate=min_side_edge_win_rate,
        recovery_window_evaluable=recovery_window_evaluable,
        recovery_min_win_rate=recovery_min_win_rate,
    )
    strategy_policy_gate = _strategy_policy_quality_gate(
        side_gates,
        policy_allowed_sides=policy_allowed_sides,
    )

    return {
        "readyForLiveCandidate": not blockers,
        "minSamples": min_samples,
        "edgeHorizonSamples": edge_horizon_samples,
        "priceSimulation": price_simulation,
        "priceSimulationFallback": PRICE_SIMULATION_SAMPLE_CLOSE
        if price_simulation == PRICE_SIMULATION_CANDLE_HIGH_LOW and allow_sample_close_fallback
        else None,
        "candleCount": len(candles),
        "minEdgeEvaluable": min_edge_evaluable,
        "minEdgeWinRate": min_edge_win_rate,
        "minSideEdgeEvaluable": min_side_edge_evaluable,
        "minSideEdgeWinRate": min_side_edge_win_rate,
        "recoveryWindowEvaluable": recovery_window_evaluable,
        "recoveryMinWinRate": recovery_min_win_rate,
        "sampleCount": len(samples),
        "edgeEvaluableCount": edge["evaluableCount"],
        "edgeWinRate": win_rate,
        "edgeTotalRoughNetPnlUsdt": edge["totalRoughNetPnlUsdt"],
        "recoveryEvaluableCount": recovery_edge["evaluableCount"],
        "recoveryProbeCount": _probe_count(samples),
        "sideGates": side_gates,
        "strategyPolicyQualityGate": strategy_policy_gate,
        "blockers": blockers,
        "liveOrderSubmitted": False,
    }


def _readiness_component(
    name: str,
    weight: int,
    passed: bool,
    *,
    blockers: list[Any],
    earned: Decimal | None = None,
) -> dict[str, Any]:
    effective_earned = Decimal(weight) if passed else Decimal("0")
    if earned is not None:
        effective_earned = min(max(earned, Decimal("0")), Decimal(weight))
    return {
        "name": name,
        "weight": weight,
        "passed": passed,
        "earned": _decimal_text(effective_earned),
        "blockers": [str(blocker) for blocker in blockers] if not passed else [],
    }


def _paper_live_lock_blockers(safety_report: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if safety_report.get("liveTradingEnabled") is not False:
        blockers.append("live trading is enabled or unknown")
    if safety_report.get("readyForLive") is not False:
        blockers.append("readyForLive is true or unknown")
    if safety_report.get("liveMutationPhaseEnabled") is True:
        blockers.append("live mutation phase is enabled")
    if safety_report.get("liveMutationFlagsArmed") is True:
        blockers.append("live mutation flags are armed")
    return blockers


def _paper_readiness_next_actions(blocking_components: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    names = {str(component.get("name")) for component in blocking_components}
    if "readonly-safety" in names:
        actions.append("fix safety-status/audit-safety findings before collecting more samples")
    if "paper-live-lock" in names:
        actions.append("disable live trading flags and keep paper mode locked")
    if "paper-sample-volume" in names:
        actions.append("run nautilus-paper-loop with --save until target sample count is reached")
    if "paper-sample-freshness" in names:
        actions.append("collect a fresh nautilus-paper-decision sample before trusting audit readiness")
    if "paper-reviewable" in names:
        actions.append("collect enough saved paper samples for review")
    if "global-edge-quality" in names:
        actions.append("keep collecting and tighten strategy gates until global edge win-rate and rough PnL are positive")
    if "policy-side-quality" in names:
        actions.append("keep current allowed side policy paused until the active side has positive side edge")
    if "rolling-recent-quality" in names:
        actions.append("wait for recent rolling windows to clear before considering any live candidate")
    if "paper-performance-quality" in names:
        actions.append("keep paper-only until closed trade count, equity, expectancy, drawdown, and profit factor pass")
    return _dedupe(actions)


def _paper_collection_progress(
    *,
    audit_report: dict[str, Any],
    quality_gate: dict[str, Any],
    performance_gate: dict[str, Any],
    target_sample_count: int,
    target_closed_count: int,
) -> dict[str, Any]:
    sample_count = _as_int(audit_report.get("sampleCount")) or 0
    performance_observed = (
        performance_gate.get("observed") if isinstance(performance_gate.get("observed"), dict) else {}
    )
    closed_count = _as_int(performance_observed.get("evaluableClosedCount"))
    if closed_count is None:
        closed_count = _as_int(performance_observed.get("closedCount")) or 0
    unpriced_closed_count = _as_int(performance_observed.get("unpricedClosedCount")) or 0
    skipped_closed_count = _as_int(performance_observed.get("skippedClosedCount")) or 0
    open_count = _as_int(performance_observed.get("openCount")) or 0
    evaluable_count = _as_int(quality_gate.get("edgeEvaluableCount")) or 0
    probe_count = _as_int(quality_gate.get("recoveryProbeCount")) or 0
    action_counts = audit_report.get("actionCounts") if isinstance(audit_report.get("actionCounts"), dict) else {}
    paper_open_count = sum(
        _as_int(action_counts.get(action)) or 0
        for action in ("paper-open-long", "paper-open-short")
    )
    hold_count = _as_int(action_counts.get("hold")) or 0
    blocker_counts = audit_report.get("blockerCounts") if isinstance(audit_report.get("blockerCounts"), dict) else {}
    latest_sample = audit_report.get("latestSample") if isinstance(audit_report.get("latestSample"), dict) else {}

    return {
        "samples": {
            "current": sample_count,
            "target": target_sample_count,
            "remaining": max(target_sample_count - sample_count, 0),
            "progressPct": _progress_pct(sample_count, target_sample_count),
        },
        "closedTrades": {
            "current": closed_count,
            "target": target_closed_count,
            "remaining": max(target_closed_count - closed_count, 0),
            "progressPct": _progress_pct(closed_count, target_closed_count),
            "evaluable": closed_count,
            "unpriced": unpriced_closed_count,
            "skipped": skipped_closed_count,
        },
        "paperOrders": {
            "open": open_count,
            "evaluableEntries": evaluable_count,
            "paperOpenSignals": paper_open_count,
            "probeCount": probe_count,
            "holdCount": hold_count,
            "entryYield": _ratio_float(paper_open_count, sample_count),
        },
        "latestSample": {
            "eventId": latest_sample.get("eventId"),
            "timestamp": latest_sample.get("timestamp"),
            "action": latest_sample.get("action"),
            "side": latest_sample.get("side"),
            "wouldOpen": latest_sample.get("wouldOpen"),
            "blockers": latest_sample.get("blockers") if isinstance(latest_sample.get("blockers"), list) else [],
        },
        "topBlockers": _top_counts(blocker_counts),
        "readyForCollectionTargets": (
            sample_count >= target_sample_count
            and closed_count >= target_closed_count
            and open_count == 0
            and unpriced_closed_count == 0
            and skipped_closed_count == 0
        ),
        "liveOrderSubmitted": False,
    }


def _progress_pct(current: int, target: int) -> float | None:
    if target <= 0:
        return None
    return round(min(current / target, 1), 6)


def _ratio_float(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _top_counts(counts: dict[str, Any], *, limit: int = 8) -> list[dict[str, Any]]:
    rows = [
        {"reason": str(reason), "count": count}
        for reason, raw_count in counts.items()
        if (count := _as_int(raw_count)) is not None and count > 0
    ]
    return sorted(rows, key=lambda row: (-row["count"], row["reason"]))[:limit]


def _strict_readiness_quality_blockers(quality_gate: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if quality_gate.get("priceSimulation") != PRICE_SIMULATION_CANDLE_HIGH_LOW:
        blockers.append("strict readiness requires candle-high-low price simulation")
    if quality_gate.get("priceSimulationFallback") is not None:
        blockers.append("strict readiness forbids sample-close fallback")

    edge_horizon_samples = _as_int(quality_gate.get("edgeHorizonSamples"))
    if edge_horizon_samples is None or edge_horizon_samples < 3:
        blockers.append(f"strict readiness requires edge horizon samples at least 3, got {edge_horizon_samples}")

    min_edge_evaluable = _as_int(quality_gate.get("minEdgeEvaluable"))
    if min_edge_evaluable is None or min_edge_evaluable < 3:
        blockers.append(f"strict readiness requires min edge evaluable at least 3, got {min_edge_evaluable}")

    min_edge_win_rate = _decimal_or_none(quality_gate.get("minEdgeWinRate"))
    if min_edge_win_rate is None or min_edge_win_rate < Decimal("0.55"):
        blockers.append(f"strict readiness requires min edge win rate at least 0.55, got {quality_gate.get('minEdgeWinRate')}")

    min_side_edge_evaluable = _as_int(quality_gate.get("minSideEdgeEvaluable"))
    if min_side_edge_evaluable is None or min_side_edge_evaluable < 2:
        blockers.append(
            f"strict readiness requires min side edge evaluable at least 2, got {min_side_edge_evaluable}"
        )

    min_side_edge_win_rate = _decimal_or_none(quality_gate.get("minSideEdgeWinRate"))
    if min_side_edge_win_rate is None or min_side_edge_win_rate < Decimal("0.55"):
        blockers.append(
            f"strict readiness requires min side edge win rate at least 0.55, got {quality_gate.get('minSideEdgeWinRate')}"
        )

    recovery_window_evaluable = _as_int(quality_gate.get("recoveryWindowEvaluable"))
    if recovery_window_evaluable is None or recovery_window_evaluable < 3:
        blockers.append(
            f"strict readiness requires recovery window evaluable at least 3, got {recovery_window_evaluable}"
        )

    recovery_min_win_rate = _decimal_or_none(quality_gate.get("recoveryMinWinRate"))
    if recovery_min_win_rate is None or recovery_min_win_rate < Decimal("0.55"):
        blockers.append(
            f"strict readiness requires recovery min win rate at least 0.55, got {quality_gate.get('recoveryMinWinRate')}"
        )

    return blockers


def _strict_readiness_rolling_blockers(rolling_windows: dict[str, Any]) -> list[str]:
    configured = rolling_windows.get("configured") if isinstance(rolling_windows.get("configured"), list) else []
    configured_set = {_as_int(window) for window in configured}
    missing = [window for window in DEFAULT_ROLLING_WINDOWS if window not in configured_set]
    if not missing:
        return []
    return [f"strict readiness requires rolling windows {list(DEFAULT_ROLLING_WINDOWS)}, missing {missing}"]


def _rolling_quality_windows(
    samples: list[dict[str, Any]],
    *,
    symbol: str,
    currency: str,
    edge_horizon_samples: int,
    min_samples: int,
    min_edge_evaluable: int,
    min_edge_win_rate: float,
    min_side_edge_evaluable: int,
    min_side_edge_win_rate: float,
    policy_allowed_sides: set[str],
    recovery_window_evaluable: int,
    recovery_min_win_rate: float,
    rolling_windows: tuple[int, ...],
    external_blockers: list[str],
    candles: list[dict[str, Any]],
    price_simulation: str,
    allow_sample_close_fallback: bool,
) -> dict[str, Any]:
    reports: dict[str, Any] = {}
    blockers: list[str] = []
    eligible_windows: list[int] = []
    for window in rolling_windows:
        window_samples = samples[:window]
        if len(window_samples) < min_samples:
            reports[str(window)] = {
                "sampleCount": len(window_samples),
                "minSamples": min_samples,
                "readyForRecentQuality": False,
                "skipped": True,
                "blockers": [f"sample count {len(window_samples)} below gate {min_samples}"],
            }
            continue
        eligible_windows.append(window)
        gate = _paper_quality_gate(
            window_samples,
            symbol=symbol,
            currency=currency,
            edge_horizon_samples=edge_horizon_samples,
            min_samples=min_samples,
            min_edge_evaluable=min_edge_evaluable,
            min_edge_win_rate=min_edge_win_rate,
            min_side_edge_evaluable=min_side_edge_evaluable,
            min_side_edge_win_rate=min_side_edge_win_rate,
            policy_allowed_sides=policy_allowed_sides,
            recovery_window_evaluable=recovery_window_evaluable,
            recovery_min_win_rate=recovery_min_win_rate,
            candles=candles,
            price_simulation=price_simulation,
            allow_sample_close_fallback=allow_sample_close_fallback,
        )
        _apply_quality_gate_external_blockers(gate, external_blockers, label="paper audit freshness")
        policy_gate = (
            gate.get("strategyPolicyQualityGate")
            if isinstance(gate.get("strategyPolicyQualityGate"), dict)
            else {}
        )
        window_blockers = [str(reason) for reason in gate.get("blockers") or []]
        if policy_gate.get("readyForCurrentStrategyLiveCandidate") is not True:
            window_blockers.extend(
                f"policy: {reason}" for reason in policy_gate.get("liveBlockers") or []
            )
        reports[str(window)] = {
            "sampleCount": len(window_samples),
            "readyForRecentQuality": not window_blockers,
            "paperQualityGate": gate,
            "blockers": _dedupe(window_blockers),
        }
        blockers.extend(f"last {window} samples: {reason}" for reason in reports[str(window)]["blockers"])

    if not eligible_windows:
        blockers.append(f"no rolling window has at least {min_samples} sample(s)")

    return {
        "configured": list(rolling_windows),
        "eligible": eligible_windows,
        "readyForRecentQuality": not blockers,
        "blockers": _dedupe(blockers),
        "windows": reports,
    }


def _apply_quality_gate_external_blockers(
    quality_gate: dict[str, Any],
    blockers: list[str],
    *,
    label: str,
) -> None:
    if not blockers:
        return
    quality_gate.setdefault("blockers", [])
    quality_gate["blockers"].extend(f"{label}: {reason}" for reason in blockers)
    quality_gate["blockers"] = _dedupe([str(reason) for reason in quality_gate["blockers"]])
    quality_gate["readyForLiveCandidate"] = False


def _normalize_rolling_windows(rolling_windows: tuple[int, ...] | None) -> tuple[int, ...]:
    if rolling_windows is None:
        return ()
    return tuple(sorted({int(window) for window in rolling_windows if int(window) > 0}))


def _side_quality_gates(
    side_stats: dict[str, Any],
    evaluations: list[dict[str, Any]],
    *,
    min_side_edge_evaluable: int,
    min_side_edge_win_rate: float,
    recovery_window_evaluable: int,
    recovery_min_win_rate: float,
) -> dict[str, Any]:
    min_win_rate = Decimal(str(min_side_edge_win_rate))
    gates: dict[str, Any] = {}
    for side in sorted(OPEN_SIDES):
        stats = side_stats.get(side) if isinstance(side_stats.get(side), dict) else {}
        evaluable_count = _as_int(stats.get("evaluableCount")) or 0
        win_rate = _decimal_or_none(stats.get("winRate"))
        total_pnl = _decimal_or_none(stats.get("totalRoughNetPnlUsdt"))
        blockers: list[str] = []
        warnings: list[str] = []
        paper_pause_reasons: list[str] = []

        if evaluable_count < min_side_edge_evaluable:
            blockers.append(f"{side} edge evaluable count {evaluable_count} below gate {min_side_edge_evaluable}")
            warnings.append(f"{side} needs more paper samples before side quality can pause entries")
        else:
            if win_rate is None:
                blockers.append(f"{side} edge win rate is not available")
                paper_pause_reasons.append("edge win rate is not available")
            elif win_rate < min_win_rate:
                reason = f"edge win rate {win_rate} below gate {min_win_rate}"
                blockers.append(f"{side} {reason}")
                paper_pause_reasons.append(reason)
            if total_pnl is None or total_pnl <= 0:
                reason = f"edge rough net pnl {stats.get('totalRoughNetPnlUsdt', '0')} is not positive"
                blockers.append(f"{side} {reason}")
                paper_pause_reasons.append(reason)

        recovery = _side_recovery_stats(
            evaluations,
            side=side,
            recovery_window_evaluable=recovery_window_evaluable,
            recovery_min_win_rate=recovery_min_win_rate,
        )
        recovery_ready = recovery["readyForRecovery"]
        if paper_pause_reasons and recovery_ready:
            warnings.append(f"{side} recovered for new paper entries using recent window")

        gates[side] = {
            "readyForLiveCandidate": not blockers,
            "readyForNewPaperEntry": not paper_pause_reasons or recovery_ready,
            "pauseNewPaperEntries": bool(paper_pause_reasons) and not recovery_ready,
            "evaluableCount": evaluable_count,
            "winCount": _as_int(stats.get("winCount")) or 0,
            "lossCount": _as_int(stats.get("lossCount")) or 0,
            "flatCount": _as_int(stats.get("flatCount")) or 0,
            "winRate": stats.get("winRate"),
            "totalRoughNetPnlUsdt": stats.get("totalRoughNetPnlUsdt", "0"),
            "recovery": recovery,
            "blockers": blockers,
            "paperPauseReasons": paper_pause_reasons,
            "warnings": warnings,
        }
    return gates


def _side_recovery_stats(
    evaluations: list[dict[str, Any]],
    *,
    side: str,
    recovery_window_evaluable: int,
    recovery_min_win_rate: float,
) -> dict[str, Any]:
    side_items = [item for item in evaluations if str(item.get("side") or "") == side]
    recent_items = side_items[-recovery_window_evaluable:]
    wins = sum(1 for item in recent_items if item.get("outcome") == "win")
    losses = sum(1 for item in recent_items if item.get("outcome") == "loss")
    flats = sum(1 for item in recent_items if item.get("outcome") == "flat")
    pnl_values = [_decimal_or_none(item.get("roughNetPnlUsdt")) or Decimal("0") for item in recent_items]
    total_pnl = sum(pnl_values, Decimal("0"))
    win_rate = round(wins / len(recent_items), 6) if recent_items else None
    blockers: list[str] = []
    if len(recent_items) < recovery_window_evaluable:
        blockers.append(f"recent evaluable count {len(recent_items)} below recovery window {recovery_window_evaluable}")
    if win_rate is None:
        blockers.append("recent win rate is not available")
    elif Decimal(str(win_rate)) < Decimal(str(recovery_min_win_rate)):
        blockers.append(f"recent win rate {win_rate} below recovery gate {recovery_min_win_rate}")
    if total_pnl <= 0:
        blockers.append(f"recent rough net pnl {_decimal_text(total_pnl)} is not positive")
    return {
        "readyForRecovery": not blockers,
        "windowEvaluable": recovery_window_evaluable,
        "minWinRate": recovery_min_win_rate,
        "evaluableCount": len(recent_items),
        "winCount": wins,
        "lossCount": losses,
        "flatCount": flats,
        "winRate": win_rate,
        "totalRoughNetPnlUsdt": _decimal_text(total_pnl),
        "entryEventIds": [item.get("entryEventId") for item in recent_items],
        "blockers": blockers,
    }


def _strategy_policy_quality_gate(
    side_gates: dict[str, Any],
    *,
    policy_allowed_sides: set[str],
) -> dict[str, Any]:
    blockers: list[str] = []
    live_blockers: list[str] = []
    allowed_sides = sorted(policy_allowed_sides)
    evaluable_count = 0
    win_count = 0
    pnl_total = Decimal("0")
    if not allowed_sides:
        blockers.append("no strategy side is allowed by policy")
        live_blockers.append("no strategy side is allowed by policy")

    for side in allowed_sides:
        gate = side_gates.get(side) if isinstance(side_gates.get(side), dict) else None
        if gate is None:
            blockers.append(f"{side} has no side quality gate")
            continue
        evaluable_count += _as_int(gate.get("evaluableCount")) or 0
        win_count += _as_int(gate.get("winCount")) or 0
        pnl_total += _decimal_or_none(gate.get("totalRoughNetPnlUsdt")) or Decimal("0")
        if gate.get("readyForNewPaperEntry") is not True:
            side_reasons = gate.get("paperPauseReasons") if isinstance(gate.get("paperPauseReasons"), list) else []
            if not side_reasons:
                side_reasons = gate.get("blockers") if isinstance(gate.get("blockers"), list) else []
            blockers.extend(f"{side}: {reason}" for reason in side_reasons)
        if gate.get("readyForLiveCandidate") is not True:
            side_reasons = gate.get("blockers") if isinstance(gate.get("blockers"), list) else []
            live_blockers.extend(f"{side}: {reason}" for reason in side_reasons)

    win_rate = round(win_count / evaluable_count, 6) if evaluable_count else None

    return {
        "readyForCurrentStrategyPaperCandidate": not blockers,
        "readyForCurrentStrategyLiveCandidate": not live_blockers,
        "allowedSides": allowed_sides,
        "evaluableCount": evaluable_count,
        "winCount": win_count,
        "winRate": win_rate,
        "totalRoughNetPnlUsdt": _decimal_text(pnl_total),
        "blockers": blockers,
        "liveBlockers": live_blockers,
        "liveOrderSubmitted": False,
    }


def _normalize_policy_sides(policy_allowed_sides: set[str] | None) -> set[str]:
    if policy_allowed_sides is None:
        return set(OPEN_SIDES)
    return {str(side).lower() for side in policy_allowed_sides if str(side).lower() in OPEN_SIDES}


def _samples_to_edge_events(samples: list[dict[str, Any]], *, include_probes: bool = False) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for sample in samples:
        would_open = sample.get("wouldOpen")
        action = sample.get("action")
        virtual_order = sample.get("virtualOrder")
        if include_probes and not would_open:
            probe = sample.get("paperProbe") if isinstance(sample.get("paperProbe"), dict) else {}
            probe_order = probe.get("virtualOrder") if isinstance(probe.get("virtualOrder"), dict) else None
            if probe.get("eligibleForRecoveryStats") is True and probe_order:
                would_open = True
                action = f"probe-{probe.get('side') or sample.get('side')}"
                virtual_order = probe_order
        events.append(
            {
            "id": sample.get("eventId"),
            "ts": sample.get("timestamp"),
            "payload": {
                "mode": "paper-trading-read-only",
                "symbol": sample.get("symbol"),
                "currency": sample.get("currency"),
                "timestamp": sample.get("timestamp"),
                "wouldOpen": would_open,
                "action": action,
                "side": sample.get("side"),
                "confidence": sample.get("confidence"),
                "virtualOrder": virtual_order,
                "market": sample.get("market"),
                "blockers": sample.get("blockers", []),
            },
        }
        )
    return events


def _probe_count(samples: list[dict[str, Any]]) -> int:
    count = 0
    for sample in samples:
        probe = sample.get("paperProbe") if isinstance(sample.get("paperProbe"), dict) else {}
        if probe.get("eligibleForRecoveryStats") is True and isinstance(probe.get("virtualOrder"), dict):
            count += 1
    return count


def _evaluate_edge(
    entry_sample: dict[str, Any],
    future_samples: list[dict[str, Any]],
    *,
    candles: list[dict[str, Any]] | None = None,
    price_simulation: str = PRICE_SIMULATION_SAMPLE_CLOSE,
    allow_sample_close_fallback: bool = True,
) -> dict[str, Any] | None:
    order = entry_sample.get("virtualOrder") if isinstance(entry_sample.get("virtualOrder"), dict) else {}
    entry_price = _decimal_or_none(order.get("entryPrice"))
    vol = _decimal_or_none(order.get("vol"))
    contract_size = _decimal_or_none(order.get("contractSize"))
    estimated_taker_fee = _decimal_or_none(order.get("estimatedTakerFee")) or Decimal("0")
    stop_loss = _decimal_or_none(order.get("stopLossPrice"))
    take_profit = _decimal_or_none(order.get("takeProfitPrice"))
    side = str(entry_sample.get("side") or "")
    if entry_price is None or vol is None or contract_size is None:
        return None
    if entry_price <= 0 or vol <= 0 or contract_size <= 0:
        return None
    exit_sample, exit_price, exit_reason, exit_meta = _select_virtual_exit(
        side=side,
        entry_sample=entry_sample,
        future_samples=future_samples,
        stop_loss=stop_loss,
        take_profit=take_profit,
        candles=candles or [],
        price_simulation=price_simulation,
        allow_sample_close_fallback=allow_sample_close_fallback,
    )
    if exit_sample is None or exit_price is None:
        return None

    if side == "open-long":
        price_move = exit_price - entry_price
    elif side == "open-short":
        price_move = entry_price - exit_price
    else:
        return None
    move_bps = price_move / entry_price * Decimal("10000")
    gross_pnl = price_move * vol * contract_size
    rough_net = gross_pnl - (estimated_taker_fee * Decimal("2"))
    if rough_net > 0:
        outcome = "win"
    elif rough_net < 0:
        outcome = "loss"
    else:
        outcome = "flat"
    return {
        "entryEventId": entry_sample.get("eventId"),
        "exitEventId": exit_sample.get("eventId"),
        "entryTimestamp": entry_sample.get("timestamp"),
        "exitTimestamp": exit_sample.get("timestamp"),
        "side": side,
        "entryPrice": _decimal_text(entry_price),
        "exitPrice": _decimal_text(exit_price),
        "exitReason": exit_reason,
        "moveBps": _decimal_text(move_bps),
        "grossPnlUsdt": _decimal_text(gross_pnl),
        "roughNetPnlUsdt": _decimal_text(rough_net),
        "outcome": outcome,
        **exit_meta,
    }


def _select_virtual_exit(
    *,
    side: str,
    entry_sample: dict[str, Any],
    future_samples: list[dict[str, Any]],
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
    candles: list[dict[str, Any]],
    price_simulation: str,
    allow_sample_close_fallback: bool,
) -> tuple[dict[str, Any] | None, Decimal | None, str | None, dict[str, Any]]:
    if price_simulation == PRICE_SIMULATION_CANDLE_HIGH_LOW:
        candle_result = _select_candle_virtual_exit(
            side=side,
            entry_sample=entry_sample,
            future_samples=future_samples,
            stop_loss=stop_loss,
            take_profit=take_profit,
            candles=candles,
        )
        if candle_result is not None:
            return candle_result
        if not allow_sample_close_fallback:
            return None, None, None, _exit_meta(
                exit_source=PRICE_SIMULATION_CANDLE_HIGH_LOW,
                price_simulation=price_simulation,
                fallback_used=False,
            )

    return _select_sample_close_virtual_exit(
        side=side,
        future_samples=future_samples,
        stop_loss=stop_loss,
        take_profit=take_profit,
        price_simulation=price_simulation,
        fallback_used=price_simulation == PRICE_SIMULATION_CANDLE_HIGH_LOW,
    )


def _select_sample_close_virtual_exit(
    *,
    side: str,
    future_samples: list[dict[str, Any]],
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
    price_simulation: str,
    fallback_used: bool,
) -> tuple[dict[str, Any] | None, Decimal | None, str | None, dict[str, Any]]:
    valid_markets: list[tuple[dict[str, Any], Decimal]] = []
    for sample in future_samples:
        market = sample.get("market") if isinstance(sample.get("market"), dict) else {}
        price = _decimal_or_none(market.get("lastTradePrice"))
        if price is None or price <= 0:
            continue
        valid_markets.append((sample, price))
        meta = _exit_meta(
            exit_source=PRICE_SIMULATION_SAMPLE_CLOSE,
            price_simulation=price_simulation,
            fallback_used=fallback_used,
        )
        if side == "open-long":
            if stop_loss is not None and price <= stop_loss:
                return sample, stop_loss, "stop-loss", meta
            if take_profit is not None and price >= take_profit:
                return sample, take_profit, "take-profit", meta
        elif side == "open-short":
            if stop_loss is not None and price >= stop_loss:
                return sample, stop_loss, "stop-loss", meta
            if take_profit is not None and price <= take_profit:
                return sample, take_profit, "take-profit", meta

    if not valid_markets:
        return None, None, None, _exit_meta(
            exit_source=PRICE_SIMULATION_SAMPLE_CLOSE,
            price_simulation=price_simulation,
            fallback_used=fallback_used,
        )
    sample, price = valid_markets[-1]
    return sample, price, "horizon", _exit_meta(
        exit_source=PRICE_SIMULATION_SAMPLE_CLOSE,
        price_simulation=price_simulation,
        fallback_used=fallback_used,
    )


def _select_candle_virtual_exit(
    *,
    side: str,
    entry_sample: dict[str, Any],
    future_samples: list[dict[str, Any]],
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
    candles: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, Decimal | None, str | None, dict[str, Any]] | None:
    entry_ts = _as_int(entry_sample.get("timestamp"))
    horizon_ts = _as_int(future_samples[-1].get("timestamp")) if future_samples else None
    if entry_ts is None or horizon_ts is None:
        return None
    horizon_candles = [
        candle
        for candle in candles
        if (_as_int(candle.get("openTimeMs")) or 0) > entry_ts
        and (_as_int(candle.get("openTimeMs")) or 0) <= horizon_ts
    ]
    if not horizon_candles:
        return None

    for candle in horizon_candles:
        high = _decimal_or_none(candle.get("high"))
        low = _decimal_or_none(candle.get("low"))
        close = _decimal_or_none(candle.get("close"))
        if high is None or low is None or close is None or high <= 0 or low <= 0 or close <= 0:
            continue
        if side == "open-long":
            stop_hit = stop_loss is not None and low <= stop_loss
            take_hit = take_profit is not None and high >= take_profit
        elif side == "open-short":
            stop_hit = stop_loss is not None and high >= stop_loss
            take_hit = take_profit is not None and low <= take_profit
        else:
            return None

        exit_sample = _nearest_future_sample_for_candle(future_samples, candle)
        if stop_hit and take_hit:
            return (
                exit_sample,
                stop_loss,
                "stop-loss",
                _exit_meta(
                    exit_source=PRICE_SIMULATION_CANDLE_HIGH_LOW,
                    price_simulation=PRICE_SIMULATION_CANDLE_HIGH_LOW,
                    fallback_used=False,
                    exit_candle=candle,
                    intra_candle_ambiguous=True,
                ),
            )
        if stop_hit:
            return (
                exit_sample,
                stop_loss,
                "stop-loss",
                _exit_meta(
                    exit_source=PRICE_SIMULATION_CANDLE_HIGH_LOW,
                    price_simulation=PRICE_SIMULATION_CANDLE_HIGH_LOW,
                    fallback_used=False,
                    exit_candle=candle,
                ),
            )
        if take_hit:
            return (
                exit_sample,
                take_profit,
                "take-profit",
                _exit_meta(
                    exit_source=PRICE_SIMULATION_CANDLE_HIGH_LOW,
                    price_simulation=PRICE_SIMULATION_CANDLE_HIGH_LOW,
                    fallback_used=False,
                    exit_candle=candle,
                ),
            )

    last_candle = horizon_candles[-1]
    close = _decimal_or_none(last_candle.get("close"))
    if close is None or close <= 0:
        return None
    return (
        _nearest_future_sample_for_candle(future_samples, last_candle),
        close,
        "horizon",
        _exit_meta(
            exit_source=PRICE_SIMULATION_CANDLE_HIGH_LOW,
            price_simulation=PRICE_SIMULATION_CANDLE_HIGH_LOW,
            fallback_used=False,
            exit_candle=last_candle,
        ),
    )


def _nearest_future_sample_for_candle(
    future_samples: list[dict[str, Any]],
    candle: dict[str, Any],
) -> dict[str, Any] | None:
    candle_ts = _as_int(candle.get("openTimeMs")) or 0
    for sample in future_samples:
        sample_ts = _as_int(sample.get("timestamp")) or 0
        if sample_ts >= candle_ts:
            return sample
    return future_samples[-1] if future_samples else None


def _exit_meta(
    *,
    exit_source: str,
    price_simulation: str,
    fallback_used: bool,
    exit_candle: dict[str, Any] | None = None,
    intra_candle_ambiguous: bool = False,
) -> dict[str, Any]:
    return {
        "exitSource": exit_source,
        "priceSimulation": price_simulation,
        "fallbackUsed": fallback_used,
        "intraCandleAmbiguous": intra_candle_ambiguous,
        "ambiguityPolicy": "conservative-stop-first" if intra_candle_ambiguous else None,
        "exitCandle": exit_candle,
    }


def _edge_side_stats(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    for side in sorted({str(item.get("side") or "unknown") for item in evaluations}):
        side_items = [item for item in evaluations if str(item.get("side") or "unknown") == side]
        wins = sum(1 for item in side_items if item["outcome"] == "win")
        losses = sum(1 for item in side_items if item["outcome"] == "loss")
        flats = sum(1 for item in side_items if item["outcome"] == "flat")
        pnl_values = [_decimal_or_none(item.get("roughNetPnlUsdt")) or Decimal("0") for item in side_items]
        bps_values = [_decimal_or_none(item.get("moveBps")) or Decimal("0") for item in side_items]
        stats[side] = {
            "evaluableCount": len(side_items),
            "winCount": wins,
            "lossCount": losses,
            "flatCount": flats,
            "winRate": round(wins / len(side_items), 6) if side_items else None,
            "avgMoveBps": _decimal_text(sum(bps_values, Decimal("0")) / len(bps_values)) if bps_values else None,
            "totalRoughNetPnlUsdt": _decimal_text(sum(pnl_values, Decimal("0"))) if pnl_values else "0",
        }
    return stats


def _normalize_candles(candles: list[Any] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for candle in candles or []:
        if hasattr(candle, "to_dict"):
            raw = candle.to_dict()
        elif isinstance(candle, dict):
            raw = candle
        else:
            continue

        open_time_ms = _as_int(
            raw.get("openTimeMs")
            or raw.get("open_time_ms")
            or raw.get("openTime")
            or raw.get("time")
        )
        if open_time_ms is None:
            continue
        high = _decimal_or_none(raw.get("high"))
        low = _decimal_or_none(raw.get("low"))
        close = _decimal_or_none(raw.get("close"))
        open_price = _decimal_or_none(raw.get("open"))
        if high is None or low is None or close is None or open_price is None:
            continue
        normalized.append(
            {
                "symbol": str(raw.get("symbol") or "").upper() or None,
                "interval": raw.get("interval"),
                "exchangeInterval": raw.get("exchangeInterval") or raw.get("exchange_interval"),
                "openTimeMs": open_time_ms,
                "closeTimeMs": _as_int(raw.get("closeTimeMs") or raw.get("close_time_ms")),
                "open": _decimal_text(open_price),
                "high": _decimal_text(high),
                "low": _decimal_text(low),
                "close": _decimal_text(close),
                "volume": _decimal_text(_decimal_or_none(raw.get("volume"))),
                "quoteVolume": _decimal_text(
                    _decimal_or_none(raw.get("quoteVolume") or raw.get("quote_volume"))
                ),
                "source": raw.get("source"),
            }
        )
    return sorted(normalized, key=lambda row: (_as_int(row.get("openTimeMs")) or 0, str(row.get("interval") or "")))


def _candle_interval_summary(candles: list[dict[str, Any]]) -> str | None:
    values = sorted({str(candle.get("interval")) for candle in candles if candle.get("interval")})
    if not values:
        return None
    return values[0] if len(values) == 1 else ",".join(values)


def _candle_source_summary(candles: list[dict[str, Any]]) -> str | None:
    values = sorted({str(candle.get("source")) for candle in candles if candle.get("source")})
    if not values:
        return None
    return values[0] if len(values) == 1 else "mixed"


def _paper_ledger_warnings(
    *,
    price_simulation: str,
    candle_count: int,
    allow_sample_close_fallback: bool,
) -> list[str]:
    warnings = ["paper ledger is read-only and never submits exchange orders"]
    if price_simulation == PRICE_SIMULATION_CANDLE_HIGH_LOW:
        warnings.append("paper ledger uses candle high/low simulation with conservative stop-first ambiguity policy")
        if candle_count <= 0:
            warnings.append("paper ledger has no candles available for high/low simulation")
        if allow_sample_close_fallback:
            warnings.append("paper ledger falls back to sample-close when candle coverage is missing")
    else:
        warnings.append("paper ledger is sample-close only; intra-sample high/low path is not observed")
    return warnings


def _paper_performance_gate(
    performance_report: dict[str, Any] | None,
    *,
    min_closed_count: int,
    min_win_rate: float,
    min_profit_factor: float,
    max_drawdown_pct: float,
    max_consecutive_losses: int,
) -> dict[str, Any]:
    thresholds = {
        "minClosedCount": min_closed_count,
        "minWinRate": min_win_rate,
        "minProfitFactor": min_profit_factor,
        "maxDrawdownPct": max_drawdown_pct,
        "maxConsecutiveLosses": max_consecutive_losses,
        "requireEndingEquityAboveInitial": True,
        "requirePositiveExpectancy": True,
        "requireNoOpenOrders": True,
        "requireRecentEquityImproving": True,
        "minRecentEquityWindow": 5,
    }
    if not isinstance(performance_report, dict):
        return {
            "readyForLocalPaperPerformance": False,
            "thresholds": thresholds,
            "observed": {},
            "blockers": ["paper performance report is missing"],
            "liveOrderSubmitted": False,
        }

    closed_count = _as_int(performance_report.get("closedCount")) or 0
    evaluable_closed_count = _as_int(performance_report.get("evaluableClosedCount"))
    if evaluable_closed_count is None:
        evaluable_closed_count = closed_count
    unpriced_closed_count = _as_int(performance_report.get("unpricedClosedCount")) or 0
    skipped_closed_count = _as_int(performance_report.get("skippedClosedCount")) or unpriced_closed_count
    open_count = _as_int(performance_report.get("openCount")) or 0
    equity_trend = performance_report.get("equityTrend") if isinstance(performance_report.get("equityTrend"), dict) else {}
    consecutive_losses = _as_int(performance_report.get("consecutiveLosses")) or 0
    initial_equity = _decimal_or_none(performance_report.get("initialEquity"))
    ending_equity = _decimal_or_none(performance_report.get("endingEquity"))
    win_rate = _decimal_or_none(performance_report.get("winRate"))
    profit_factor = _decimal_or_none(performance_report.get("profitFactor"))
    max_drawdown = _decimal_or_none(performance_report.get("maxDrawdown"))
    max_drawdown_pct_value = _decimal_or_none(performance_report.get("maxDrawdownPct"))
    expectancy = _decimal_or_none(performance_report.get("expectancy"))

    blockers: list[str] = []
    if performance_report.get("liveOrderSubmitted") is not False:
        blockers.append("paper performance report liveOrderSubmitted is not false")
    if evaluable_closed_count < min_closed_count:
        blockers.append(f"performance evaluable closed count {evaluable_closed_count} below gate {min_closed_count}")
    if unpriced_closed_count > 0:
        blockers.append(f"performance has {unpriced_closed_count} unpriced closed orders")
    if skipped_closed_count > 0:
        blockers.append(f"performance has {skipped_closed_count} skipped closed orders")
    if open_count != 0:
        blockers.append(f"performance open count {open_count} must be zero for readiness snapshot")
    if initial_equity is None or initial_equity <= 0:
        blockers.append("performance initial equity is missing or non-positive")
    if ending_equity is None:
        blockers.append("performance ending equity is missing")
    elif initial_equity is not None and ending_equity <= initial_equity:
        blockers.append(f"performance ending equity {ending_equity} is not above initial equity {initial_equity}")
    if win_rate is None:
        blockers.append("performance win rate is missing")
    elif win_rate < Decimal(str(min_win_rate)):
        blockers.append(f"performance win rate {win_rate} below gate {min_win_rate}")
    if profit_factor is None:
        blockers.append("performance profit factor is missing")
    elif profit_factor < Decimal(str(min_profit_factor)):
        blockers.append(f"performance profit factor {profit_factor} below gate {min_profit_factor}")
    if max_drawdown_pct_value is None:
        blockers.append("performance max drawdown pct is missing")
    elif max_drawdown_pct_value > Decimal(str(max_drawdown_pct)):
        blockers.append(f"performance max drawdown pct {max_drawdown_pct_value} above gate {max_drawdown_pct}")
    if expectancy is None:
        blockers.append("performance expectancy is missing")
    elif expectancy <= 0:
        blockers.append(f"performance expectancy {expectancy} is not positive")
    if consecutive_losses > max_consecutive_losses:
        blockers.append(f"performance consecutive losses {consecutive_losses} above gate {max_consecutive_losses}")
    recent_count = _as_int(equity_trend.get("count")) or 0
    recent_window = _as_int(equity_trend.get("window")) or 5
    recent_change = _decimal_or_none(equity_trend.get("recentEquityChange"))
    recent_slope = _decimal_or_none(equity_trend.get("recentEquitySlope"))
    if not equity_trend:
        blockers.append("performance recent equity trend is missing")
    elif recent_count < recent_window:
        blockers.append(f"performance recent equity trend count {recent_count} below window {recent_window}")
    elif equity_trend.get("recentEquityImproving") is not True:
        blockers.append("performance recent equity trend is not improving")
    if equity_trend and recent_change is not None and recent_change <= 0:
        blockers.append(f"performance recent equity change {recent_change} is not positive")
    if equity_trend and recent_slope is not None and recent_slope <= 0:
        blockers.append(f"performance recent equity slope {recent_slope} is not positive")

    return {
        "readyForLocalPaperPerformance": not blockers,
        "thresholds": thresholds,
        "observed": {
            "initialEquity": _decimal_text(initial_equity),
            "endingEquity": _decimal_text(ending_equity),
            "netPnlUsdt": _decimal_text(ending_equity - initial_equity)
            if initial_equity is not None and ending_equity is not None
            else None,
            "closedCount": closed_count,
            "evaluableClosedCount": evaluable_closed_count,
            "unpricedClosedCount": unpriced_closed_count,
            "skippedClosedCount": skipped_closed_count,
            "openCount": open_count,
            "winRate": performance_report.get("winRate"),
            "profitFactor": performance_report.get("profitFactor"),
            "maxDrawdown": _decimal_text(max_drawdown),
            "maxDrawdownPct": performance_report.get("maxDrawdownPct"),
            "expectancy": _decimal_text(expectancy),
            "consecutiveLosses": consecutive_losses,
            "equityTrend": equity_trend,
        },
        "blockers": blockers,
        "liveOrderSubmitted": False,
    }


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _count_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "")
        if value:
            counts[value] = counts.get(value, 0) + 1
    return counts
