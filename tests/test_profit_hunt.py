from mexc_futures_engine.profit_hunt import build_profit_hunt_report


def test_profit_hunt_promotes_best_positive_side_variant():
    report = build_profit_hunt_report(
        {
            "mode": "paper-execution-ledger-read-only",
            "symbol": "BTC_USDT",
            "currency": "USDT",
            "priceSimulation": "candle-high-low",
            "priceSimulationFallback": None,
            "orders": [
                _order("long-1", "open-long", "0.9", "-1", 1),
                _order("long-2", "open-long", "0.9", "-1", 2),
                _order("short-1", "open-short", "0.8", "1", 3),
                _order("short-2", "open-short", "0.8", "1", 4),
                _order("short-3", "open-short", "0.8", "1", 5),
                _order("short-4", "open-short", "0.8", "1", 6),
                _order("short-5", "open-short", "0.8", "1", 7),
            ],
            "liveOrderSubmitted": False,
        },
        initial_equity="100",
        confidence_thresholds=(0, 0.75),
        min_closed_count=5,
        min_win_rate=0.55,
        min_profit_factor=1.25,
        max_drawdown_pct=0.02,
    )

    assert report["readyForPromotion"] is True
    assert report["bestCandidate"]["filter"] == {"side": "open-short", "minConfidence": 0.0}
    assert report["bestCandidate"]["performance"]["endingEquity"] == "105"
    assert report["bestCandidate"]["performance"]["equityTrend"]["recentEquityImproving"] is True
    assert report["liveOrderSubmitted"] is False


def test_profit_hunt_refuses_negative_recent_equity():
    report = build_profit_hunt_report(
        {
            "mode": "paper-execution-ledger-read-only",
            "symbol": "BTC_USDT",
            "currency": "USDT",
            "orders": [
                _order("short-1", "open-short", "0.8", "10", 1),
                _order("short-2", "open-short", "0.8", "10", 2),
                _order("short-3", "open-short", "0.8", "-1", 3),
                _order("short-4", "open-short", "0.8", "-1", 4),
                _order("short-5", "open-short", "0.8", "-1", 5),
                _order("short-6", "open-short", "0.8", "-1", 6),
                _order("short-7", "open-short", "0.8", "-1", 7),
            ],
            "liveOrderSubmitted": False,
        },
        initial_equity="100",
        confidence_thresholds=(0,),
        min_closed_count=5,
        min_win_rate=0.55,
        min_profit_factor=1.25,
        max_drawdown_pct=0.2,
    )

    assert report["readyForPromotion"] is False
    assert any("recent equity trend" in blocker for blocker in report["bestCandidate"]["blockers"])


def test_profit_hunt_entry_metric_sweep_promotes_selective_context():
    strong_short_metrics = {
        "depthImbalanceTop10": "-0.42",
        "spreadBps": "0.02",
        "fundingRate": "0.00002",
        "avgRangeBps": "8",
        "latestRangeBps": "6",
    }
    weak_long_metrics = {
        "depthImbalanceTop10": "0.5",
        "spreadBps": "0.02",
        "fundingRate": "0.00002",
        "avgRangeBps": "8",
        "latestRangeBps": "6",
    }
    report = build_profit_hunt_report(
        {
            "mode": "paper-execution-ledger-read-only",
            "symbol": "BTC_USDT",
            "currency": "USDT",
            "orders": [
                _order("long-1", "open-long", "0.9", "-1", 1, entry_metrics=weak_long_metrics),
                _order("long-2", "open-long", "0.9", "-1", 2, entry_metrics=weak_long_metrics),
                _order("short-1", "open-short", "0.9", "1", 3, entry_metrics=strong_short_metrics),
                _order("short-2", "open-short", "0.9", "1", 4, entry_metrics=strong_short_metrics),
                _order("short-3", "open-short", "0.9", "1", 5, entry_metrics=strong_short_metrics),
                _order("short-4", "open-short", "0.9", "1", 6, entry_metrics=strong_short_metrics),
                _order("short-5", "open-short", "0.9", "1", 7, entry_metrics=strong_short_metrics),
            ],
            "liveOrderSubmitted": False,
        },
        initial_equity="100",
        confidence_thresholds=(0,),
        min_closed_count=5,
        min_win_rate=0.55,
        min_profit_factor=1.25,
        max_drawdown_pct=0.02,
        entry_metric_sweeps={
            "minDepthImbalanceTop10": (0.3,),
            "maxSpreadBps": (0.05,),
            "maxAbsFundingRate": (0.0001,),
            "minAvgRangeBps": (5,),
            "maxLatestRangeBps": (10,),
        },
    )

    assert report["readyForPromotion"] is True
    assert report["bestCandidate"]["filter"] == {
        "side": "open-short",
        "minConfidence": 0.0,
        "entryMetrics": {
            "minDepthImbalanceTop10": 0.3,
            "maxSpreadBps": 0.05,
            "maxAbsFundingRate": 0.0001,
            "minAvgRangeBps": 5.0,
            "maxLatestRangeBps": 10.0,
        },
    }
    assert report["bestCandidate"]["source"]["selectedOrderCount"] == 5
    assert report["thresholds"]["entryMetricFilterVariantCount"] == 1
    assert report["liveOrderSubmitted"] is False


def test_profit_hunt_entry_metric_sweep_missing_metrics_is_explicit():
    report = build_profit_hunt_report(
        {
            "mode": "paper-execution-ledger-read-only",
            "symbol": "BTC_USDT",
            "currency": "USDT",
            "orders": [
                _order("short-1", "open-short", "0.9", "1", 1),
                _order("short-2", "open-short", "0.9", "1", 2),
            ],
            "liveOrderSubmitted": False,
        },
        initial_equity="100",
        confidence_thresholds=(0,),
        min_closed_count=1,
        min_win_rate=0.55,
        min_profit_factor=1.25,
        max_drawdown_pct=0.02,
        entry_metric_sweeps={"minDepthImbalanceTop10": (0.3,)},
    )

    assert report["readyForPromotion"] is False
    assert report["bestCandidate"]["source"]["missingEntryMetricCount"] == 2
    assert report["bestCandidate"]["performance"]["closedCount"] == 0


def _order(order_id, side, confidence, pnl, exit_timestamp, *, entry_metrics=None):
    order = {
        "orderId": order_id,
        "sourceType": "virtual-entry",
        "sourceEventId": exit_timestamp,
        "createdTimestamp": exit_timestamp - 1,
        "symbol": "BTC_USDT",
        "currency": "USDT",
        "side": side,
        "confidence": confidence,
        "status": "EXPIRED",
        "exit": {
            "exitTimestamp": exit_timestamp,
            "roughNetPnlUsdt": pnl,
        },
        "roughNetPnlUsdt": pnl,
        "liveOrderSubmitted": False,
    }
    if entry_metrics is not None:
        order["entryMetrics"] = entry_metrics
    return order
