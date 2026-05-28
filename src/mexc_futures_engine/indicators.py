from __future__ import annotations

from decimal import Decimal
import time
from typing import Any

from .candles import Candle


def build_candle_trend_report(
    candles: list[Candle],
    *,
    short_period: int = 5,
    long_period: int = 20,
    max_candle_age_seconds: int | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    if short_period <= 0:
        raise ValueError("short_period must be positive")
    if long_period <= 0:
        raise ValueError("long_period must be positive")
    if short_period >= long_period:
        raise ValueError("short_period must be less than long_period")
    if max_candle_age_seconds is not None and max_candle_age_seconds <= 0:
        raise ValueError("max_candle_age_seconds must be positive when set")

    sorted_candles = sorted(candles, key=lambda candle: candle.open_time_ms)
    blockers: list[str] = []
    warnings: list[str] = []
    if len(sorted_candles) < long_period:
        blockers.append(f"only {len(sorted_candles)} candle(s); need {long_period}")

    latest = sorted_candles[-1] if sorted_candles else None
    latest_age_seconds = None
    if latest is not None:
        effective_now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        latest_ts = latest.close_time_ms or latest.open_time_ms
        latest_age_seconds = max(0, (effective_now_ms - latest_ts) // 1000)
        if max_candle_age_seconds is not None and latest_age_seconds > max_candle_age_seconds:
            blockers.append(f"latest candle age {latest_age_seconds}s above gate {max_candle_age_seconds}s")
    elif max_candle_age_seconds is not None:
        blockers.append("latest candle is missing")

    closes = [candle.close for candle in sorted_candles]
    highs = [candle.high for candle in sorted_candles]
    lows = [candle.low for candle in sorted_candles]
    short_ema = _ema(closes, short_period) if len(closes) >= short_period else None
    long_ema = _ema(closes, long_period) if len(closes) >= long_period else None
    trend = "unknown"
    if short_ema is not None and long_ema is not None:
        if short_ema > long_ema:
            trend = "bullish"
        elif short_ema < long_ema:
            trend = "bearish"
        else:
            trend = "flat"
    else:
        warnings.append("trend EMA unavailable until enough candles are collected")

    latest_close = closes[-1] if closes else None
    range_bps = None
    if latest_close is not None and latest_close > 0 and highs and lows:
        range_bps = (highs[-1] - lows[-1]) / latest_close * Decimal("10000")

    return {
        "ok": not blockers,
        "source": "MEXC REST klines",
        "candleCount": len(sorted_candles),
        "shortPeriod": short_period,
        "longPeriod": long_period,
        "trend": trend,
        "latestCandle": latest.to_dict() if latest else None,
        "latestCandleAgeSeconds": latest_age_seconds,
        "observed": {
            "shortEma": _decimal_text(short_ema),
            "longEma": _decimal_text(long_ema),
            "latestClose": _decimal_text(latest_close),
            "latestRangeBps": _decimal_text(range_bps),
        },
        "blockers": blockers,
        "warnings": warnings,
    }


def build_candle_volatility_report(
    candles: list[Candle],
    *,
    min_avg_range_bps: float | None = None,
    max_avg_range_bps: float | None = None,
    min_latest_range_bps: float | None = None,
    max_latest_range_bps: float | None = None,
    max_candle_age_seconds: int | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    if min_avg_range_bps is not None and min_avg_range_bps < 0:
        raise ValueError("min_avg_range_bps must be non-negative when set")
    if max_avg_range_bps is not None and max_avg_range_bps < 0:
        raise ValueError("max_avg_range_bps must be non-negative when set")
    if min_latest_range_bps is not None and min_latest_range_bps < 0:
        raise ValueError("min_latest_range_bps must be non-negative when set")
    if max_latest_range_bps is not None and max_latest_range_bps < 0:
        raise ValueError("max_latest_range_bps must be non-negative when set")
    if (
        min_avg_range_bps is not None
        and max_avg_range_bps is not None
        and min_avg_range_bps > max_avg_range_bps
    ):
        raise ValueError("min_avg_range_bps must be at most max_avg_range_bps")
    if (
        min_latest_range_bps is not None
        and max_latest_range_bps is not None
        and min_latest_range_bps > max_latest_range_bps
    ):
        raise ValueError("min_latest_range_bps must be at most max_latest_range_bps")
    if max_candle_age_seconds is not None and max_candle_age_seconds <= 0:
        raise ValueError("max_candle_age_seconds must be positive when set")

    sorted_candles = sorted(candles, key=lambda candle: candle.open_time_ms)
    blockers: list[str] = []
    warnings: list[str] = []
    if not sorted_candles:
        blockers.append("no candles available for volatility filter")

    latest = sorted_candles[-1] if sorted_candles else None
    latest_age_seconds = None
    if latest is not None:
        effective_now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        latest_ts = latest.close_time_ms or latest.open_time_ms
        latest_age_seconds = max(0, (effective_now_ms - latest_ts) // 1000)
        if max_candle_age_seconds is not None and latest_age_seconds > max_candle_age_seconds:
            blockers.append(f"latest candle age {latest_age_seconds}s above gate {max_candle_age_seconds}s")
    elif max_candle_age_seconds is not None:
        blockers.append("latest candle is missing")

    ranges = [_range_bps(candle) for candle in sorted_candles]
    valid_ranges = [value for value in ranges if value is not None]
    avg_range_bps = sum(valid_ranges, Decimal("0")) / Decimal(len(valid_ranges)) if valid_ranges else None
    latest_range_bps = ranges[-1] if ranges else None
    if not valid_ranges:
        blockers.append("no valid candle ranges available")
    elif len(valid_ranges) < len(sorted_candles):
        warnings.append("some candles had invalid range inputs and were skipped")

    _append_range_gate_blockers(
        blockers,
        label="average candle range",
        value=avg_range_bps,
        min_bps=min_avg_range_bps,
        max_bps=max_avg_range_bps,
    )
    _append_range_gate_blockers(
        blockers,
        label="latest candle range",
        value=latest_range_bps,
        min_bps=min_latest_range_bps,
        max_bps=max_latest_range_bps,
    )
    if all(
        threshold is None
        for threshold in (
            min_avg_range_bps,
            max_avg_range_bps,
            min_latest_range_bps,
            max_latest_range_bps,
        )
    ):
        warnings.append("volatility filter has no range thresholds configured")

    regime = _range_regime(avg_range_bps, min_bps=min_avg_range_bps, max_bps=max_avg_range_bps)
    return {
        "ok": not blockers,
        "source": "MEXC REST klines",
        "candleCount": len(sorted_candles),
        "validCandleRangeCount": len(valid_ranges),
        "regime": regime,
        "latestCandle": latest.to_dict() if latest else None,
        "latestCandleAgeSeconds": latest_age_seconds,
        "thresholds": {
            "minAvgRangeBps": min_avg_range_bps,
            "maxAvgRangeBps": max_avg_range_bps,
            "minLatestRangeBps": min_latest_range_bps,
            "maxLatestRangeBps": max_latest_range_bps,
            "maxCandleAgeSeconds": max_candle_age_seconds,
        },
        "observed": {
            "avgRangeBps": _decimal_text(avg_range_bps),
            "latestRangeBps": _decimal_text(latest_range_bps),
        },
        "blockers": blockers,
        "warnings": warnings,
    }


def _ema(values: list[Decimal], period: int) -> Decimal | None:
    if len(values) < period:
        return None
    alpha = Decimal("2") / Decimal(period + 1)
    ema = sum(values[:period], Decimal("0")) / Decimal(period)
    for value in values[period:]:
        ema = (value - ema) * alpha + ema
    return ema


def _range_bps(candle: Candle) -> Decimal | None:
    if candle.close <= 0 or candle.high < candle.low:
        return None
    return (candle.high - candle.low) / candle.close * Decimal("10000")


def _append_range_gate_blockers(
    blockers: list[str],
    *,
    label: str,
    value: Decimal | None,
    min_bps: float | None,
    max_bps: float | None,
) -> None:
    if value is None:
        if min_bps is not None or max_bps is not None:
            blockers.append(f"{label} is unavailable")
        return
    if min_bps is not None and value < Decimal(str(min_bps)):
        blockers.append(f"{label} {_decimal_text(value)} below floor {min_bps}")
    if max_bps is not None and value > Decimal(str(max_bps)):
        blockers.append(f"{label} {_decimal_text(value)} above ceiling {max_bps}")


def _range_regime(avg_range_bps: Decimal | None, *, min_bps: float | None, max_bps: float | None) -> str:
    if avg_range_bps is None:
        return "unknown"
    if min_bps is not None and avg_range_bps < Decimal(str(min_bps)):
        return "flat"
    if max_bps is not None and avg_range_bps > Decimal(str(max_bps)):
        return "volatile"
    if avg_range_bps < Decimal("5"):
        return "flat"
    if avg_range_bps > Decimal("500"):
        return "volatile"
    return "normal"


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")
