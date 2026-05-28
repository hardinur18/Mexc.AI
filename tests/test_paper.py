from mexc_futures_engine.paper import build_paper_audit_report
from mexc_futures_engine.paper import build_paper_decision_report
from mexc_futures_engine.paper import build_paper_edge_report
from mexc_futures_engine.paper import build_paper_ledger_report
from mexc_futures_engine.paper import build_paper_readiness_report
from mexc_futures_engine.paper import apply_paper_side_quality_governor
from mexc_futures_engine.paper import summarize_paper_decision_report


def test_paper_decision_would_open_from_safe_handoff():
    report = build_paper_decision_report(
        state_handoff=_handoff(side="open-long", confidence=0.72, preflight_allowed=True),
        min_confidence=0.65,
        max_margin_fraction=0.75,
    )

    assert report["wouldOpen"] is True
    assert report["action"] == "paper-open-long"
    assert report["liveOrderSubmitted"] is False
    assert report["virtualOrder"]["notional"] == "8"
    assert report["virtualOrder"]["requiredMargin"] == "4"
    assert report["market"]["lastTradePrice"] == "80010"
    assert report["paperGates"]["observed"]["depthImbalanceTop10"] == "0.14"


def test_paper_decision_can_use_paper_equity_instead_of_live_balance():
    report = build_paper_decision_report(
        state_handoff=_handoff(
            side="open-long",
            confidence=0.72,
            preflight_allowed=False,
            free_balance="0.00000001",
            preflight_reasons=["available balance 0.00000001 is below estimated margin 4.00000000"],
        ),
        min_confidence=0.65,
        max_margin_fraction=0.75,
        paper_equity_usdt="6.00000001",
    )

    assert report["wouldOpen"] is True
    assert report["virtualOrder"]["requiredMargin"] == "4"
    assert report["account"]["liveFreeBalance"] == "0.00000001"
    assert report["account"]["paperFreeBalance"] == "6.00000001"
    assert report["account"]["paperEquityOverrideEnabled"] is True
    assert any("live-balance preflight reason isolated" in warning for warning in report["warnings"])
    assert "strategy preflight is not allowed" not in report["blockers"]


def test_paper_decision_holds_when_confidence_low():
    report = build_paper_decision_report(
        state_handoff=_handoff(side="open-short", confidence=0.52, preflight_allowed=True),
        min_confidence=0.65,
    )

    assert report["wouldOpen"] is False
    assert report["action"] == "hold"
    assert any("below 0.65" in blocker for blocker in report["blockers"])


def test_paper_decision_holds_when_active_order_exists():
    handoff = _handoff(side="open-long", confidence=0.72, preflight_allowed=True)
    handoff["stateCache"]["account"]["activeOrderCount"] = 1
    handoff["strategyHandoff"]["safeToOpenNewPositionPreflight"] = False

    report = build_paper_decision_report(state_handoff=handoff)

    assert report["wouldOpen"] is False
    assert "strategy handoff is not safe for new-position preflight" in report["blockers"]
    assert "existing active order count is 1" in report["blockers"]


def test_paper_decision_holds_when_depth_gate_fails():
    handoff = _handoff(side="open-long", confidence=0.72, preflight_allowed=True)
    handoff["strategyHandoff"]["strategyPreview"]["metrics"]["depthImbalanceTop10"] = "0.09"

    report = build_paper_decision_report(state_handoff=handoff, min_depth_imbalance=0.12)

    assert report["wouldOpen"] is False
    assert "depth imbalance 0.09 below long gate 0.12" in report["blockers"]


def test_paper_decision_holds_when_required_market_metric_missing():
    handoff = _handoff(side="open-long", confidence=0.72, preflight_allowed=True)
    handoff["strategyHandoff"]["strategyPreview"]["metrics"].pop("depthImbalanceTop10")

    report = build_paper_decision_report(state_handoff=handoff)

    assert report["wouldOpen"] is False
    assert "depth imbalance gate missing strategy metric" in report["blockers"]


def test_paper_decision_uses_reported_spread_bps_when_bid_ask_missing():
    handoff = _handoff(side="open-long", confidence=0.72, preflight_allowed=True)
    metrics = handoff["strategyHandoff"]["strategyPreview"]["metrics"]
    metrics.pop("bid")
    metrics.pop("ask")
    metrics.pop("spread")
    metrics["spreadBps"] = "1.2"

    report = build_paper_decision_report(state_handoff=handoff, max_spread_bps=2.5)

    assert report["wouldOpen"] is True
    assert report["paperGates"]["observed"]["spreadBps"] == "1.2"


def test_paper_decision_holds_when_market_snapshot_is_stale():
    handoff = _handoff(side="open-long", confidence=0.72, preflight_allowed=True)
    handoff["stateCache"]["market"]["lastTrade"]["tsEvent"] = 1
    handoff["stateCache"]["market"]["bookDeltas"]["tsEvent"] = 1

    report = build_paper_decision_report(state_handoff=handoff, max_market_age_seconds=60)

    assert report["wouldOpen"] is False
    assert any("last trade market age" in blocker for blocker in report["blockers"])
    assert any("order book market age" in blocker for blocker in report["blockers"])


def test_paper_decision_holds_when_trend_filter_blocks_side():
    report = build_paper_decision_report(
        state_handoff=_handoff(side="open-short", confidence=0.72, preflight_allowed=True),
        trend_filter={
            "ok": True,
            "source": "test",
            "trend": "bullish",
            "candleCount": 20,
            "shortPeriod": 5,
            "longPeriod": 20,
            "latestCandleAgeSeconds": 10,
            "observed": {"shortEma": "101", "longEma": "100"},
            "blockers": [],
            "warnings": [],
        },
    )

    assert report["wouldOpen"] is False
    assert "trend filter blocks short: trend is bullish" in report["blockers"]
    assert report["trendFilter"]["enabled"] is True


def test_paper_decision_holds_when_volatility_filter_blocks_range():
    report = build_paper_decision_report(
        state_handoff=_handoff(side="open-long", confidence=0.72, preflight_allowed=True),
        volatility_filter={
            "ok": False,
            "source": "test",
            "regime": "volatile",
            "candleCount": 12,
            "validCandleRangeCount": 12,
            "latestCandleAgeSeconds": 8,
            "thresholds": {"maxAvgRangeBps": 50},
            "observed": {"avgRangeBps": "62", "latestRangeBps": "80"},
            "blockers": ["average candle range 62 above ceiling 50"],
            "warnings": [],
        },
    )

    assert report["wouldOpen"] is False
    assert "volatility filter not ready: average candle range 62 above ceiling 50" in report["blockers"]
    assert report["volatilityFilter"]["enabled"] is True
    assert report["regimeFilter"]["regime"] == "volatile"
    assert report["liveOrderSubmitted"] is False


def test_paper_decision_summary_omits_inputs():
    report = build_paper_decision_report(
        state_handoff=_handoff(side="open-long", confidence=0.72, preflight_allowed=True),
        include_raw=True,
    )

    summary = summarize_paper_decision_report(report)

    assert "inputs" in report
    assert "inputs" not in summary
    assert summary["wouldOpen"] is True
    assert summary["volatilityFilter"]["enabled"] is False
    assert summary["regimeFilter"]["enabled"] is False


def test_paper_audit_counts_actions_and_blockers():
    audit = build_paper_audit_report(
        [
            _event(3, "paper-open-long", True, "open-long"),
            _event(2, "hold", False, "hold", blockers=["strategy side is not actionable: hold"]),
            _event(1, "paper-open-long", True, "open-long"),
        ],
        symbol="BTC_USDT",
        min_samples=3,
    )

    assert audit["sampleCount"] == 3
    assert audit["readyForPaperReview"] is True
    assert audit["wouldOpenCount"] == 2
    assert audit["actionCounts"]["paper-open-long"] == 2
    assert audit["blockerCounts"]["strategy side is not actionable: hold"] == 1
    assert audit["consecutiveWouldOpen"] == 1
    assert audit["edgePreview"]["evaluableCount"] == 0
    assert audit["paperQualityGate"]["readyForLiveCandidate"] is False
    assert "edge win rate is not available" in audit["paperQualityGate"]["blockers"]


def test_paper_audit_sorts_unordered_events_before_latest_and_consecutive_stats():
    audit = build_paper_audit_report(
        [
            _event(1, "paper-open-long", True, "open-long"),
            _event(3, "paper-open-long", True, "open-long"),
            _event(2, "paper-open-long", True, "open-long"),
        ],
        symbol="BTC_USDT",
        min_samples=3,
    )

    assert audit["latestSample"]["eventId"] == 3
    assert audit["consecutiveWouldOpen"] == 3


def test_paper_edge_report_marks_forward_win():
    edge = build_paper_edge_report(
        [
            _event(2, "hold", False, "hold", market_price="80100"),
            _event(1, "paper-open-long", True, "open-long", market_price="80000"),
        ],
        symbol="BTC_USDT",
        horizon_samples=1,
        min_evaluable=1,
    )

    assert edge["readyForEdgeReview"] is True
    assert edge["evaluableCount"] == 1
    assert edge["winCount"] == 1
    assert edge["sideStats"]["open-long"]["winRate"] == 1.0
    assert edge["evaluations"][0]["moveBps"] == "12.5"
    assert edge["evaluations"][0]["exitReason"] == "horizon"
    assert edge["evaluations"][0]["roughNetPnlUsdt"] == "0.0084"


def test_paper_edge_report_marks_take_profit_before_horizon_exit():
    edge = build_paper_edge_report(
        [
            _event(2, "hold", False, "hold", market_price="80200"),
            _event(
                1,
                "paper-open-long",
                True,
                "open-long",
                market_price="80000",
                stop_loss_price="79900",
                take_profit_price="80100",
            ),
        ],
        symbol="BTC_USDT",
        horizon_samples=1,
        min_evaluable=1,
    )

    assert edge["evaluations"][0]["exitReason"] == "take-profit"
    assert edge["evaluations"][0]["exitPrice"] == "80100"
    assert edge["evaluations"][0]["roughNetPnlUsdt"] == "0.0084"


def test_paper_ledger_builds_lifecycle_from_virtual_entries():
    ledger = build_paper_ledger_report(
        [
            _event(3, "paper-open-long", True, "open-long", market_price="80150"),
            _event(2, "hold", False, "hold", market_price="80200"),
            _event(
                1,
                "paper-open-long",
                True,
                "open-long",
                market_price="80000",
                take_profit_price="80100",
            ),
        ],
        symbol="BTC_USDT",
        horizon_samples=1,
    )

    assert ledger["orderCount"] == 2
    assert ledger["statusCounts"]["TAKE_PROFIT"] == 1
    assert ledger["statusCounts"]["OPEN"] == 1
    assert ledger["orders"][0]["status"] == "TAKE_PROFIT"
    assert ledger["orders"][0]["lifecycle"] == ["NEW", "FILLED", "TAKE_PROFIT"]
    assert ledger["orders"][0]["exit"]["exitReason"] == "take-profit"
    assert ledger["orders"][1]["status"] == "OPEN"
    assert ledger["orders"][1]["liveOrderSubmitted"] is False


def test_paper_ledger_can_exit_from_candle_high_low_take_profit():
    ledger = build_paper_ledger_report(
        [
            _event(2, "hold", False, "hold", market_price="80050"),
            _event(
                1,
                "paper-open-long",
                True,
                "open-long",
                market_price="80000",
                stop_loss_price="79900",
                take_profit_price="80100",
            ),
        ],
        symbol="BTC_USDT",
        horizon_samples=1,
        price_simulation="candle-high-low",
        candles=[_candle(1500, high="80120", low="79980", close="80050")],
    )

    order = ledger["orders"][0]
    assert ledger["priceSimulation"] == "candle-high-low"
    assert order["status"] == "TAKE_PROFIT"
    assert order["exit"]["exitSource"] == "candle-high-low"
    assert order["exit"]["exitPrice"] == "80100"
    assert order["exit"]["exitCandle"]["high"] == "80120"


def test_paper_ledger_marks_same_candle_stop_and_take_profit_as_ambiguous_stop_first():
    ledger = build_paper_ledger_report(
        [
            _event(2, "hold", False, "hold", market_price="80050"),
            _event(
                1,
                "paper-open-long",
                True,
                "open-long",
                market_price="80000",
                stop_loss_price="79950",
                take_profit_price="80100",
            ),
        ],
        symbol="BTC_USDT",
        horizon_samples=1,
        price_simulation="candle-high-low",
        candles=[_candle(1500, high="80120", low="79900", close="80050")],
    )

    order = ledger["orders"][0]
    assert order["status"] == "STOPPED"
    assert order["exit"]["exitReason"] == "stop-loss"
    assert order["exit"]["intraCandleAmbiguous"] is True
    assert order["exit"]["ambiguityPolicy"] == "conservative-stop-first"


def test_paper_ledger_falls_back_to_sample_close_when_candles_missing():
    ledger = build_paper_ledger_report(
        [
            _event(2, "hold", False, "hold", market_price="80200"),
            _event(
                1,
                "paper-open-long",
                True,
                "open-long",
                market_price="80000",
                stop_loss_price="79900",
                take_profit_price="80100",
            ),
        ],
        symbol="BTC_USDT",
        horizon_samples=1,
        price_simulation="candle-high-low",
        candles=[],
    )

    order = ledger["orders"][0]
    assert order["status"] == "TAKE_PROFIT"
    assert order["exit"]["exitSource"] == "sample-close"
    assert order["exit"]["fallbackUsed"] is True


def test_paper_ledger_can_include_probe_candidates_without_marking_live():
    ledger = build_paper_ledger_report(
        [
            _event(2, "hold", False, "hold", market_price="79800"),
            _event(1, "hold", False, "open-short", market_price="80000", paper_probe=True),
        ],
        symbol="BTC_USDT",
        horizon_samples=1,
        include_probes=True,
    )

    assert ledger["orderCount"] == 1
    assert ledger["sourceCounts"]["paper-probe"] == 1
    assert ledger["orders"][0]["sourceType"] == "paper-probe"
    assert ledger["orders"][0]["status"] == "EXPIRED"
    assert ledger["liveOrderSubmitted"] is False


def test_paper_ledger_carries_entry_metrics_from_decision_filters():
    ledger = build_paper_ledger_report(
        [
            _event(2, "hold", False, "hold", market_price="79900"),
            _event(
                1,
                "paper-open-short",
                True,
                "open-short",
                market_price="80000",
                paper_gates={
                    "observed": {
                        "depthImbalanceTop10": "-0.42",
                        "spreadBps": "0.02",
                        "fundingRate": "0.00002",
                    }
                },
                volatility_filter={
                    "observed": {
                        "avgRangeBps": "8",
                        "latestRangeBps": "6",
                    }
                },
            ),
        ],
        symbol="BTC_USDT",
        horizon_samples=1,
    )

    assert ledger["orders"][0]["entryMetrics"] == {
        "depthImbalanceTop10": "-0.42",
        "spreadBps": "0.02",
        "fundingRate": "0.00002",
        "avgRangeBps": "8",
        "latestRangeBps": "6",
    }


def test_paper_audit_quality_gate_allows_positive_edge():
    audit = build_paper_audit_report(
        [
            _event(3, "hold", False, "hold", market_price="80200"),
            _event(2, "paper-open-long", True, "open-long", market_price="80100"),
            _event(1, "paper-open-long", True, "open-long", market_price="80000"),
        ],
        symbol="BTC_USDT",
        min_samples=3,
        min_edge_evaluable=2,
        min_edge_win_rate=0.5,
        policy_allowed_sides={"open-long"},
    )

    assert audit["paperQualityGate"]["readyForLiveCandidate"] is True
    assert audit["paperQualityGate"]["edgeWinRate"] == 1.0
    assert audit["paperQualityGate"]["blockers"] == []


def test_paper_side_quality_governor_pauses_bad_side():
    decision = build_paper_decision_report(
        state_handoff=_handoff(side="open-long", confidence=0.72, preflight_allowed=True),
    )
    audit = build_paper_audit_report(
        [
            _event(3, "hold", False, "hold", market_price="79900"),
            _event(2, "paper-open-long", True, "open-long", market_price="79950"),
            _event(1, "paper-open-long", True, "open-long", market_price="80000"),
        ],
        symbol="BTC_USDT",
        min_samples=3,
        edge_horizon_samples=1,
        min_edge_evaluable=1,
        min_side_edge_evaluable=1,
        min_side_edge_win_rate=0.5,
    )

    governed = apply_paper_side_quality_governor(decision, audit)

    assert governed["wouldOpen"] is False
    assert governed["action"] == "hold"
    assert governed["virtualOrder"] is None
    assert governed["paperProbe"]["eligibleForRecoveryStats"] is True
    assert governed["paperProbe"]["virtualOrder"]["entryPrice"] == "80000"
    assert governed["paperQualityGovernor"]["action"] == "pause-side"
    assert any("paper side quality paused open-long" in blocker for blocker in governed["blockers"])


def test_paper_audit_policy_gate_can_ignore_disabled_bad_side():
    audit = build_paper_audit_report(
        [
            _event(4, "hold", False, "hold", market_price="79900"),
            _event(3, "paper-open-short", True, "open-short", market_price="80000"),
            _event(2, "hold", False, "hold", market_price="79900"),
            _event(1, "paper-open-long", True, "open-long", market_price="80000"),
        ],
        symbol="BTC_USDT",
        min_samples=4,
        edge_horizon_samples=1,
        min_edge_evaluable=2,
        min_edge_win_rate=0.55,
        min_side_edge_evaluable=1,
        min_side_edge_win_rate=0.5,
        policy_allowed_sides={"open-short"},
    )

    global_gate = audit["paperQualityGate"]
    policy_gate = global_gate["strategyPolicyQualityGate"]

    assert global_gate["readyForLiveCandidate"] is False
    assert policy_gate["readyForCurrentStrategyPaperCandidate"] is True
    assert policy_gate["readyForCurrentStrategyLiveCandidate"] is True
    assert policy_gate["allowedSides"] == ["open-short"]
    assert policy_gate["winRate"] == 1.0
    assert policy_gate["totalRoughNetPnlUsdt"] == "0.0084"


def test_paper_side_recovery_requires_recent_positive_window():
    audit = build_paper_audit_report(
        [
            _event(4, "hold", False, "hold", market_price="79900"),
            _event(3, "paper-open-short", True, "open-short", market_price="80000"),
            _event(2, "hold", False, "hold", market_price="80100"),
            _event(1, "paper-open-short", True, "open-short", market_price="80000"),
        ],
        symbol="BTC_USDT",
        min_samples=4,
        edge_horizon_samples=1,
        min_edge_evaluable=1,
        min_side_edge_evaluable=1,
        min_side_edge_win_rate=0.55,
        recovery_window_evaluable=2,
        recovery_min_win_rate=0.55,
        policy_allowed_sides={"open-short"},
    )

    short_gate = audit["paperQualityGate"]["sideGates"]["open-short"]

    assert short_gate["pauseNewPaperEntries"] is True
    assert short_gate["recovery"]["readyForRecovery"] is False
    assert short_gate["recovery"]["winRate"] == 0.5


def test_paper_side_recovery_unpauses_after_recent_positive_window():
    audit = build_paper_audit_report(
        [
            _event(6, "hold", False, "hold", market_price="79800"),
            _event(5, "paper-open-short", True, "open-short", market_price="80000"),
            _event(4, "hold", False, "hold", market_price="79800"),
            _event(3, "paper-open-short", True, "open-short", market_price="80000"),
            _event(2, "hold", False, "hold", market_price="80500"),
            _event(1, "paper-open-short", True, "open-short", market_price="80000"),
        ],
        symbol="BTC_USDT",
        min_samples=6,
        edge_horizon_samples=1,
        min_edge_evaluable=1,
        min_side_edge_evaluable=1,
        min_side_edge_win_rate=0.55,
        recovery_window_evaluable=2,
        recovery_min_win_rate=0.55,
        policy_allowed_sides={"open-short"},
    )

    short_gate = audit["paperQualityGate"]["sideGates"]["open-short"]
    policy_gate = audit["paperQualityGate"]["strategyPolicyQualityGate"]

    assert short_gate["readyForLiveCandidate"] is False
    assert short_gate["pauseNewPaperEntries"] is False
    assert short_gate["recovery"]["readyForRecovery"] is True
    assert policy_gate["readyForCurrentStrategyPaperCandidate"] is True
    assert policy_gate["readyForCurrentStrategyLiveCandidate"] is False


def test_paper_side_recovery_can_use_governor_probe_samples():
    audit = build_paper_audit_report(
        [
            _event(6, "hold", False, "open-short", market_price="79800"),
            _event(5, "hold", False, "open-short", market_price="80000", paper_probe=True),
            _event(4, "hold", False, "open-short", market_price="79800"),
            _event(3, "hold", False, "open-short", market_price="80000", paper_probe=True),
            _event(2, "hold", False, "hold", market_price="80500"),
            _event(1, "paper-open-short", True, "open-short", market_price="80000"),
        ],
        symbol="BTC_USDT",
        min_samples=6,
        edge_horizon_samples=1,
        min_edge_evaluable=1,
        min_side_edge_evaluable=1,
        min_side_edge_win_rate=0.55,
        recovery_window_evaluable=2,
        recovery_min_win_rate=0.55,
        policy_allowed_sides={"open-short"},
    )

    short_gate = audit["paperQualityGate"]["sideGates"]["open-short"]

    assert audit["paperQualityGate"]["recoveryProbeCount"] == 2
    assert short_gate["readyForLiveCandidate"] is False
    assert short_gate["pauseNewPaperEntries"] is False
    assert short_gate["recovery"]["readyForRecovery"] is True
    assert short_gate["recovery"]["winRate"] == 1.0


def test_paper_audit_blocks_stale_samples_and_reports_rolling_windows():
    audit = build_paper_audit_report(
        [
            _event(4, "hold", False, "hold", market_price="79900"),
            _event(3, "paper-open-long", True, "open-long", market_price="80000"),
            _event(2, "hold", False, "hold", market_price="80100"),
            _event(1, "paper-open-long", True, "open-long", market_price="80000"),
        ],
        symbol="BTC_USDT",
        min_samples=4,
        edge_horizon_samples=1,
        min_edge_evaluable=1,
        min_edge_win_rate=0.5,
        min_side_edge_evaluable=1,
        max_sample_age_seconds=1,
        rolling_windows=(2,),
    )

    assert audit["latestSampleAgeSeconds"] is not None
    assert audit["paperQualityGate"]["readyForLiveCandidate"] is False
    assert any("paper audit freshness" in blocker for blocker in audit["paperQualityGate"]["blockers"])
    assert audit["rollingWindows"]["configured"] == [2]


def test_paper_readiness_scores_safety_and_blocks_unproven_edge():
    audit = build_paper_audit_report(
        [
            _event(4, "hold", False, "hold", market_price="79900"),
            _event(3, "paper-open-long", True, "open-long", market_price="80000"),
            _event(2, "hold", False, "hold", market_price="79900"),
            _event(1, "paper-open-long", True, "open-long", market_price="80000"),
        ],
        symbol="BTC_USDT",
        min_samples=4,
        edge_horizon_samples=1,
        min_edge_evaluable=1,
        min_side_edge_evaluable=1,
        policy_allowed_sides={"open-long"},
        max_sample_age_seconds=10**12,
        rolling_windows=(4,),
    )
    readiness = build_paper_readiness_report(
        audit_report=audit,
        safety_report={
            "ok": True,
            "readyForReadonly": True,
            "readyForLive": False,
            "liveTradingEnabled": False,
            "killSwitchActive": False,
        },
        target_sample_count=10,
    )

    assert readiness["readyForLive"] is False
    assert readiness["liveOrderSubmitted"] is False
    assert readiness["readyForLocalPaperStrategy"] is False
    assert readiness["localPaperReadinessPercent"] > 0
    assert any(component["name"] == "paper-sample-volume" for component in readiness["components"])
    assert any("target sample count" in action for action in readiness["nextActions"])


def test_paper_readiness_blocks_when_performance_is_negative_even_if_audit_is_positive():
    audit = build_paper_audit_report(
        [
            _event(4, "hold", False, "hold", market_price="80200"),
            _event(3, "hold", False, "hold", market_price="80200"),
            _event(2, "paper-open-long", True, "open-long", market_price="80100"),
            _event(1, "paper-open-long", True, "open-long", market_price="80000"),
        ],
        symbol="BTC_USDT",
        min_samples=4,
        edge_horizon_samples=1,
        min_edge_evaluable=2,
        min_edge_win_rate=0.5,
        min_side_edge_evaluable=1,
        policy_allowed_sides={"open-long"},
        max_sample_age_seconds=10**12,
        rolling_windows=(4,),
    )
    readiness = build_paper_readiness_report(
        audit_report=audit,
        safety_report={
            "ok": True,
            "readyForReadonly": True,
            "readyForLive": False,
            "liveTradingEnabled": False,
            "killSwitchActive": False,
        },
        target_sample_count=4,
        performance_report={
            "mode": "paper-performance-read-only",
            "initialEquity": "100",
            "endingEquity": "99",
            "closedCount": 50,
            "openCount": 0,
            "winRate": 0.6,
            "profitFactor": 0.9,
            "maxDrawdownPct": 0.01,
            "expectancy": "-0.02",
            "consecutiveLosses": 2,
            "liveOrderSubmitted": False,
        },
    )

    performance_component = [
        component for component in readiness["components"] if component["name"] == "paper-performance-quality"
    ][0]
    assert readiness["readyForLocalPaperStrategy"] is False
    assert readiness["readyForLive"] is False
    assert performance_component["passed"] is False
    assert readiness["performanceSummary"]["readyForLocalPaperPerformance"] is False
    assert readiness["collectionProgress"]["samples"]["current"] == 4
    assert readiness["collectionProgress"]["samples"]["target"] == 100
    assert readiness["collectionProgress"]["samples"]["remaining"] == 96
    assert readiness["collectionProgress"]["closedTrades"]["current"] == 50
    assert readiness["collectionProgress"]["closedTrades"]["remaining"] == 0
    assert readiness["collectionProgress"]["closedTrades"]["unpriced"] == 0
    assert readiness["collectionProgress"]["paperOrders"]["open"] == 0
    assert readiness["collectionProgress"]["liveOrderSubmitted"] is False


def test_paper_readiness_blocks_weak_thresholds_and_sample_close_even_if_audit_claims_ready():
    readiness = build_paper_readiness_report(
        audit_report={
            "symbol": "BTC_USDT",
            "currency": "USDT",
            "sampleCount": 100,
            "readyForPaperReview": True,
            "latestSampleAgeSeconds": 1,
            "maxSampleAgeSeconds": 3600,
            "warnings": [],
            "paperQualityGate": {
                "readyForLiveCandidate": True,
                "priceSimulation": "sample-close",
                "priceSimulationFallback": None,
                "edgeHorizonSamples": 1,
                "minEdgeEvaluable": 1,
                "minEdgeWinRate": 0.1,
                "minSideEdgeEvaluable": 1,
                "minSideEdgeWinRate": 0.1,
                "recoveryWindowEvaluable": 1,
                "recoveryMinWinRate": 0.1,
                "edgeWinRate": 1.0,
                "edgeTotalRoughNetPnlUsdt": "1",
                "strategyPolicyQualityGate": {
                    "readyForCurrentStrategyLiveCandidate": True,
                    "liveBlockers": [],
                    "allowedSides": ["open-long"],
                },
                "blockers": [],
            },
            "rollingWindows": {
                "readyForRecentQuality": True,
                "configured": [1],
                "blockers": [],
            },
        },
        safety_report={
            "ok": True,
            "readyForReadonly": True,
            "readyForLive": False,
            "liveTradingEnabled": False,
            "killSwitchActive": False,
        },
        target_sample_count=100,
        performance_report={
            "mode": "paper-performance-read-only",
            "initialEquity": "100",
            "endingEquity": "101",
            "closedCount": 50,
            "openCount": 0,
            "winRate": 0.6,
            "profitFactor": 1.3,
            "maxDrawdownPct": 0.01,
            "expectancy": "0.02",
            "consecutiveLosses": 2,
            "liveOrderSubmitted": False,
        },
    )

    components = {component["name"]: component for component in readiness["components"]}
    assert readiness["readyForLocalPaperStrategy"] is False
    assert readiness["localPaperReadinessPercent"] < 100
    assert components["paper-reviewable"]["passed"] is False
    assert any("candle-high-low" in blocker for blocker in components["paper-reviewable"]["blockers"])
    assert components["global-edge-quality"]["passed"] is False
    assert any("edge horizon samples" in blocker for blocker in components["global-edge-quality"]["blockers"])
    assert any("min edge evaluable" in blocker for blocker in components["global-edge-quality"]["blockers"])
    assert components["rolling-recent-quality"]["passed"] is False
    assert any("rolling windows" in blocker for blocker in components["rolling-recent-quality"]["blockers"])


def test_paper_readiness_blocks_unpriced_performance_orders():
    readiness = build_paper_readiness_report(
        audit_report=_strict_ready_audit_report(),
        safety_report={
            "ok": True,
            "readyForReadonly": True,
            "readyForLive": False,
            "liveTradingEnabled": False,
            "killSwitchActive": False,
        },
        target_sample_count=100,
        performance_report={
            "mode": "paper-performance-read-only",
            "initialEquity": "100",
            "endingEquity": "105",
            "closedCount": 50,
            "evaluableClosedCount": 50,
            "unpricedClosedCount": 1,
            "skippedClosedCount": 1,
            "openCount": 0,
            "winRate": 0.6,
            "profitFactor": 1.3,
            "maxDrawdownPct": 0.01,
            "expectancy": "0.1",
            "consecutiveLosses": 1,
            "liveOrderSubmitted": False,
        },
    )

    components = {component["name"]: component for component in readiness["components"]}
    assert components["paper-performance-quality"]["passed"] is False
    assert readiness["collectionProgress"]["closedTrades"]["unpriced"] == 1
    assert readiness["collectionProgress"]["readyForCollectionTargets"] is False
    assert any("unpriced closed orders" in blocker for blocker in components["paper-performance-quality"]["blockers"])


def test_paper_readiness_blocks_recent_equity_decline_even_if_total_equity_positive():
    readiness = build_paper_readiness_report(
        audit_report=_strict_ready_audit_report(),
        safety_report={
            "ok": True,
            "readyForReadonly": True,
            "readyForLive": False,
            "liveTradingEnabled": False,
            "killSwitchActive": False,
        },
        target_sample_count=100,
        performance_report={
            "mode": "paper-performance-read-only",
            "initialEquity": "100",
            "endingEquity": "110",
            "closedCount": 50,
            "evaluableClosedCount": 50,
            "unpricedClosedCount": 0,
            "skippedClosedCount": 0,
            "openCount": 0,
            "winRate": 0.6,
            "profitFactor": 1.3,
            "maxDrawdownPct": 0.01,
            "expectancy": "0.2",
            "consecutiveLosses": 2,
            "equityTrend": {
                "window": 5,
                "count": 5,
                "recentEquityChange": "-1",
                "recentEquitySlope": "-0.1",
                "positiveStepRate": 0.4,
                "recentEquityImproving": False,
            },
            "liveOrderSubmitted": False,
        },
    )

    components = {component["name"]: component for component in readiness["components"]}
    assert components["paper-performance-quality"]["passed"] is False
    assert any("recent equity trend" in blocker for blocker in components["paper-performance-quality"]["blockers"])


def test_paper_readiness_blocks_skipped_closed_orders_even_when_not_unpriced():
    readiness = build_paper_readiness_report(
        audit_report=_strict_ready_audit_report(),
        safety_report={
            "ok": True,
            "readyForReadonly": True,
            "readyForLive": False,
            "liveTradingEnabled": False,
            "killSwitchActive": False,
        },
        target_sample_count=100,
        performance_report={
            "mode": "paper-performance-read-only",
            "initialEquity": "100",
            "endingEquity": "110",
            "closedCount": 50,
            "evaluableClosedCount": 50,
            "unpricedClosedCount": 0,
            "skippedClosedCount": 1,
            "openCount": 0,
            "winRate": 0.6,
            "profitFactor": 1.3,
            "maxDrawdownPct": 0.01,
            "expectancy": "0.2",
            "consecutiveLosses": 2,
            "equityTrend": {
                "window": 5,
                "count": 5,
                "recentEquityChange": "2",
                "recentEquitySlope": "0.1",
                "positiveStepRate": 0.8,
                "recentEquityImproving": True,
            },
            "liveOrderSubmitted": False,
        },
    )

    components = {component["name"]: component for component in readiness["components"]}
    assert components["paper-performance-quality"]["passed"] is False
    assert any("skipped closed orders" in blocker for blocker in components["paper-performance-quality"]["blockers"])
    assert readiness["collectionProgress"]["readyForCollectionTargets"] is False


def test_paper_readiness_blocks_live_mutation_flags_even_when_live_trading_false():
    readiness = build_paper_readiness_report(
        audit_report=_strict_ready_audit_report(),
        safety_report={
            "ok": True,
            "readyForReadonly": True,
            "readyForLive": False,
            "liveTradingEnabled": False,
            "liveMutationPhaseEnabled": True,
            "liveMutationFlagsArmed": True,
            "killSwitchActive": False,
        },
        target_sample_count=100,
        performance_report={
            "mode": "paper-performance-read-only",
            "initialEquity": "100",
            "endingEquity": "105",
            "closedCount": 50,
            "evaluableClosedCount": 50,
            "unpricedClosedCount": 0,
            "openCount": 0,
            "winRate": 0.6,
            "profitFactor": 1.3,
            "maxDrawdownPct": 0.01,
            "expectancy": "0.1",
            "consecutiveLosses": 1,
            "liveOrderSubmitted": False,
        },
    )

    components = {component["name"]: component for component in readiness["components"]}
    assert components["paper-live-lock"]["passed"] is False
    assert any("live mutation phase" in blocker for blocker in components["paper-live-lock"]["blockers"])
    assert any("live mutation flags" in blocker for blocker in components["paper-live-lock"]["blockers"])


def test_paper_governor_blocks_when_policy_gate_fails():
    decision = build_paper_decision_report(
        state_handoff=_handoff(side="open-short", confidence=0.72, preflight_allowed=True),
    )
    audit = build_paper_audit_report(
        [
            _event(4, "hold", False, "hold", market_price="79900"),
            _event(3, "paper-open-short", True, "open-short", market_price="80000"),
            _event(2, "hold", False, "hold", market_price="79900"),
            _event(1, "paper-open-long", True, "open-long", market_price="80000"),
        ],
        symbol="BTC_USDT",
        min_samples=4,
        edge_horizon_samples=1,
        min_edge_evaluable=1,
        min_side_edge_evaluable=1,
        min_side_edge_win_rate=0.5,
        recovery_window_evaluable=2,
    )

    governed = apply_paper_side_quality_governor(decision, audit)

    assert governed["wouldOpen"] is False
    assert governed["paperQualityGovernor"]["action"] == "pause-policy"
    assert any("paper policy quality paused open-short" in blocker for blocker in governed["blockers"])


def _handoff(*, side, confidence, preflight_allowed, free_balance="6", preflight_reasons=None):
    active_order_count = 0
    if side == "open-long":
        imbalance = "0.14"
    elif side == "open-short":
        imbalance = "-0.14"
    else:
        imbalance = "0"
    return {
        "ok": True,
        "symbol": "BTC_USDT",
        "currency": "USDT",
        "readyForLiveRuntime": False,
        "stateCache": {
            "instrument": {
                "instrumentId": "BTC_USDT-PERP.MEXC",
                "multiplier": "0.0001",
                "takerFee": "0.0001",
            },
            "market": {
                "lastTrade": {
                    "price": "80010",
                    "size": "3",
                    "tradeId": "trade-1",
                },
                "bookDeltas": {
                    "sequence": 7,
                    "deltaCount": 4,
                },
            },
            "account": {
                "balance": {"free": free_balance},
                "openPositionCount": 0,
                "activeOrderCount": active_order_count,
            },
        },
        "strategyHandoff": {
            "safeToEvaluateSignals": True,
            "safeToOpenNewPositionPreflight": active_order_count == 0,
            "strategyPreview": {
                "side": side,
                "confidence": confidence,
                "preflightAllowed": preflight_allowed,
                "preflightReasons": preflight_reasons or [],
                "candidateOrder": {
                    "price": "80000",
                    "vol": "1",
                    "contractSize": "0.0001",
                    "leverage": "2",
                    "stopLossPrice": "79720",
                    "takeProfitPrice": "80440",
                },
                "metrics": {
                    "bid": "79999.5",
                    "ask": "80000.5",
                    "spread": "1",
                    "fundingRate": "0.0001",
                    "depthImbalanceTop10": imbalance,
                },
            },
        },
        "blockers": [],
    }


def _event(
    event_id,
    action,
    would_open,
    side,
    *,
    blockers=None,
    market_price=None,
    stop_loss_price=None,
    take_profit_price=None,
    paper_probe=False,
    paper_gates=None,
    volatility_filter=None,
):
    virtual_order = {
        "entryPrice": "80000",
        "vol": "1",
        "contractSize": "0.0001",
        "estimatedTakerFee": "0.0008",
        "stopLossPrice": stop_loss_price,
        "takeProfitPrice": take_profit_price,
    }
    return {
        "id": event_id,
        "ts": event_id * 1000,
        "eventType": "nautilus_paper_decision",
        "payload": {
            "timestamp": event_id * 1000,
            "mode": "paper-trading-read-only",
            "symbol": "BTC_USDT",
            "currency": "USDT",
            "wouldOpen": would_open,
            "action": action,
            "side": side,
            "confidence": "0.72",
            "virtualOrder": virtual_order if would_open else None,
            "paperProbe": {
                "enabled": True,
                "side": side,
                "eligibleForRecoveryStats": True,
                "virtualOrder": virtual_order,
                "liveOrderSubmitted": False,
            }
            if paper_probe
            else None,
            "market": {
                "lastTradePrice": market_price,
                "lastTradeSize": "1",
                "lastTradeId": f"trade-{event_id}",
            }
            if market_price is not None
            else None,
            "paperGates": paper_gates,
            "volatilityFilter": volatility_filter,
            "blockers": blockers or [],
        },
    }


def _strict_ready_audit_report():
    return {
        "symbol": "BTC_USDT",
        "currency": "USDT",
        "sampleCount": 100,
        "readyForPaperReview": True,
        "latestSampleAgeSeconds": 1,
        "maxSampleAgeSeconds": 3600,
        "warnings": [],
        "actionCounts": {"paper-open-long": 50, "hold": 50},
        "blockerCounts": {},
        "latestSample": {
            "eventId": 100,
            "timestamp": 100000,
            "action": "hold",
            "side": "hold",
            "wouldOpen": False,
            "blockers": [],
        },
        "policyAllowedSides": ["open-long"],
        "paperQualityGate": {
            "readyForLiveCandidate": True,
            "priceSimulation": "candle-high-low",
            "priceSimulationFallback": None,
            "edgeHorizonSamples": 3,
            "minEdgeEvaluable": 3,
            "minEdgeWinRate": 0.55,
            "minSideEdgeEvaluable": 2,
            "minSideEdgeWinRate": 0.55,
            "recoveryWindowEvaluable": 3,
            "recoveryMinWinRate": 0.55,
            "edgeEvaluableCount": 50,
            "edgeWinRate": 0.6,
            "edgeTotalRoughNetPnlUsdt": "5",
            "recoveryProbeCount": 0,
            "strategyPolicyQualityGate": {
                "readyForCurrentStrategyLiveCandidate": True,
                "liveBlockers": [],
                "allowedSides": ["open-long"],
            },
            "blockers": [],
        },
        "rollingWindows": {
            "readyForRecentQuality": True,
            "configured": [5, 10, 25, 50],
            "blockers": [],
        },
    }


def _candle(open_time_ms, *, high, low, close, open_price="80000"):
    return {
        "symbol": "BTC_USDT",
        "interval": "1m",
        "openTimeMs": open_time_ms,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": "1",
        "quoteVolume": "80000",
        "source": "test-candle",
    }
