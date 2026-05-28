from mexc_futures_engine.performance import build_paper_performance_report
from mexc_futures_engine.performance import equity_curve_from_closed_orders


def test_paper_performance_builds_metrics_from_closed_ledger_orders():
    report = build_paper_performance_report(_ledger(), initial_equity="100")

    assert report["mode"] == "paper-performance-read-only"
    assert report["initialEquity"] == "100"
    assert report["endingEquity"] == "108"
    assert report["netPnlUsdt"] == "8"
    assert report["returnPct"] == 0.08
    assert report["peakEquity"] == "115"
    assert report["maxDrawdown"] == "7"
    assert report["maxDrawdownPct"] == 7 / 115
    assert report["winRate"] == 0.5
    assert report["averageWin"] == "7.5"
    assert report["averageLoss"] == "-3.5"
    assert report["profitFactor"] == 15 / 7
    assert report["tradeCount"] == 5
    assert report["closedCount"] == 4
    assert report["openCount"] == 1
    assert report["expectancy"] == "2"
    assert report["consecutiveLosses"] == 2
    assert report["equityTrend"]["count"] == 4
    assert report["equityTrend"]["recentEquityImproving"] is False
    assert report["liveOrderSubmitted"] is False


def test_equity_curve_uses_closed_orders_in_exit_order_only():
    curve = equity_curve_from_closed_orders(_ledger(), initial_equity="100")

    assert [point["orderId"] for point in curve] == [
        "virtual-entry-1",
        "virtual-entry-2",
        "virtual-entry-4",
        "virtual-entry-3",
    ]
    assert [point["equity"] for point in curve] == [
        "110",
        "115",
        "112",
        "108",
    ]


def test_paper_performance_handles_empty_or_unprofitable_ledgers():
    report = build_paper_performance_report(
        {
            "mode": "paper-execution-ledger-read-only",
            "symbol": "BTC_USDT",
            "currency": "USDT",
            "orders": [
                _order("open-1", "OPEN", None, 1),
                _order("closed-1", "EXPIRED", "-2", 2),
            ],
        },
        initial_equity="50",
    )

    assert report["endingEquity"] == "48"
    assert report["peakEquity"] == "50"
    assert report["maxDrawdown"] == "2"
    assert report["winRate"] == 0.0
    assert report["averageWin"] is None
    assert report["averageLoss"] == "-2"
    assert report["profitFactor"] == 0.0
    assert report["expectancy"] == "-2"
    assert report["consecutiveLosses"] == 1
    assert report["closedCount"] == 1
    assert report["openCount"] == 1


def test_paper_performance_skips_unpriced_closed_orders():
    report = build_paper_performance_report(
        {
            "mode": "paper-execution-ledger-read-only",
            "symbol": "BTC_USDT",
            "currency": "USDT",
            "orders": [
                _order("priced-1", "TAKE_PROFIT", "3", 1),
                {
                    "orderId": "unpriced-1",
                    "sourceEventId": 2,
                    "createdTimestamp": 2,
                    "symbol": "BTC_USDT",
                    "currency": "USDT",
                    "side": "open-long",
                    "status": "EXPIRED",
                    "exit": None,
                    "roughNetPnlUsdt": None,
                    "liveOrderSubmitted": False,
                },
                _order("open-1", "OPEN", None, 3),
            ],
        },
        initial_equity="20",
    )

    assert report["endingEquity"] == "23"
    assert report["closedCount"] == 1
    assert report["evaluableClosedCount"] == 1
    assert report["unpricedClosedCount"] == 1
    assert report["skippedClosedCount"] == 1
    assert report["openCount"] == 1
    assert any("skipped 1 unpriced" in warning for warning in report["warnings"])


def test_paper_performance_reports_recent_equity_trend():
    report = build_paper_performance_report(
        {
            "mode": "paper-execution-ledger-read-only",
            "symbol": "BTC_USDT",
            "currency": "USDT",
            "orders": [
                _order("closed-1", "EXPIRED", "-1", 1),
                _order("closed-2", "TAKE_PROFIT", "1", 2),
                _order("closed-3", "TAKE_PROFIT", "2", 3),
                _order("closed-4", "TAKE_PROFIT", "3", 4),
                _order("closed-5", "TAKE_PROFIT", "4", 5),
            ],
        },
        initial_equity="100",
    )

    assert report["equityTrend"]["window"] == 5
    assert report["equityTrend"]["count"] == 5
    assert report["equityTrend"]["recentEquityChange"] == "9"
    assert report["equityTrend"]["recentEquityImproving"] is True


def test_paper_performance_detects_recent_equity_deterioration():
    report = build_paper_performance_report(
        {
            "mode": "paper-execution-ledger-read-only",
            "symbol": "BTC_USDT",
            "currency": "USDT",
            "orders": [
                _order("closed-1", "TAKE_PROFIT", "20", 1),
                _order("closed-2", "TAKE_PROFIT", "20", 2),
                _order("closed-3", "TAKE_PROFIT", "20", 3),
                _order("closed-4", "EXPIRED", "-1", 4),
                _order("closed-5", "EXPIRED", "-2", 5),
                _order("closed-6", "EXPIRED", "-3", 6),
                _order("closed-7", "EXPIRED", "-4", 7),
                _order("closed-8", "EXPIRED", "-5", 8),
            ],
        },
        initial_equity="100",
    )

    assert report["endingEquity"] == "145"
    assert report["equityTrend"]["recentEquityChange"] == "-15"
    assert report["equityTrend"]["recentEquityImproving"] is False


def test_paper_performance_uses_ledger_initial_equity_when_present():
    ledger = _ledger()
    ledger["initialEquity"] = "25"

    report = build_paper_performance_report(ledger)

    assert report["initialEquity"] == "25"
    assert report["endingEquity"] == "33"


def _ledger():
    return {
        "mode": "paper-execution-ledger-read-only",
        "symbol": "BTC_USDT",
        "currency": "USDT",
        "orderCount": 5,
        "closedCount": 4,
        "openCount": 1,
        "orders": [
            _order("virtual-entry-3", "EXPIRED", "-4", 4000),
            _order("virtual-entry-1", "TAKE_PROFIT", "10", 1000),
            _order("virtual-entry-5", "OPEN", None, 5000),
            _order("virtual-entry-4", "EXPIRED", "-3", 3000),
            _order("virtual-entry-2", "TAKE_PROFIT", "5", 2000),
        ],
        "liveOrderSubmitted": False,
    }


def _order(order_id, status, pnl, exit_timestamp):
    return {
        "orderId": order_id,
        "sourceEventId": int(str(exit_timestamp)[0]),
        "createdTimestamp": exit_timestamp - 100,
        "symbol": "BTC_USDT",
        "currency": "USDT",
        "side": "open-long",
        "status": status,
        "exit": {
            "exitTimestamp": exit_timestamp,
            "roughNetPnlUsdt": pnl,
        }
        if status != "OPEN"
        else None,
        "roughNetPnlUsdt": pnl,
        "liveOrderSubmitted": False,
    }
