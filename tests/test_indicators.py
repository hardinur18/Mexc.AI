from decimal import Decimal

from mexc_futures_engine.candles import Candle
from mexc_futures_engine.indicators import build_candle_trend_report
from mexc_futures_engine.indicators import build_candle_volatility_report


def test_candle_trend_report_marks_bullish_cross():
    candles = [
        _candle(index, close)
        for index, close in enumerate(["100", "101", "102", "103", "104", "105"], start=1)
    ]

    report = build_candle_trend_report(candles, short_period=2, long_period=4, now_ms=6 * 60_000)

    assert report["ok"] is True
    assert report["trend"] == "bullish"
    assert report["observed"]["shortEma"] is not None
    assert report["latestCandleAgeSeconds"] == 0


def test_candle_trend_report_blocks_when_latest_candle_stale():
    candles = [_candle(index, "100") for index in range(1, 5)]

    report = build_candle_trend_report(
        candles,
        short_period=2,
        long_period=4,
        max_candle_age_seconds=30,
        now_ms=10 * 60_000,
    )

    assert report["ok"] is False
    assert any("latest candle age" in blocker for blocker in report["blockers"])


def test_candle_volatility_report_observes_average_and_latest_ranges():
    candles = [
        _candle(1, "100", high_delta="1", low_delta="1"),
        _candle(2, "100", high_delta="2", low_delta="1"),
        _candle(3, "100", high_delta="3", low_delta="1"),
    ]

    report = build_candle_volatility_report(
        candles,
        min_avg_range_bps=100,
        max_avg_range_bps=400,
        max_latest_range_bps=500,
        now_ms=3 * 60_000,
    )

    assert report["ok"] is True
    assert report["regime"] == "normal"
    assert report["observed"]["avgRangeBps"] == "300"
    assert report["observed"]["latestRangeBps"] == "400"


def test_candle_volatility_report_blocks_flat_and_volatile_ranges():
    candles = [
        _candle(1, "100", high_delta="0.01", low_delta="0.01"),
        _candle(2, "100", high_delta="10", low_delta="10"),
    ]

    report = build_candle_volatility_report(
        candles,
        min_avg_range_bps=1500,
        max_latest_range_bps=1000,
        now_ms=2 * 60_000,
    )

    assert report["ok"] is False
    assert "average candle range 1001 below floor 1500" in report["blockers"]
    assert "latest candle range 2000 above ceiling 1000" in report["blockers"]


def _candle(index, close, *, high_delta="1", low_delta="1"):
    price = Decimal(close)
    return Candle(
        symbol="BTC_USDT",
        interval="1m",
        exchange_interval="Min1",
        open_time_ms=index * 60_000,
        close_time_ms=index * 60_000,
        open=price,
        high=price + Decimal(high_delta),
        low=price - Decimal(low_delta),
        close=price,
        volume=Decimal("1"),
        quote_volume=price,
    )
