"""Realtime positions dashboard backend — multi-account."""
from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

os.chdir(ROOT)

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from mexc_futures_engine.client import MexcFuturesClient
from mexc_futures_engine.settings import MexcSettings
from cascade import (
    ORCHESTRATOR as CASCADE_ORCHESTRATOR,
    CASCADE_LIVE_ENABLED,
    CascadeExecutor,
    CascadeMode,
    compute_performance_metrics as cascade_performance_metrics,
    list_journal_entries as cascade_list_journal,
)
from ws_client import WS_CLIENT


# ═══════════════════════════════════════════════════════════════════
# Account manager — load accounts.json, build a client pool per account.
# ═══════════════════════════════════════════════════════════════════

@dataclass
class AccountEntry:
    id: str
    name: str
    color: str
    category: str
    client: MexcFuturesClient = field(repr=False)
    # Cached equity from last snapshot — used by cascade orchestrator
    _cached_equity: float = 0.0


def _load_accounts() -> list[AccountEntry]:
    cfg_path = ROOT / "accounts.json"
    if not cfg_path.exists():
        # Fallback: build single account from .env
        s = MexcSettings.from_env()
        return [
            AccountEntry(
                id="main",
                name="Main",
                color="violet",
                category="utama",
                client=MexcFuturesClient(s),
            )
        ]

    raw = json.loads(cfg_path.read_text())
    entries: list[AccountEntry] = []
    for item in raw.get("accounts", []):
        if not item.get("access_key") or not item.get("secret_key"):
            continue
        base = MexcSettings.from_env()
        settings = MexcSettings(
            access_key=item["access_key"],
            secret_key=item["secret_key"],
            base_url=base.base_url,
            recv_window=base.recv_window,
            use_doh_dns=base.use_doh_dns,
            doh_url=base.doh_url,
            live_trading_enabled=base.live_trading_enabled,
            live_confirm=base.live_confirm,
            live_mutation_phase_enabled=base.live_mutation_phase_enabled,
            state_db=base.state_db,
            strategy_allowed_sides=base.strategy_allowed_sides,
        )
        entries.append(
            AccountEntry(
                id=item["id"],
                name=item.get("name", item["id"]),
                color=item.get("color", "violet"),
                category=item.get("category", "utama"),
                client=MexcFuturesClient(settings),
            )
        )
    if not entries:
        s = MexcSettings.from_env()
        entries.append(
            AccountEntry(
                id="main",
                name="Main",
                color="violet",
                category="utama",
                client=MexcFuturesClient(s),
            )
        )
    return entries


ACCOUNTS: list[AccountEntry] = _load_accounts()
ACCOUNTS_BY_ID: dict[str, AccountEntry] = {a.id: a for a in ACCOUNTS}


# ─── Accounts persistence helpers ─────────────────────────────────

ACCOUNTS_PATH = ROOT / "accounts.json"

ALLOWED_COLORS = {"violet", "emerald", "sky", "amber", "rose", "cyan", "fuchsia", "lime"}


def _read_accounts_file() -> list[dict]:
    if not ACCOUNTS_PATH.exists():
        return []
    raw = json.loads(ACCOUNTS_PATH.read_text())
    return list(raw.get("accounts", []))


def _write_accounts_file(accounts: list[dict]) -> None:
    ACCOUNTS_PATH.write_text(json.dumps({"accounts": accounts}, indent=2) + "\n")


def _reload_account_manager() -> None:
    """Re-read accounts.json and rebuild ACCOUNTS / ACCOUNTS_BY_ID."""
    global ACCOUNTS, ACCOUNTS_BY_ID
    ACCOUNTS = _load_accounts()
    ACCOUNTS_BY_ID = {a.id: a for a in ACCOUNTS}


# ═══════════════════════════════════════════════════════════════════
# Shared caches (not account-specific)
# ═══════════════════════════════════════════════════════════════════

_contract_cache: dict[str, dict] = {}
_sr_cache: dict[str, tuple[float, list[dict]]] = {}
_SR_TTL_SECONDS = 600  # 10 minutes


def get_contract_cached(symbol: str) -> dict:
    if symbol not in _contract_cache:
        # Use any account's client; contract spec is public.
        any_client = ACCOUNTS[0].client
        _contract_cache[symbol] = any_client.contract_detail(symbol).get("data", {})
    return _contract_cache[symbol]


def compute_pivot_levels(symbol: str) -> list[dict]:
    """Pivot points + Fibonacci retracement from latest complete daily candle."""
    any_client = ACCOUNTS[0].client
    try:
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - (5 * 86400 * 1000)
        resp = any_client.klines(
            symbol=symbol, interval="Day1", start_time_ms=start_ms, end_time_ms=now_ms
        )
    except Exception:
        return []
    data = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(data, dict):
        return []
    times = data.get("time") or []
    highs = data.get("high") or []
    lows = data.get("low") or []
    closes = data.get("close") or []
    if not (times and highs and lows and closes):
        return []
    idx = -2 if len(times) >= 2 else -1
    try:
        h = float(highs[idx])
        l = float(lows[idx])
        c = float(closes[idx])
    except (ValueError, TypeError, IndexError):
        return []
    pp = (h + l + c) / 3
    r1 = 2 * pp - l
    s1 = 2 * pp - h
    r2 = pp + (h - l)
    s2 = pp - (h - l)

    # Fibonacci retracement levels (between previous day H and L)
    rng = h - l
    fib_382 = h - rng * 0.382
    fib_5 = h - rng * 0.5
    fib_618 = h - rng * 0.618

    return [
        {"label": "R2", "price": round(r2, 8), "kind": "resistance"},
        {"label": "R1", "price": round(r1, 8), "kind": "resistance"},
        {"label": "Fib 38.2", "price": round(fib_382, 8), "kind": "pivot"},
        {"label": "PP", "price": round(pp, 8), "kind": "pivot"},
        {"label": "Fib 50.0", "price": round(fib_5, 8), "kind": "pivot"},
        {"label": "Fib 61.8", "price": round(fib_618, 8), "kind": "pivot"},
        {"label": "S1", "price": round(s1, 8), "kind": "support"},
        {"label": "S2", "price": round(s2, 8), "kind": "support"},
    ]


_funding_cache: dict[str, tuple[float, dict]] = {}
_FUNDING_TTL_SECONDS = 30

_sparkline_cache: dict[str, tuple[float, list[list[float]]]] = {}
_SPARKLINE_TTL_SECONDS = 300  # 5 min

_analytics_cache: dict[str, tuple[float, dict]] = {}
_lite_analytics_cache: dict[str, tuple[float, dict]] = {}
_ANALYTICS_TTL_SECONDS = 60

# Closed positions tracker — detect when positions disappear
_previous_position_ids: dict[str, dict[int, dict]] = {}  # account_id -> {position_id: snapshot}
_closed_positions_log: list[dict] = []
_CLOSED_LOG_MAX = 200

# Funding rate history per symbol (rolling 24h, samples every minute)
_funding_history: dict[str, list[tuple[float, float]]] = {}
_FUNDING_HISTORY_MAX = 1440  # 24h × 60 min

# Orderbook depth cache
_depth_cache: dict[str, tuple[float, dict]] = {}
_DEPTH_TTL_SECONDS = 15

# Per-interval kline cache for multi-timeframe analysis
_klines_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_KLINES_TTL_SECONDS = {
    "Min15": 60,
    "Min60": 180,
    "Hour4": 600,
    "Day1": 1800,
}


def fetch_klines_cached(symbol: str, interval: str, count: int = 100) -> list[dict]:
    """Fetch klines for given interval, return list of {time, open, high, low, close, vol}."""
    cache_key = (symbol, interval)
    now = time.time()
    ttl = _KLINES_TTL_SECONDS.get(interval, 300)
    cached = _klines_cache.get(cache_key)
    if cached and (now - cached[0]) < ttl:
        return cached[1]

    # Approx duration per candle in seconds
    sec_per_candle = {
        "Min1": 60, "Min5": 300, "Min15": 900,
        "Min30": 1800, "Min60": 3600, "Hour1": 3600,
        "Hour4": 14400, "Hour8": 28800, "Day1": 86400,
    }.get(interval, 900)
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (count * sec_per_candle * 1000)

    any_client = ACCOUNTS[0].client
    try:
        resp = any_client.klines(
            symbol=symbol, interval=interval, start_time_ms=start_ms, end_time_ms=now_ms
        )
    except Exception:
        return []
    data = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(data, dict):
        return []
    times = data.get("time") or []
    opens = data.get("open") or []
    highs = data.get("high") or []
    lows = data.get("low") or []
    closes = data.get("close") or []
    vols = data.get("vol") or []
    out: list[dict] = []
    for i in range(len(times)):
        try:
            out.append({
                "t": int(times[i]),
                "o": float(opens[i]),
                "h": float(highs[i]),
                "l": float(lows[i]),
                "c": float(closes[i]),
                "v": float(vols[i]) if i < len(vols) else 0.0,
            })
        except (ValueError, TypeError, IndexError):
            continue
    out = out[-count:]
    _klines_cache[cache_key] = (now, out)
    return out


def _track_funding(symbol: str, rate: float) -> None:
    history = _funding_history.setdefault(symbol, [])
    history.append((time.time(), rate))
    if len(history) > _FUNDING_HISTORY_MAX:
        history.pop(0)


def _funding_trend(symbol: str) -> str | None:
    """Direction over last hour. rising/falling/stable."""
    history = _funding_history.get(symbol, [])
    if len(history) < 3:
        return None
    one_hr_ago = time.time() - 3600
    older = [v for t, v in history if t >= one_hr_ago][:5]
    newer = [v for _, v in history[-5:]]
    if not older or not newer:
        return None
    avg_old = sum(older) / len(older)
    avg_new = sum(newer) / len(newer)
    delta = avg_new - avg_old
    if abs(delta) < 0.00005:
        return "stable"
    return "rising" if delta > 0 else "falling"


def get_depth_cached(symbol: str, depth: int = 10) -> dict:
    """Cached orderbook depth. Returns {asks: [[price, vol, n]], bids: [[price, vol, n]]}."""
    now = time.time()
    cached = _depth_cache.get(symbol)
    if cached and (now - cached[0]) < _DEPTH_TTL_SECONDS:
        return cached[1]
    any_client = ACCOUNTS[0].client
    try:
        resp = any_client.depth(symbol, limit=depth)
    except Exception:
        return {}
    data = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(data, dict):
        return {}
    _depth_cache[symbol] = (now, data)
    return data


def _orderbook_imbalance(symbol: str) -> dict | None:
    """Compute bid/ask depth imbalance from top 10 levels."""
    depth = get_depth_cached(symbol, 10)
    asks = depth.get("asks") or []
    bids = depth.get("bids") or []
    if not asks or not bids:
        return None
    try:
        ask_vol = sum(float(row[1]) for row in asks[:10])
        bid_vol = sum(float(row[1]) for row in bids[:10])
    except (ValueError, TypeError, IndexError):
        return None
    total = ask_vol + bid_vol
    if total == 0:
        return None
    # +100 = all bids (max buy pressure), -100 = all asks (max sell pressure)
    imbalance_pct = ((bid_vol - ask_vol) / total) * 100
    return {
        "bid_vol": round(bid_vol, 4),
        "ask_vol": round(ask_vol, 4),
        "imbalance_pct": round(imbalance_pct, 2),
        "bias": "buy_pressure" if imbalance_pct > 15
                else "sell_pressure" if imbalance_pct < -15
                else "balanced",
    }


def _bollinger_lower(closes: list[float], period: int = 20, std_mult: float = 2.0) -> tuple[float, float, float] | None:
    """Return (lower, middle, upper) Bollinger Bands or None."""
    if len(closes) < period:
        return None
    recent = closes[-period:]
    mean = sum(recent) / period
    variance = sum((x - mean) ** 2 for x in recent) / period
    std = variance ** 0.5
    return (mean - std_mult * std, mean, mean + std_mult * std)


def _ema(closes: list[float], period: int) -> float | None:
    """Exponential moving average."""
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period  # seed with SMA
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def _rsi_series(closes: list[float], period: int = 14) -> list[float | None]:
    """Compute RSI for every bar (returns same length as closes, None for warmup bars)."""
    if len(closes) < period + 1:
        return [None] * len(closes)
    result: list[float | None] = [None] * period
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses += -diff
    avg_gain = gains / period
    avg_loss = losses / period
    rsi = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))
    result.append(rsi)
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gain = max(diff, 0)
        loss = max(-diff, 0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            result.append(100.0)
        else:
            rsi = 100 - (100 / (1 + avg_gain / avg_loss))
            result.append(rsi)
    return result


def _find_swing_lows(closes: list[float], left: int = 3, right: int = 3) -> list[int]:
    """Return indices where close is lowest of ±N neighbors (swing pivot)."""
    out = []
    for i in range(left, len(closes) - right):
        window = closes[i - left : i + right + 1]
        if closes[i] == min(window) and closes[i] < closes[i - 1]:
            out.append(i)
    return out


def _detect_bullish_divergence(
    closes: list[float], rsi_vals: list[float | None], lookback: int = 30
) -> bool:
    """Real RSI bullish divergence using swing pivot detection.

    Look for last 2 swing lows within lookback bars.
    Bullish divergence = newer swing has LOWER price + HIGHER RSI.
    """
    if len(closes) < lookback or len(rsi_vals) < lookback:
        return False
    recent_window = closes[-lookback:]
    rsi_window = rsi_vals[-lookback:]
    pivots = _find_swing_lows(recent_window, left=2, right=2)
    if len(pivots) < 2:
        return False
    # Take the 2 most recent pivots
    older_idx = pivots[-2]
    newer_idx = pivots[-1]
    older_price = recent_window[older_idx]
    newer_price = recent_window[newer_idx]
    older_rsi = rsi_window[older_idx]
    newer_rsi = rsi_window[newer_idx]
    if older_rsi is None or newer_rsi is None:
        return False
    # Need at least 1% price diff and 4 RSI diff to be meaningful
    price_lower = newer_price < older_price * 0.99
    rsi_higher = newer_rsi > older_rsi + 4
    return price_lower and rsi_higher


def _vwap_4h(bars: list[dict], period: int = 24) -> float | None:
    """Volume-weighted average price over last N bars."""
    if len(bars) < period:
        return None
    recent = bars[-period:]
    tot_vol = sum(b["v"] for b in recent)
    if tot_vol == 0:
        return None
    return sum(((b["h"] + b["l"] + b["c"]) / 3) * b["v"] for b in recent) / tot_vol


# ═══════════════════════════════════════════════════════════════════
# Candle pattern detection (multi-TF). All return True/False per pattern.
# ═══════════════════════════════════════════════════════════════════
def _true_range(prev: dict, curr: dict) -> float:
    """True Range: max(H-L, |H-prevC|, |L-prevC|)."""
    return max(
        curr["h"] - curr["l"],
        abs(curr["h"] - prev["c"]),
        abs(curr["l"] - prev["c"]),
    )


def _atr(bars: list[dict], period: int = 14) -> float | None:
    """Average True Range — measures volatility per bar."""
    if len(bars) < period + 1:
        return None
    trs = [_true_range(bars[i - 1], bars[i]) for i in range(1, len(bars))]
    recent = trs[-period:]
    return sum(recent) / len(recent) if recent else None


def _anchor_vwap(bars: list[dict], anchor_idx: int) -> float | None:
    """Volume-weighted average price anchored from bar index forward.

    anchor_idx: index into bars where to start anchoring (e.g., swing low).
    Returns cumulative VWAP from that point to last bar.
    """
    if anchor_idx >= len(bars) or anchor_idx < 0:
        return None
    sub = bars[anchor_idx:]
    if not sub:
        return None
    pv_sum = 0.0
    v_sum = 0.0
    for b in sub:
        typical = (b["h"] + b["l"] + b["c"]) / 3
        v = float(b.get("v") or 0)
        pv_sum += typical * v
        v_sum += v
    return pv_sum / v_sum if v_sum > 0 else None


def _candle_body(b: dict) -> float:
    return abs(b["c"] - b["o"])


def _candle_range(b: dict) -> float:
    return max(1e-12, b["h"] - b["l"])


def _is_bullish(b: dict) -> bool:
    return b["c"] > b["o"]


def _is_bearish(b: dict) -> bool:
    return b["c"] < b["o"]


def _bullish_engulfing(bars: list[dict]) -> bool:
    if len(bars) < 2:
        return False
    p, c = bars[-2], bars[-1]
    return (
        _is_bearish(p)
        and _is_bullish(c)
        and c["o"] <= p["c"]
        and c["c"] >= p["o"]
        and _candle_body(c) > _candle_body(p) * 1.0
    )


def _bearish_engulfing(bars: list[dict]) -> bool:
    if len(bars) < 2:
        return False
    p, c = bars[-2], bars[-1]
    return (
        _is_bullish(p)
        and _is_bearish(c)
        and c["o"] >= p["c"]
        and c["c"] <= p["o"]
        and _candle_body(c) > _candle_body(p) * 1.0
    )


def _hammer(bars: list[dict]) -> bool:
    """Bullish reversal: small body at top, long lower shadow."""
    if len(bars) < 1:
        return False
    b = bars[-1]
    body = _candle_body(b)
    rng = _candle_range(b)
    if body < rng * 0.05:
        return False
    lower_shadow = min(b["o"], b["c"]) - b["l"]
    upper_shadow = b["h"] - max(b["o"], b["c"])
    return lower_shadow > body * 2 and upper_shadow < body * 0.8


def _shooting_star(bars: list[dict]) -> bool:
    """Bearish reversal: small body at bottom, long upper shadow."""
    if len(bars) < 1:
        return False
    b = bars[-1]
    body = _candle_body(b)
    rng = _candle_range(b)
    if body < rng * 0.05:
        return False
    lower_shadow = min(b["o"], b["c"]) - b["l"]
    upper_shadow = b["h"] - max(b["o"], b["c"])
    return upper_shadow > body * 2 and lower_shadow < body * 0.8


def _doji(bars: list[dict]) -> bool:
    """Indecision: tiny body relative to range."""
    if len(bars) < 1:
        return False
    b = bars[-1]
    return _candle_body(b) < _candle_range(b) * 0.10


def _bullish_harami(bars: list[dict]) -> bool:
    """Small bullish candle inside larger bearish previous."""
    if len(bars) < 2:
        return False
    p, c = bars[-2], bars[-1]
    return (
        _is_bearish(p)
        and _is_bullish(c)
        and c["h"] < p["o"]
        and c["l"] > p["c"]
    )


def _bearish_harami(bars: list[dict]) -> bool:
    if len(bars) < 2:
        return False
    p, c = bars[-2], bars[-1]
    return (
        _is_bullish(p)
        and _is_bearish(c)
        and c["h"] < p["c"]
        and c["l"] > p["o"]
    )


def _morning_star(bars: list[dict]) -> bool:
    """Bullish 3-candle reversal: red, small body, strong green."""
    if len(bars) < 3:
        return False
    a, b, c = bars[-3], bars[-2], bars[-1]
    return (
        _is_bearish(a)
        and _candle_body(b) < _candle_body(a) * 0.4
        and _is_bullish(c)
        and c["c"] > (a["o"] + a["c"]) / 2
    )


def _evening_star(bars: list[dict]) -> bool:
    if len(bars) < 3:
        return False
    a, b, c = bars[-3], bars[-2], bars[-1]
    return (
        _is_bullish(a)
        and _candle_body(b) < _candle_body(a) * 0.4
        and _is_bearish(c)
        and c["c"] < (a["o"] + a["c"]) / 2
    )


def _three_white_soldiers(bars: list[dict]) -> bool:
    """3 consecutive strong green candles, each closing higher."""
    if len(bars) < 3:
        return False
    a, b, c = bars[-3], bars[-2], bars[-1]
    return (
        _is_bullish(a)
        and _is_bullish(b)
        and _is_bullish(c)
        and b["c"] > a["c"]
        and c["c"] > b["c"]
        and _candle_body(a) > _candle_range(a) * 0.5
        and _candle_body(b) > _candle_range(b) * 0.5
        and _candle_body(c) > _candle_range(c) * 0.5
    )


def _three_black_crows(bars: list[dict]) -> bool:
    if len(bars) < 3:
        return False
    a, b, c = bars[-3], bars[-2], bars[-1]
    return (
        _is_bearish(a)
        and _is_bearish(b)
        and _is_bearish(c)
        and b["c"] < a["c"]
        and c["c"] < b["c"]
        and _candle_body(a) > _candle_range(a) * 0.5
        and _candle_body(b) > _candle_range(b) * 0.5
        and _candle_body(c) > _candle_range(c) * 0.5
    )


# ═══════════════════════════════════════════════════════════════════
# More candle patterns: Pin bar, Tweezer, Dragonfly/Gravestone doji,
# Piercing line, Dark cloud cover, Inside/Outside bar
# ═══════════════════════════════════════════════════════════════════
def _bullish_pin_bar(bars: list[dict]) -> bool:
    """Strict pin bar bullish: tiny body at top, very long lower wick (≥2.5×body+upper)."""
    if not bars:
        return False
    b = bars[-1]
    body = _candle_body(b)
    rng = _candle_range(b)
    if rng < 1e-12:
        return False
    upper_shadow = b["h"] - max(b["o"], b["c"])
    lower_shadow = min(b["o"], b["c"]) - b["l"]
    return (
        lower_shadow > rng * 0.66
        and body < rng * 0.25
        and upper_shadow < body * 1.5
    )


def _bearish_pin_bar(bars: list[dict]) -> bool:
    if not bars:
        return False
    b = bars[-1]
    body = _candle_body(b)
    rng = _candle_range(b)
    if rng < 1e-12:
        return False
    upper_shadow = b["h"] - max(b["o"], b["c"])
    lower_shadow = min(b["o"], b["c"]) - b["l"]
    return (
        upper_shadow > rng * 0.66
        and body < rng * 0.25
        and lower_shadow < body * 1.5
    )


def _tweezer_bottom(bars: list[dict]) -> bool:
    """Two consecutive candles dengan low yang sangat dekat → bottom support."""
    if len(bars) < 2:
        return False
    p, c = bars[-2], bars[-1]
    low_diff = abs(p["l"] - c["l"]) / max(c["l"], 1e-12)
    return (
        low_diff < 0.002  # lows within 0.2%
        and _is_bearish(p)
        and _is_bullish(c)
    )


def _tweezer_top(bars: list[dict]) -> bool:
    if len(bars) < 2:
        return False
    p, c = bars[-2], bars[-1]
    high_diff = abs(p["h"] - c["h"]) / max(c["h"], 1e-12)
    return (
        high_diff < 0.002
        and _is_bullish(p)
        and _is_bearish(c)
    )


def _dragonfly_doji(bars: list[dict]) -> bool:
    """Doji bullish: tiny body at top, long lower wick."""
    if not bars:
        return False
    b = bars[-1]
    body = _candle_body(b)
    rng = _candle_range(b)
    if rng < 1e-12 or body >= rng * 0.10:
        return False
    upper_shadow = b["h"] - max(b["o"], b["c"])
    lower_shadow = min(b["o"], b["c"]) - b["l"]
    return lower_shadow > rng * 0.6 and upper_shadow < rng * 0.15


def _gravestone_doji(bars: list[dict]) -> bool:
    if not bars:
        return False
    b = bars[-1]
    body = _candle_body(b)
    rng = _candle_range(b)
    if rng < 1e-12 or body >= rng * 0.10:
        return False
    upper_shadow = b["h"] - max(b["o"], b["c"])
    lower_shadow = min(b["o"], b["c"]) - b["l"]
    return upper_shadow > rng * 0.6 and lower_shadow < rng * 0.15


def _piercing_line(bars: list[dict]) -> bool:
    """Bullish: red candle followed by green that closes above 50% of red body."""
    if len(bars) < 2:
        return False
    p, c = bars[-2], bars[-1]
    if not (_is_bearish(p) and _is_bullish(c)):
        return False
    p_mid = (p["o"] + p["c"]) / 2
    return c["o"] < p["c"] and c["c"] > p_mid and c["c"] < p["o"]


def _dark_cloud_cover(bars: list[dict]) -> bool:
    """Bearish: green candle followed by red that closes below 50% of green body."""
    if len(bars) < 2:
        return False
    p, c = bars[-2], bars[-1]
    if not (_is_bullish(p) and _is_bearish(c)):
        return False
    p_mid = (p["o"] + p["c"]) / 2
    return c["o"] > p["c"] and c["c"] < p_mid and c["c"] > p["o"]


def _inside_bar(bars: list[dict]) -> bool:
    """Current bar's range fully inside prior bar's range — consolidation."""
    if len(bars) < 2:
        return False
    p, c = bars[-2], bars[-1]
    return c["h"] < p["h"] and c["l"] > p["l"]


# ═══════════════════════════════════════════════════════════════════
# Smart Money Concepts: Liquidity Sweep, Order Block, FVG, BOS/CHOCH
# ═══════════════════════════════════════════════════════════════════
def detect_liquidity_sweep(bars: list[dict], lookback: int = 20) -> dict:
    """Stop hunt detection: wick above prior N-bar high, then close back below = bull sweep
    (whales took stops, now reversal often follows).

    Returns {bullish_sweep, bearish_sweep, sweep_strength (0-1)}.
    """
    if len(bars) < lookback + 1:
        return {"bullish_sweep": False, "bearish_sweep": False, "sweep_strength": 0}
    prior = bars[-lookback - 1 : -1]
    last = bars[-1]
    prior_high = max(b["h"] for b in prior)
    prior_low = min(b["l"] for b in prior)

    # Bullish sweep: low broke below prior_low but close back above
    bullish_sweep = last["l"] < prior_low and last["c"] > prior_low
    # Bearish sweep: high broke above prior_high but close back below
    bearish_sweep = last["h"] > prior_high and last["c"] < prior_high

    strength = 0.0
    if bullish_sweep:
        wick_size = prior_low - last["l"]
        body_size = max(_candle_body(last), 1e-12)
        strength = min(1.0, wick_size / body_size / 2)
    elif bearish_sweep:
        wick_size = last["h"] - prior_high
        body_size = max(_candle_body(last), 1e-12)
        strength = min(1.0, wick_size / body_size / 2)

    return {
        "bullish_sweep": bullish_sweep,
        "bearish_sweep": bearish_sweep,
        "sweep_strength": round(strength, 3),
        "prior_high": round(prior_high, 8),
        "prior_low": round(prior_low, 8),
    }


def detect_order_block(bars: list[dict]) -> dict:
    """Last opposite-color candle before strong impulse = order block (institutional zone).

    Bullish OB: last bearish candle before strong bullish impulse → support.
    Bearish OB: last bullish candle before strong bearish impulse → resistance.
    """
    if len(bars) < 5:
        return {"bullish_ob_zone": None, "bearish_ob_zone": None}

    out = {"bullish_ob_zone": None, "bearish_ob_zone": None}
    # Look for strong impulse in last 5 bars (body > 1.5× avg body of preceding 10)
    if len(bars) >= 15:
        avg_body = sum(_candle_body(b) for b in bars[-15:-5]) / 10 or 1e-12
        for i in range(len(bars) - 5, len(bars)):
            cur = bars[i]
            if _candle_body(cur) > avg_body * 1.5:
                if _is_bullish(cur) and i > 0:
                    # Find last bearish before this impulse
                    for j in range(i - 1, max(0, i - 5), -1):
                        if _is_bearish(bars[j]):
                            out["bullish_ob_zone"] = {
                                "high": round(bars[j]["h"], 8),
                                "low": round(bars[j]["l"], 8),
                                "bar_index_from_now": len(bars) - 1 - j,
                            }
                            break
                elif _is_bearish(cur) and i > 0:
                    for j in range(i - 1, max(0, i - 5), -1):
                        if _is_bullish(bars[j]):
                            out["bearish_ob_zone"] = {
                                "high": round(bars[j]["h"], 8),
                                "low": round(bars[j]["l"], 8),
                                "bar_index_from_now": len(bars) - 1 - j,
                            }
                            break
                break
    return out


def detect_fair_value_gap(bars: list[dict]) -> dict:
    """FVG: 3-candle pattern where middle candle's range doesn't overlap
    candle[i-2].high < candle[i].low (bullish FVG, magnet from above)
    candle[i-2].low > candle[i].high (bearish FVG)

    Returns list of recent unfilled FVGs.
    """
    if len(bars) < 3:
        return {"bullish_fvg": None, "bearish_fvg": None}
    out: dict = {"bullish_fvg": None, "bearish_fvg": None}
    # Check last 10 candles for FVG
    for i in range(max(2, len(bars) - 10), len(bars)):
        a = bars[i - 2]
        b = bars[i - 1]
        c = bars[i]
        # Bullish FVG: gap up where a.high < c.low
        if a["h"] < c["l"]:
            # Check if still unfilled (price hasn't traded into gap since)
            still_unfilled = all(later["l"] > a["h"] for later in bars[i + 1 :])
            if still_unfilled:
                out["bullish_fvg"] = {
                    "high": round(c["l"], 8),
                    "low": round(a["h"], 8),
                    "bar_index_from_now": len(bars) - 1 - i,
                }
        # Bearish FVG: gap down where a.low > c.high
        if a["l"] > c["h"]:
            still_unfilled = all(later["h"] < a["l"] for later in bars[i + 1 :])
            if still_unfilled:
                out["bearish_fvg"] = {
                    "high": round(a["l"], 8),
                    "low": round(c["h"], 8),
                    "bar_index_from_now": len(bars) - 1 - i,
                }
    return out


def detect_market_structure(bars: list[dict], lookback: int = 30) -> dict:
    """Detect BOS (Break of Structure) / CHOCH (Change of Character).

    BOS bullish: price broke above last swing high → continuation
    BOS bearish: price broke below last swing low → continuation
    CHOCH: structure shift (HH→LL or LL→HH)
    """
    if len(bars) < lookback:
        return {"bos_bullish": False, "bos_bearish": False, "choch": None, "structure": None}

    closes = [b["c"] for b in bars[-lookback:]]
    highs = [b["h"] for b in bars[-lookback:]]
    lows = [b["l"] for b in bars[-lookback:]]

    # Find swing highs/lows in window (3-bar pivot)
    swing_highs = []
    swing_lows = []
    for i in range(2, len(closes) - 2):
        if highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and highs[i] > highs[i + 1] and highs[i] > highs[i + 2]:
            swing_highs.append((i, highs[i]))
        if lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and lows[i] < lows[i + 1] and lows[i] < lows[i + 2]:
            swing_lows.append((i, lows[i]))

    last_high = swing_highs[-1][1] if swing_highs else None
    last_low = swing_lows[-1][1] if swing_lows else None
    current = closes[-1]

    bos_bull = last_high is not None and current > last_high * 1.001
    bos_bear = last_low is not None and current < last_low * 0.999

    # Structure trend (simplified)
    structure = None
    if len(swing_highs) >= 2 and len(swing_lows) >= 2:
        higher_highs = swing_highs[-1][1] > swing_highs[-2][1]
        higher_lows = swing_lows[-1][1] > swing_lows[-2][1]
        lower_highs = swing_highs[-1][1] < swing_highs[-2][1]
        lower_lows = swing_lows[-1][1] < swing_lows[-2][1]
        if higher_highs and higher_lows:
            structure = "uptrend (HH+HL)"
        elif lower_highs and lower_lows:
            structure = "downtrend (LH+LL)"
        elif higher_lows and lower_highs:
            structure = "compression"
        else:
            structure = "mixed"

    return {
        "bos_bullish": bos_bull,
        "bos_bearish": bos_bear,
        "structure": structure,
        "last_swing_high": round(last_high, 8) if last_high else None,
        "last_swing_low": round(last_low, 8) if last_low else None,
    }


# ═══════════════════════════════════════════════════════════════════
# Wyckoff phase classifier + Whale accumulation flag
# ═══════════════════════════════════════════════════════════════════
def classify_wyckoff_phase(bars: list[dict], oi_history: list[tuple[float, float]] | None = None) -> dict:
    """Classify market phase using price action + volume + OI.

    Heuristic:
    - Accumulation: price sideways/down + volume slowly rising + OI rising = smart money buying
    - Mark-up: price rising + volume rising + OI rising = trend continuation
    - Distribution: price sideways/up at top + volume rising + OI flat-falling = smart money selling
    - Mark-down: price falling + volume rising + OI falling = trend continuation down
    """
    if len(bars) < 20:
        return {"phase": "unknown", "confidence": 0}

    recent = bars[-20:]
    closes = [b["c"] for b in recent]
    vols = [b["v"] for b in recent]

    # Price slope (% change first→last)
    price_slope = (closes[-1] - closes[0]) / max(closes[0], 1e-12) * 100
    # Price volatility (std / mean)
    mean_p = sum(closes) / len(closes)
    var = sum((c - mean_p) ** 2 for c in closes) / len(closes)
    std_p = var ** 0.5
    volatility_pct = (std_p / max(mean_p, 1e-12)) * 100

    # Volume trend (last 5 vs prior 15 avg)
    last5_vol = sum(vols[-5:]) / 5
    prior15_vol = sum(vols[:-5]) / 15 if len(vols) > 5 else 1
    vol_ratio = last5_vol / max(prior15_vol, 1e-12)

    # OI direction (last vs prior)
    oi_trend = "flat"
    if oi_history and len(oi_history) >= 10:
        oi_vals = [v for _, v in oi_history[-10:]]
        oi_slope = (oi_vals[-1] - oi_vals[0]) / max(oi_vals[0], 1e-12) * 100
        if oi_slope > 2:
            oi_trend = "rising"
        elif oi_slope < -2:
            oi_trend = "falling"

    phase = "unknown"
    confidence = 0
    if abs(price_slope) < 2 and volatility_pct < 3 and oi_trend == "rising":
        phase = "accumulation"
        confidence = 75 if vol_ratio > 1.1 else 60
    elif abs(price_slope) < 2 and volatility_pct < 3 and oi_trend == "falling":
        phase = "distribution"
        confidence = 70
    elif price_slope > 3 and vol_ratio > 1.2 and oi_trend == "rising":
        phase = "mark-up"
        confidence = 80
    elif price_slope < -3 and vol_ratio > 1.2 and oi_trend == "falling":
        phase = "mark-down"
        confidence = 80
    elif price_slope < -3 and vol_ratio > 1.5:
        phase = "capitulation"
        confidence = 70
    elif abs(price_slope) < 1 and volatility_pct < 2:
        phase = "consolidation"
        confidence = 50

    return {
        "phase": phase,
        "confidence": confidence,
        "price_slope_pct": round(price_slope, 2),
        "volatility_pct": round(volatility_pct, 2),
        "vol_ratio": round(vol_ratio, 2),
        "oi_trend": oi_trend,
    }


def detect_whale_accumulation(
    bars: list[dict], oi_history: list[tuple[float, float]] | None = None
) -> dict:
    """Detect stealth whale accumulation: OI rising significantly while price stays flat
    AND volume increasing → big money loading without moving price."""
    if not oi_history or len(oi_history) < 30 or len(bars) < 20:
        return {"detected": False, "intensity": 0}

    # OI change over last 30min
    oi_recent = [v for _, v in oi_history[-30:]]
    oi_slope = (oi_recent[-1] - oi_recent[0]) / max(oi_recent[0], 1e-12) * 100

    # Price change over same window (last 30 bars from bars... but bars are 4h)
    # Use last 10 bars of whatever the input is
    closes = [b["c"] for b in bars[-10:]]
    price_change = abs((closes[-1] - closes[0]) / max(closes[0], 1e-12)) * 100

    vols = [b["v"] for b in bars[-10:]]
    last_vol = sum(vols[-3:]) / 3
    prior_vol = sum(vols[:-3]) / max(1, len(vols) - 3)
    vol_ratio = last_vol / max(prior_vol, 1e-12)

    # Whale accumulation:
    # OI rising 5%+ in last 30 samples (typically 30min)
    # AND price relatively flat (<2% change)
    # AND volume normal-to-elevated
    detected = oi_slope > 5 and price_change < 2 and vol_ratio > 0.8
    intensity = min(100, int(oi_slope * 4)) if detected else 0

    return {
        "detected": detected,
        "intensity": intensity,
        "oi_change_pct": round(oi_slope, 2),
        "price_change_pct": round(price_change, 2),
    }


def detect_candle_patterns(bars: list[dict]) -> dict:
    """Return all detected patterns at last bar."""
    if not bars:
        return {}
    return {
        "bullish_engulfing": _bullish_engulfing(bars),
        "bearish_engulfing": _bearish_engulfing(bars),
        "hammer": _hammer(bars),
        "shooting_star": _shooting_star(bars),
        "doji": _doji(bars),
        "bullish_harami": _bullish_harami(bars),
        "bearish_harami": _bearish_harami(bars),
        "morning_star": _morning_star(bars),
        "evening_star": _evening_star(bars),
        "three_white_soldiers": _three_white_soldiers(bars),
        "three_black_crows": _three_black_crows(bars),
        "bullish_pin_bar": _bullish_pin_bar(bars),
        "bearish_pin_bar": _bearish_pin_bar(bars),
        "tweezer_bottom": _tweezer_bottom(bars),
        "tweezer_top": _tweezer_top(bars),
        "dragonfly_doji": _dragonfly_doji(bars),
        "gravestone_doji": _gravestone_doji(bars),
        "piercing_line": _piercing_line(bars),
        "dark_cloud_cover": _dark_cloud_cover(bars),
        "inside_bar": _inside_bar(bars),
    }


def _mtf_rsi_sequence_score(
    rsi_15m: float | None,
    rsi_1h: float | None,
    rsi_4h: float | None,
    rsi_1d: float | None,
    direction: str = "LONG",
) -> int:
    """Telescoping MTF shift detector. Lower TFs turn FIRST = real reversal.

    LONG: 15m > 1h > 4h, 4h still low (early bullish recovery)
    SHORT: 15m < 1h < 4h, 4h still high (early bearish distribution)
    """
    vals = [rsi_15m, rsi_1h, rsi_4h, rsi_1d]
    if any(v is None for v in vals):
        return 0
    if direction == "LONG":
        if (
            rsi_15m > rsi_1h
            and rsi_1h > rsi_4h
            and rsi_4h < 45
            and rsi_15m > 35
        ):
            return 12
    elif direction == "SHORT":
        # Mirror: 15m dropping faster than higher TFs while HTF still elevated
        if (
            rsi_15m < rsi_1h
            and rsi_1h < rsi_4h
            and rsi_4h > 55
            and rsi_15m < 65
        ):
            return 12
    return 0


def _detect_bearish_divergence(
    closes: list[float], rsi_series: list[float | None], lookback: int = 20
) -> bool:
    """Bearish divergence: price makes higher-high, RSI makes lower-high.

    Mirror of _detect_bullish_divergence. Signals distribution / topping.
    """
    if len(closes) < lookback or len(rsi_series) < lookback:
        return False
    recent_closes = closes[-lookback:]
    recent_rsi = rsi_series[-lookback:]
    swing_highs = _find_swing_highs(recent_closes, left=3, right=3)
    if len(swing_highs) < 2:
        return False
    last_two = swing_highs[-2:]
    i1, i2 = last_two[0], last_two[1]
    price_higher = recent_closes[i2] > recent_closes[i1]
    rsi_at_1 = recent_rsi[i1]
    rsi_at_2 = recent_rsi[i2]
    if rsi_at_1 is None or rsi_at_2 is None:
        return False
    rsi_lower = rsi_at_2 < rsi_at_1
    return price_higher and rsi_lower


def _find_swing_highs(closes: list[float], left: int = 3, right: int = 3) -> list[int]:
    """Find indices where close[i] is highest in window [i-left, i+right]."""
    out: list[int] = []
    for i in range(left, len(closes) - right):
        window = closes[i - left:i + right + 1]
        if closes[i] == max(window):
            out.append(i)
    return out


def _three_bar_reversal(bars: list[dict]) -> bool:
    """Bullish reversal: 2+ red bars followed by 1 strong green bar.

    Last bar: green AND larger body than avg of prior 3 reds.
    """
    if len(bars) < 4:
        return False
    last = bars[-1]
    prior = bars[-4:-1]
    last_green = last["c"] > last["o"]
    if not last_green:
        return False
    prior_reds = sum(1 for b in prior if b["c"] < b["o"])
    if prior_reds < 2:
        return False
    last_body = abs(last["c"] - last["o"])
    avg_prior_body = sum(abs(b["c"] - b["o"]) for b in prior) / 3
    return last_body > avg_prior_body * 0.8  # last green at least 80% of avg prior body

def detect_candle_patterns_rich(bars: list[dict]) -> list[dict]:
    """Scan last 3 bars for any detected patterns, return list with metadata.

    Each entry: {pattern, bullish, bar_index_from_now, open/high/low/close,
                 trigger_price, confirmed, confirmation_bar_close}
    - bar_index_from_now=0 means latest closed bar
    - trigger_price = the level a trader watches (high for bullish, low for bearish)
    - confirmed = True if a LATER bar's close exceeded trigger price (pattern validated)
    """
    if not bars:
        return []

    PATTERN_SPECS: list[tuple[str, object, bool | None, int, str]] = [
        ("bullish_engulfing", _bullish_engulfing, True, 2, "high"),
        ("bearish_engulfing", _bearish_engulfing, False, 2, "low"),
        ("hammer", _hammer, True, 1, "high"),
        ("shooting_star", _shooting_star, False, 1, "low"),
        ("bullish_pin_bar", _bullish_pin_bar, True, 1, "high"),
        ("bearish_pin_bar", _bearish_pin_bar, False, 1, "low"),
        ("dragonfly_doji", _dragonfly_doji, True, 1, "high"),
        ("gravestone_doji", _gravestone_doji, False, 1, "low"),
        ("morning_star", _morning_star, True, 3, "high"),
        ("evening_star", _evening_star, False, 3, "low"),
        ("three_white_soldiers", _three_white_soldiers, True, 3, "high"),
        ("three_black_crows", _three_black_crows, False, 3, "low"),
        ("piercing_line", _piercing_line, True, 2, "high"),
        ("dark_cloud_cover", _dark_cloud_cover, False, 2, "low"),
        ("tweezer_bottom", _tweezer_bottom, True, 2, "high"),
        ("tweezer_top", _tweezer_top, False, 2, "low"),
        ("bullish_harami", _bullish_harami, True, 2, "high"),
        ("bearish_harami", _bearish_harami, False, 2, "low"),
        ("doji", _doji, None, 1, "close"),
        ("inside_bar", _inside_bar, None, 2, "close"),
    ]

    seen: set[str] = set()
    detected: list[dict] = []
    for offset in range(0, min(3, len(bars))):
        scan_bars = bars[: len(bars) - offset] if offset > 0 else bars
        if not scan_bars:
            continue
        last = scan_bars[-1]
        for name, detector, bullish, min_bars, trigger_logic in PATTERN_SPECS:
            if name in seen or len(scan_bars) < min_bars:
                continue
            try:
                if detector(scan_bars):  # type: ignore
                    if trigger_logic == "high":
                        trigger = last["h"]
                    elif trigger_logic == "low":
                        trigger = last["l"]
                    else:
                        trigger = last["c"]
                    seen.add(name)

                    # Phase 7: Confirmation check
                    # Pattern confirmed if any later bar (after detection bar) closed
                    # beyond the trigger in the pattern's direction.
                    confirmed = False
                    confirmation_close = None
                    if offset > 0:
                        # Look at bars AFTER the detection bar (i.e. bars[len-offset:])
                        post_bars = bars[len(bars) - offset:]
                        for pb in post_bars:
                            if bullish is True:
                                if pb["c"] > trigger:
                                    confirmed = True
                                    confirmation_close = round(pb["c"], 8)
                                    break
                            elif bullish is False:
                                if pb["c"] < trigger:
                                    confirmed = True
                                    confirmation_close = round(pb["c"], 8)
                                    break
                            else:
                                # Neutral patterns (doji, inside_bar) need follow-through both ways
                                pass
                    detected.append({
                        "pattern": name,
                        "bullish": bullish,
                        "bar_index_from_now": offset,
                        "open": round(last["o"], 8),
                        "high": round(last["h"], 8),
                        "low": round(last["l"], 8),
                        "close": round(last["c"], 8),
                        "trigger_price": round(trigger, 8),
                        "confirmed": confirmed,
                        "confirmation_close": confirmation_close,
                    })
            except Exception:
                continue
    return detected


def detect_liquidity_grab(bars: list[dict], lookback: int = 20) -> dict:
    """Phase 7: Liquidity grab pattern — strongest reversal signal.

    Bullish grab: bar's low < lookback_low (sweep stops) AND close > lookback_low
                  (close back above) within same bar. Wick down then reject.
    Bearish grab: bar's high > lookback_high AND close < lookback_high.

    Scans last 3 bars to detect recent grabs.
    """
    out = {
        "bullish_grab": False,
        "bearish_grab": False,
        "bar_index_from_now": None,
        "grab_low": None,
        "grab_high": None,
        "broken_low": None,
        "broken_high": None,
        "rejection_pct": None,
    }
    if len(bars) < lookback + 3:
        return out

    for offset in range(0, 3):
        idx = len(bars) - 1 - offset
        if idx < lookback:
            continue
        bar = bars[idx]
        window = bars[idx - lookback:idx]
        if not window:
            continue
        prior_low = min(b["l"] for b in window)
        prior_high = max(b["h"] for b in window)

        # Bullish grab: wicked below prior_low but closed back above
        if bar["l"] < prior_low and bar["c"] > prior_low:
            wick_size = prior_low - bar["l"]
            close_back = bar["c"] - bar["l"]
            if close_back > wick_size * 1.5:  # strong rejection
                out["bullish_grab"] = True
                out["bar_index_from_now"] = offset
                out["grab_low"] = round(bar["l"], 8)
                out["broken_low"] = round(prior_low, 8)
                out["rejection_pct"] = round(close_back / (bar["h"] - bar["l"] + 1e-12) * 100, 2)
                return out

        # Bearish grab
        if bar["h"] > prior_high and bar["c"] < prior_high:
            wick_size = bar["h"] - prior_high
            close_back = bar["h"] - bar["c"]
            if close_back > wick_size * 1.5:
                out["bearish_grab"] = True
                out["bar_index_from_now"] = offset
                out["grab_high"] = round(bar["h"], 8)
                out["broken_high"] = round(prior_high, 8)
                out["rejection_pct"] = round(close_back / (bar["h"] - bar["l"] + 1e-12) * 100, 2)
                return out

    return out


def compute_volume_confirmation(bars: list[dict], recent_n: int = 3, baseline_n: int = 20) -> dict:
    """Phase 7: Volume confirmation — recent activity above baseline.

    Returns: {confirmed, ratio, recent_avg, baseline_avg}
    confirmed = recent_avg > 1.2 × baseline_avg
    """
    if len(bars) < recent_n + baseline_n:
        return {"confirmed": False, "ratio": None, "recent_avg": None, "baseline_avg": None}
    recent = bars[-recent_n:]
    baseline = bars[-(recent_n + baseline_n):-recent_n]
    recent_avg = sum(float(b.get("v") or 0) for b in recent) / len(recent)
    baseline_avg = sum(float(b.get("v") or 0) for b in baseline) / len(baseline)
    if baseline_avg <= 0:
        return {"confirmed": False, "ratio": None, "recent_avg": recent_avg, "baseline_avg": baseline_avg}
    ratio = recent_avg / baseline_avg
    return {
        "confirmed": ratio > 1.2,
        "ratio": round(ratio, 3),
        "recent_avg": round(recent_avg, 2),
        "baseline_avg": round(baseline_avg, 2),
    }


def compute_funding_window_status(funding: dict | None) -> dict:
    """Phase 7: Funding settlement countdown status.

    near_settlement = True if <30 minutes to next funding settle.
    Pre-settlement window often whipsaws against dominant funding side.
    """
    out = {
        "near_settlement": False,
        "minutes_to_settle": None,
        "settlement_warning": None,
    }
    if not funding or not funding.get("next_settle_ms"):
        return out
    try:
        next_settle = int(funding["next_settle_ms"])
        now_ms = int(time.time() * 1000)
        minutes = (next_settle - now_ms) / 60000
        out["minutes_to_settle"] = round(minutes, 1)
        if 0 < minutes < 30:
            out["near_settlement"] = True
            rate = funding.get("rate", 0)
            if rate > 0.0005:
                out["settlement_warning"] = (
                    f"Settle dalam {minutes:.0f} mnt. Funding {rate*100:.3f}% — "
                    "longs bayar. Sering whipsaw turun sebelum settle."
                )
            elif rate < -0.0005:
                out["settlement_warning"] = (
                    f"Settle dalam {minutes:.0f} mnt. Funding {rate*100:.3f}% — "
                    "shorts bayar. Sering whipsaw naik sebelum settle."
                )
            else:
                out["settlement_warning"] = f"Settle dalam {minutes:.0f} mnt — hindari entry baru."
    except Exception:
        pass
    return out


def detect_wyckoff_spring_upthrust(bars: list[dict], lookback: int = 30) -> dict:
    """Spring: false break BELOW recent support + close back above. Bullish.
    Upthrust: false break ABOVE recent resistance + close back below. Bearish.

    Looks at last 3 bars vs the support/resistance of bars[-lookback:-3].
    """
    out = {
        "spring": False,
        "upthrust": False,
        "spring_bar_index_from_now": None,
        "upthrust_bar_index_from_now": None,
        "spring_low": None,
        "upthrust_high": None,
        "broken_support": None,
        "broken_resistance": None,
    }
    if len(bars) < lookback + 3:
        return out
    recent = bars[-lookback:]
    range_bars = recent[:-3]
    if not range_bars:
        return out
    support = min(b["l"] for b in range_bars)
    resistance = max(b["h"] for b in range_bars)
    last3 = recent[-3:]
    for i, b in enumerate(last3):
        bar_offset = 2 - i  # offset from now: last3[2] is current
        if b["l"] < support * 0.998 and b["c"] > support * 1.001:
            out["spring"] = True
            out["spring_bar_index_from_now"] = bar_offset
            out["spring_low"] = round(b["l"], 8)
            out["broken_support"] = round(support, 8)
            break
    for i, b in enumerate(last3):
        bar_offset = 2 - i
        if b["h"] > resistance * 1.002 and b["c"] < resistance * 0.999:
            out["upthrust"] = True
            out["upthrust_bar_index_from_now"] = bar_offset
            out["upthrust_high"] = round(b["h"], 8)
            out["broken_resistance"] = round(resistance, 8)
            break
    return out


def detect_supply_demand_zones(bars: list[dict], lookback: int = 60) -> dict:
    """Drop-Base-Rally (demand) / Rally-Base-Drop (supply) zone detection.

    Algorithm:
    1. Scan for impulsive moves (body > avg_range × 1.5)
    2. Look 1-5 bars before for "base" (small bodies)
    3. Zone = high-low of base bars
    4. Untested = no later candle has wicked into the zone
    """
    if len(bars) < lookback:
        return {"demand_zones": [], "supply_zones": []}
    recent = bars[-lookback:]
    ranges = [_candle_range(b) for b in recent]
    avg_range = sum(ranges) / max(1, len(ranges))
    if avg_range <= 0:
        return {"demand_zones": [], "supply_zones": []}

    demand_zones: list[dict] = []
    supply_zones: list[dict] = []
    for i in range(3, len(recent) - 2):
        bar = recent[i]
        body = _candle_body(bar)
        if body < avg_range * 1.3:
            continue
        is_up = bar["c"] > bar["o"]
        base_start = max(0, i - 4)
        base_bars = recent[base_start:i]
        if not base_bars:
            continue
        base_bodies = [_candle_body(b) for b in base_bars]
        if max(base_bodies, default=0) > avg_range * 0.95:
            continue
        zone_high = max(b["h"] for b in base_bars)
        zone_low = min(b["l"] for b in base_bars)
        after = recent[i + 1:]
        tested = False
        for b in after:
            if b["l"] <= zone_high and b["h"] >= zone_low:
                tested = True
                break
        zone = {
            "high": round(zone_high, 8),
            "low": round(zone_low, 8),
            "mid": round((zone_high + zone_low) / 2, 8),
            "bar_index_from_now": len(recent) - 1 - i,
            "tested": tested,
            "fresh": not tested,
            "impulse_strength": round(body / avg_range, 2),
        }
        (demand_zones if is_up else supply_zones).append(zone)
    demand_zones.sort(key=lambda z: (z["tested"], z["bar_index_from_now"]))
    supply_zones.sort(key=lambda z: (z["tested"], z["bar_index_from_now"]))
    return {"demand_zones": demand_zones[:4], "supply_zones": supply_zones[:4]}


def compute_volume_profile(bars: list[dict], bins: int = 24) -> dict:
    """Volume profile: POC, VAH, VAL, HVN, LVN from kline volumes.

    POC = price level with highest aggregated volume
    Value Area = price range containing 70% of total volume
    HVN/LVN = High/Low Volume Nodes (relative to mean)
    """
    if not bars:
        return {"poc": None, "vah": None, "val": None, "histogram": [], "hvn": [], "lvn": []}
    low = min(b["l"] for b in bars)
    high = max(b["h"] for b in bars)
    if high <= low:
        return {"poc": None, "vah": None, "val": None, "histogram": [], "hvn": [], "lvn": []}
    bin_size = (high - low) / bins
    histogram = [0.0] * bins
    for b in bars:
        bar_vol = float(b.get("v") or 0)
        if bar_vol <= 0:
            continue
        bar_low = b["l"]
        bar_high = b["h"]
        start_bin = max(0, int((bar_low - low) / bin_size))
        end_bin = min(bins - 1, int((bar_high - low) / bin_size))
        span = max(1, end_bin - start_bin + 1)
        per_bin = bar_vol / span
        for bi in range(start_bin, end_bin + 1):
            histogram[bi] += per_bin

    total = sum(histogram)
    if total == 0:
        return {"poc": None, "vah": None, "val": None, "histogram": [], "hvn": [], "lvn": []}
    poc_idx = max(range(bins), key=lambda i: histogram[i])
    poc_price = low + (poc_idx + 0.5) * bin_size

    target = total * 0.70
    captured = histogram[poc_idx]
    lo_idx = poc_idx
    hi_idx = poc_idx
    while captured < target and (lo_idx > 0 or hi_idx < bins - 1):
        lo_val = histogram[lo_idx - 1] if lo_idx > 0 else -1
        hi_val = histogram[hi_idx + 1] if hi_idx < bins - 1 else -1
        if lo_val >= hi_val and lo_idx > 0:
            lo_idx -= 1
            captured += histogram[lo_idx]
        elif hi_idx < bins - 1:
            hi_idx += 1
            captured += histogram[hi_idx]
        elif lo_idx > 0:
            lo_idx -= 1
            captured += histogram[lo_idx]
        else:
            break

    val_price = low + lo_idx * bin_size
    vah_price = low + (hi_idx + 1) * bin_size
    mean_vol = total / bins
    hvn: list[dict] = []
    lvn: list[dict] = []
    histogram_out: list[dict] = []
    for i, v in enumerate(histogram):
        price = low + (i + 0.5) * bin_size
        ratio = v / mean_vol if mean_vol > 0 else 0
        histogram_out.append({"price": round(price, 8), "volume": round(v, 2), "ratio": round(ratio, 2)})
        if ratio > 1.5:
            hvn.append({"price": round(price, 8), "volume_ratio": round(ratio, 2)})
        elif 0 < ratio < 0.3:
            lvn.append({"price": round(price, 8), "volume_ratio": round(ratio, 2)})

    return {
        "poc": round(poc_price, 8),
        "vah": round(vah_price, 8),
        "val": round(val_price, 8),
        "range_high": round(high, 8),
        "range_low": round(low, 8),
        "histogram": histogram_out,
        "hvn": sorted(hvn, key=lambda x: -x["volume_ratio"])[:5],
        "lvn": sorted(lvn, key=lambda x: x["volume_ratio"])[:5],
    }


def detect_liquidation_cluster(
    bars_1h: list[dict],
    oi_history: list[tuple[float, float]],
    funding_rate: float | None,
) -> dict:
    """Detect potential liquidation cascade setup.

    Setup: OI surge >5% + tight price compression + funding extreme
    → leveraged side piled up. Next big move = squeeze.
    """
    out = {
        "detected": False,
        "side": None,
        "oi_surge_pct": None,
        "funding_extreme": None,
        "compression": False,
        "range_pct": None,
    }
    if len(bars_1h) < 6 or not oi_history or len(oi_history) < 6:
        return out
    oi_now = oi_history[-1][1]
    oi_then = oi_history[-6][1]
    if oi_then <= 0:
        return out
    oi_surge_pct = (oi_now - oi_then) / oi_then * 100
    out["oi_surge_pct"] = round(oi_surge_pct, 2)
    last5 = bars_1h[-5:]
    high5 = max(b["h"] for b in last5)
    low5 = min(b["l"] for b in last5)
    price = last5[-1]["c"]
    range_pct = (high5 - low5) / price * 100 if price > 0 else 0
    out["range_pct"] = round(range_pct, 2)
    out["compression"] = range_pct < 3.0
    if abs(oi_surge_pct) < 3 or not out["compression"]:
        return out
    if funding_rate is not None:
        if funding_rate > 0.0005:
            out["funding_extreme"] = "long_crowded"
            out["side"] = "long_squeeze"
            out["detected"] = True
        elif funding_rate < -0.0005:
            out["funding_extreme"] = "short_crowded"
            out["side"] = "short_squeeze"
            out["detected"] = True
    if not out["detected"] and abs(oi_surge_pct) > 8:
        out["detected"] = True
        out["side"] = "long_squeeze" if oi_surge_pct > 0 else "short_squeeze"
    return out


def compute_mtf_convergence(
    trend_4h: str | None,
    sweep_4h: dict | None,
    market_structure_4h: dict | None,
    candles_15m_rich: list[dict],
    candles_1h_rich: list[dict],
    candles_4h_rich: list[dict],
    direction: str,
) -> dict:
    """Multi-TF alignment scoring 0-100 for a given direction.

    Weighting:
      - 4h trend alignment: 30
      - 4h structure (BOS) alignment: 15
      - 4h sweep alignment: 15
      - 4h candle pattern alignment: 15
      - 1h candle pattern alignment: 15
      - 15m candle pattern alignment: 10
    """
    score = 0
    factors: list[str] = []
    is_long = direction == "LONG"

    if direction == "LONG" and trend_4h == "uptrend":
        score += 30
        factors.append("4h uptrend ✓")
    elif direction == "SHORT" and trend_4h == "downtrend":
        score += 30
        factors.append("4h downtrend ✓")
    elif trend_4h == "sideways":
        score += 10
        factors.append("4h sideways (netral)")

    if market_structure_4h:
        if direction == "LONG" and market_structure_4h.get("bos_bullish"):
            score += 15
            factors.append("4h BOS bullish ✓")
        elif direction == "SHORT" and market_structure_4h.get("bos_bearish"):
            score += 15
            factors.append("4h BOS bearish ✓")

    if sweep_4h:
        if direction == "LONG" and sweep_4h.get("bullish_sweep"):
            score += 15
            factors.append("4h bullish sweep ✓")
        elif direction == "SHORT" and sweep_4h.get("bearish_sweep"):
            score += 15
            factors.append("4h bearish sweep ✓")

    def _aligned(patterns: list[dict]) -> int:
        if not patterns:
            return 0
        bullish = sum(1 for p in patterns if p.get("bullish") is True)
        bearish = sum(1 for p in patterns if p.get("bullish") is False)
        if is_long:
            return bullish - bearish
        return bearish - bullish

    a4 = _aligned(candles_4h_rich)
    a1 = _aligned(candles_1h_rich)
    a15 = _aligned(candles_15m_rich)
    if a4 > 0:
        score += 15
        factors.append(f"4h candle aligned (+{a4})")
    if a1 > 0:
        score += 15
        factors.append(f"1h candle aligned (+{a1})")
    if a15 > 0:
        score += 10
        factors.append(f"15m candle aligned (+{a15})")
    return {
        "score": min(100, score),
        "factors": factors,
        "tf_breakdown": {
            "trend_4h": trend_4h,
            "bos_4h_bullish": (market_structure_4h or {}).get("bos_bullish", False),
            "bos_4h_bearish": (market_structure_4h or {}).get("bos_bearish", False),
            "sweep_4h_bullish": (sweep_4h or {}).get("bullish_sweep", False),
            "sweep_4h_bearish": (sweep_4h or {}).get("bearish_sweep", False),
            "candle_4h_net": a4,
            "candle_1h_net": a1,
            "candle_15m_net": a15,
        },
    }


def cvd_historical_per_bar(bars_1h: list[dict], deals: list[dict] | None = None) -> dict | None:
    """Compute historical Cumulative Volume Delta from kline OHLCV.

    Standard industry proxy when tick-level trades unavailable:
        delta = volume × (2×close − high − low) / (high − low)
        buy_vol  = volume × (close − low) / (high − low)
        sell_vol = volume × (high − close) / (high − low)

    This is what Coinglass / TradingView use under the hood for CVD on bar data.

    Optionally enriches the most recent bar with actual deals when available.
    """
    if not bars_1h or len(bars_1h) < 5:
        return None

    history: list[dict] = []
    cvd = 0.0
    for b in bars_1h:
        h = b["h"]
        lo = b["l"]
        c = b["c"]
        v = float(b.get("v") or 0)
        rng = h - lo
        if rng <= 0 or v <= 0:
            buy_v = 0.0
            sell_v = 0.0
            delta = 0.0
        else:
            # Position of close within bar range. (2c-h-l)/range ∈ [-1, +1]
            # +1 = close at high (all buying), -1 = close at low (all selling)
            position = (2 * c - h - lo) / rng
            delta = v * position
            buy_v = v * (c - lo) / rng
            sell_v = v * (h - c) / rng
        cvd += delta
        history.append({
            "ts": int(b["t"]),
            "price_close": c,
            "delta": round(delta, 2),
            "cvd": round(cvd, 2),
            "buy_vol": round(buy_v, 2),
            "sell_vol": round(sell_v, 2),
            "trades": 0,
            "range_pct": round((rng / c * 100), 3) if c > 0 else 0,
        })

    # Enrich most recent bar with real deals data if available (more accurate for "now")
    if deals and history:
        last_bar = history[-1]
        bar_ts_ms = last_bar["ts"]
        bar_end_ms = bar_ts_ms + 60 * 60 * 1000
        buy_real = 0.0
        sell_real = 0.0
        trades_real = 0
        for d in deals:
            try:
                dts = int(d.get("t") or d.get("ts") or 0)
                dvol = float(d.get("v") or d.get("vol") or 0)
            except Exception:
                continue
            if dvol <= 0 or dts < bar_ts_ms or dts >= bar_end_ms:
                continue
            side = d.get("T")
            if side == 1:
                buy_real += dvol
            elif side == 2:
                sell_real += dvol
            trades_real += 1
        if (buy_real + sell_real) > 0:
            real_delta = buy_real - sell_real
            # Propagate diff into cumulative
            diff = real_delta - last_bar["delta"]
            last_bar["delta"] = round(real_delta, 2)
            last_bar["buy_vol"] = round(buy_real, 2)
            last_bar["sell_vol"] = round(sell_real, 2)
            last_bar["trades"] = trades_real
            last_bar["cvd"] = round(last_bar["cvd"] + diff, 2)
            cvd = last_bar["cvd"]

    # Divergence detection (last 5 bars vs prior 5)
    divergence = None
    if len(history) >= 10:
        last5 = history[-5:]
        prev5 = history[-10:-5]
        last_price_high = max(h["price_close"] for h in last5)
        prev_price_high = max(h["price_close"] for h in prev5)
        last_price_low = min(h["price_close"] for h in last5)
        prev_price_low = min(h["price_close"] for h in prev5)
        last_cvd = last5[-1]["cvd"]
        prev_cvd = prev5[-1]["cvd"]
        if last_price_high > prev_price_high and last_cvd < prev_cvd:
            divergence = {"type": "bearish", "detail": "price higher-high tapi CVD lower-high (jual diam-diam)"}
        elif last_price_low < prev_price_low and last_cvd > prev_cvd:
            divergence = {"type": "bullish", "detail": "price lower-low tapi CVD higher-low (beli diam-diam)"}

    # Absorption detection: large delta + small range bar
    absorption = None
    if history:
        last_bar = history[-1]
        abs_delta = abs(last_bar["delta"])
        avg_vol = sum(h["buy_vol"] + h["sell_vol"] for h in history[-10:]) / max(1, len(history[-10:]))
        # Absorption: big aggressive flow but small price range
        if avg_vol > 0 and abs_delta > avg_vol * 0.5 and last_bar["range_pct"] < 0.4:
            side = "bid_absorbing" if last_bar["delta"] < 0 else "ask_absorbing"
            absorption = {
                "detected": True,
                "side": side,
                "delta": round(last_bar["delta"], 2),
                "range_pct": round(last_bar["range_pct"], 3),
                "detail": (
                    "large sell prints di-absorb buyers (bullish)" if side == "bid_absorbing"
                    else "large buy prints di-absorb sellers (bearish)"
                ),
            }

    return {
        "history": history[-30:],  # last 30 bars (was 20)
        "current_cvd": round(cvd, 2),
        "divergence": divergence,
        "absorption": absorption,
    }


def cumulative_delta_proxy(symbol: str) -> dict | None:
    """Estimate buy vs sell pressure from recent deals (last ~100 trades)."""
    if not ACCOUNTS:
        return None
    try:
        resp = ACCOUNTS[0].client.deals(symbol, limit=100)
    except Exception:
        return None
    data = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(data, list) or not data:
        return None
    buy_vol = 0.0
    sell_vol = 0.0
    for t in data:
        try:
            vol = float(t.get("v") or t.get("vol") or 0)
        except Exception:
            vol = 0.0
        side = t.get("T")
        if side == 1:
            buy_vol += vol
        elif side == 2:
            sell_vol += vol
        else:
            s = str(t.get("side") or "").upper()
            if s == "BUY":
                buy_vol += vol
            elif s == "SELL":
                sell_vol += vol
    total = buy_vol + sell_vol
    if total <= 0:
        return None
    buy_pct = buy_vol / total * 100
    delta = buy_vol - sell_vol
    bias = "buy" if buy_pct > 55 else "sell" if buy_pct < 45 else "neutral"
    return {
        "buy_vol": round(buy_vol, 2),
        "sell_vol": round(sell_vol, 2),
        "delta": round(delta, 2),
        "buy_pct": round(buy_pct, 2),
        "bias": bias,
    }


def orderbook_heatmap(symbol: str, depth: int = 50) -> dict | None:
    """Top bid/ask walls + spread context for heatmap visualization."""
    if not ACCOUNTS:
        return None
    try:
        resp = ACCOUNTS[0].client.depth(symbol, limit=depth)
    except Exception:
        return None
    snap = resp.get("data") if isinstance(resp, dict) else None
    if not isinstance(snap, dict):
        return None
    bids_raw = snap.get("bids") or []
    asks_raw = snap.get("asks") or []
    if not bids_raw or not asks_raw:
        return None

    def parse(side: list) -> list[dict]:
        out: list[dict] = []
        for row in side:
            if isinstance(row, list) and len(row) >= 2:
                try:
                    out.append({"price": float(row[0]), "volume": float(row[1])})
                except Exception:
                    continue
        return out

    bids = parse(bids_raw)
    asks = parse(asks_raw)
    if not bids or not asks:
        return None
    best_bid = bids[0]["price"]
    best_ask = asks[0]["price"]
    return {
        "best_bid": round(best_bid, 8),
        "best_ask": round(best_ask, 8),
        "spread_pct": round((best_ask - best_bid) / best_bid * 100, 4),
        "bid_walls": sorted(bids, key=lambda x: -x["volume"])[:5],
        "ask_walls": sorted(asks, key=lambda x: -x["volume"])[:5],
        "bid_total_vol": round(sum(b["volume"] for b in bids), 2),
        "ask_total_vol": round(sum(a["volume"] for a in asks), 2),
        "bids_top": bids[:20],
        "asks_top": asks[:20],
    }


# ── MEXC API enrichment caches ───────────────────────────────────────
_oi_hist_api_cache: dict[str, tuple[float, list[dict]]] = {}
_OI_HIST_API_TTL = 60

def get_oi_history_api_cached(symbol: str, count: int = 96) -> list[dict]:
    """OI history snapshots from MEXC API. 96 × 15m = 24h."""
    if not ACCOUNTS:
        return []
    now = time.time()
    cached = _oi_hist_api_cache.get(symbol)
    if cached and (now - cached[0]) < _OI_HIST_API_TTL:
        return cached[1]
    try:
        resp = ACCOUNTS[0].client.open_interest_history(symbol, interval="Min15", count=count)
        data = resp.get("data") if isinstance(resp, dict) else None
        if isinstance(data, list):
            result = data
        elif isinstance(data, dict):
            result = data.get("oiList") or data.get("list") or []
        else:
            result = []
    except Exception:
        result = []
    _oi_hist_api_cache[symbol] = (now, result)
    return result


_lsr_cache: dict[str, tuple[float, list[dict]]] = {}
_LSR_TTL = 60

def get_long_short_ratio_cached(symbol: str, count: int = 48) -> list[dict]:
    if not ACCOUNTS:
        return []
    now = time.time()
    cached = _lsr_cache.get(symbol)
    if cached and (now - cached[0]) < _LSR_TTL:
        return cached[1]
    try:
        resp = ACCOUNTS[0].client.long_short_ratio(symbol, interval="Min15", count=count)
        data = resp.get("data") if isinstance(resp, dict) else None
        result = data if isinstance(data, list) else []
    except Exception:
        result = []
    _lsr_cache[symbol] = (now, result)
    return result


_funding_hist_cache: dict[str, tuple[float, list[dict]]] = {}
_FUNDING_HIST_TTL = 300

# ═══════════════════════════════════════════════════════════════════
# Phase 5 Group B: MEXC SPOT API client (separate base URL) for
# spot/futures basis + BTC dominance proxy + ETH/BTC ratio
# ═══════════════════════════════════════════════════════════════════
_spot_ticker_cache: tuple[float, dict] | None = None
_SPOT_TICKER_TTL = 30


def get_spot_tickers() -> dict:
    """Fetch all MEXC spot tickers (api.mexc.com/api/v3/ticker/24hr).

    Used for BTC dominance + ETH/BTC + per-coin spot premium.
    Uses DoH (via _http_get_json) since api.mexc.com is also DNS-hijacked.
    """
    global _spot_ticker_cache
    now = time.time()
    if _spot_ticker_cache and (now - _spot_ticker_cache[0]) < _SPOT_TICKER_TTL:
        return _spot_ticker_cache[1]
    # Lazy reference — _http_get_json is defined further below; we'll get
    # bound via globals() lookup at call time.
    fetcher = globals().get("_http_get_json")
    if fetcher is None:
        return {}
    data = fetcher("https://api.mexc.com/api/v3/ticker/24hr", timeout=10)
    out: dict[str, dict] = {}
    if isinstance(data, list):
        for t in data:
            sym = t.get("symbol")
            if sym:
                out[sym] = t
    if out:
        _spot_ticker_cache = (now, out)
    return out


def get_spot_price(symbol_no_underscore: str) -> float | None:
    """Get spot price for symbol like 'BTCUSDT' (no underscore)."""
    tickers = get_spot_tickers()
    t = tickers.get(symbol_no_underscore)
    if not t:
        return None
    try:
        return float(t.get("lastPrice") or 0) or None
    except Exception:
        return None


def get_btc_dominance_proxy() -> dict | None:
    """Approximate BTC dominance from MEXC spot 24h quote volume share.

    Not true global dominance, but works as a relative regime indicator.
    Returns: {btc_dom_pct, eth_btc_ratio, top10_volume}
    """
    tickers = get_spot_tickers()
    if not tickers:
        return None
    btc = tickers.get("BTCUSDT")
    eth = tickers.get("ETHUSDT")
    if not btc:
        return None
    try:
        btc_qvol = float(btc.get("quoteVolume") or 0)
    except Exception:
        return None
    # Top USDT pairs by quote volume (approx)
    usdt_pairs = [t for sym, t in tickers.items() if sym.endswith("USDT")]
    try:
        usdt_pairs.sort(key=lambda t: -float(t.get("quoteVolume") or 0))
    except Exception:
        return None
    top_total = sum(float(t.get("quoteVolume") or 0) for t in usdt_pairs[:100])
    btc_dom = (btc_qvol / top_total * 100) if top_total > 0 else None

    eth_btc_ratio = None
    if eth and btc:
        try:
            eth_p = float(eth.get("lastPrice") or 0)
            btc_p = float(btc.get("lastPrice") or 0)
            if btc_p > 0:
                eth_btc_ratio = round(eth_p / btc_p, 6)
        except Exception:
            pass

    # BTC price trend (last 24h pct change)
    try:
        btc_change_24h = float(btc.get("priceChangePercent") or 0)
    except Exception:
        btc_change_24h = 0.0

    return {
        "btc_dominance_pct": round(btc_dom, 2) if btc_dom is not None else None,
        "eth_btc_ratio": eth_btc_ratio,
        "btc_change_24h_pct": round(btc_change_24h, 3),
        "top10_share_pct": round(
            sum(float(t.get("quoteVolume") or 0) for t in usdt_pairs[:10]) / top_total * 100, 2
        ) if top_total > 0 else None,
    }


def get_spot_futures_basis(symbol: str, futures_price: float | None) -> dict | None:
    """Compute spot vs futures premium/discount %.

    symbol: e.g. 'BTC_USDT' → maps to 'BTCUSDT' spot
    Positive basis = futures above spot = bullish leverage
    Negative basis = futures below spot = bearish leverage
    """
    if futures_price is None or futures_price <= 0:
        return None
    spot_sym = symbol.replace("_", "")
    spot_price = get_spot_price(spot_sym)
    if spot_price is None or spot_price <= 0:
        return None
    basis_pct = (futures_price - spot_price) / spot_price * 100
    return {
        "spot_price": round(spot_price, 8),
        "futures_price": round(futures_price, 8),
        "basis_pct": round(basis_pct, 4),
        "bias": (
            "contango_strong" if basis_pct > 0.5
            else "contango" if basis_pct > 0.1
            else "backwardation_strong" if basis_pct < -0.5
            else "backwardation" if basis_pct < -0.1
            else "neutral"
        ),
    }


# ═══════════════════════════════════════════════════════════════════
# Phase 5 Group E: Risk Management — portfolio heat, Kelly, circuit
# breaker, signal journal (file-backed)
# ═══════════════════════════════════════════════════════════════════
_signal_journal_path = Path("/tmp/mexc_signal_journal.jsonl")
_signal_journal_seen: set[str] = set()


def record_signal_event(symbol: str, signal_payload: dict) -> None:
    """Append signal trigger to journal file (one JSON per line).

    Dedupes within same minute per (symbol, direction, score_band).
    """
    direction = signal_payload.get("signal_direction") or signal_payload.get("direction")
    score = signal_payload.get("confluence_score") or 0
    if direction not in ("LONG", "SHORT") or score < 50:
        return
    minute = int(time.time() / 60)
    score_band = (score // 5) * 5  # 50, 55, 60, ...
    dedup_key = f"{symbol}|{direction}|{score_band}|{minute}"
    if dedup_key in _signal_journal_seen:
        return
    _signal_journal_seen.add(dedup_key)
    # Trim memory periodically
    if len(_signal_journal_seen) > 5000:
        # Reset (next minute will re-dedupe)
        _signal_journal_seen.clear()
        _signal_journal_seen.add(dedup_key)

    plan = signal_payload.get("entry_plan") or {}
    entry = {
        "ts": int(time.time() * 1000),
        "symbol": symbol,
        "direction": direction,
        "score": score,
        "verdict": signal_payload.get("verdict"),
        "entry_price": plan.get("entry_price"),
        "sl": (plan.get("sl_invalidation") or {}).get("price"),
        "tp1": (plan.get("tp_ladder") or [{}])[0].get("price") if plan.get("tp_ladder") else None,
        "rr_tp1": (plan.get("rr_ratio") or {}).get("tp1"),
        "mtf_score": (signal_payload.get("mtf_convergence") or {}).get("score"),
    }
    try:
        with _signal_journal_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def read_signal_journal(limit: int = 100) -> list[dict]:
    """Read last N journal entries."""
    if not _signal_journal_path.exists():
        return []
    try:
        with _signal_journal_path.open() as f:
            lines = f.readlines()
        out = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
    except Exception:
        return []


def compute_portfolio_heat(positions: list[dict], equity: float) -> dict:
    """Sum of risk per position as % of equity.

    Heat = sum(margin × leverage × max_adverse_move_to_liq) / equity
    Approximation: position margin / equity × 100 per position summed.
    """
    if equity <= 0 or not positions:
        return {
            "total_heat_pct": 0,
            "open_positions": 0,
            "max_single_heat_pct": 0,
            "warning_level": "ok",
        }
    heats = []
    for p in positions:
        try:
            margin = float(p.get("margin") or 0)
            buffer_pct = p.get("buffer_pct")  # % to liq for isolated
            # Heat per position = margin/equity × 100 if cross, or × buffer factor if isolated
            heat = (margin / equity) * 100
            if buffer_pct is not None and buffer_pct > 0:
                # Tighter buffer = higher effective heat
                heat = heat * max(1.0, 50.0 / buffer_pct)
            heats.append(heat)
        except Exception:
            continue
    total_heat = sum(heats)
    max_heat = max(heats) if heats else 0
    if total_heat > 25:
        warn = "critical"
    elif total_heat > 15:
        warn = "high"
    elif total_heat > 8:
        warn = "moderate"
    else:
        warn = "ok"
    return {
        "total_heat_pct": round(total_heat, 2),
        "open_positions": len(positions),
        "max_single_heat_pct": round(max_heat, 2),
        "warning_level": warn,
    }


def compute_kelly_sizing(win_rate: float, avg_r_win: float, avg_r_loss: float) -> dict:
    """Kelly Criterion: f* = (bp - q) / b
    b = avg win / avg loss (R ratio), p = win rate, q = 1-p
    Recommend half-Kelly (1/2 f*) for safety.
    """
    if avg_r_loss <= 0 or avg_r_win <= 0 or win_rate <= 0 or win_rate >= 1:
        return {"kelly_fraction": 0, "half_kelly_pct": 0, "full_kelly_pct": 0, "recommendation": "data insufficient"}
    b = avg_r_win / avg_r_loss
    p = win_rate
    q = 1 - p
    f = (b * p - q) / b
    f = max(0.0, min(0.25, f))  # cap at 25%
    half = f / 2
    return {
        "kelly_fraction": round(f, 4),
        "half_kelly_pct": round(half * 100, 2),
        "full_kelly_pct": round(f * 100, 2),
        "recommendation": "use half-Kelly for safety",
        "win_rate": round(win_rate * 100, 1),
        "avg_r_win": round(avg_r_win, 2),
        "avg_r_loss": round(avg_r_loss, 2),
    }


def compute_correlation(closes_a: list[float], closes_b: list[float]) -> float | None:
    """Pearson correlation of returns between two close series."""
    if len(closes_a) < 10 or len(closes_b) < 10:
        return None
    n = min(len(closes_a), len(closes_b))
    a = closes_a[-n:]
    b = closes_b[-n:]
    # Returns
    ret_a = [(a[i] - a[i - 1]) / a[i - 1] for i in range(1, n) if a[i - 1] > 0]
    ret_b = [(b[i] - b[i - 1]) / b[i - 1] for i in range(1, n) if b[i - 1] > 0]
    n2 = min(len(ret_a), len(ret_b))
    if n2 < 5:
        return None
    ra = ret_a[-n2:]
    rb = ret_b[-n2:]
    mean_a = sum(ra) / n2
    mean_b = sum(rb) / n2
    num = sum((ra[i] - mean_a) * (rb[i] - mean_b) for i in range(n2))
    den_a = sum((x - mean_a) ** 2 for x in ra)
    den_b = sum((x - mean_b) ** 2 for x in rb)
    if den_a <= 0 or den_b <= 0:
        return None
    den = (den_a * den_b) ** 0.5
    return num / den if den > 0 else None


def btc_correlation_check(symbol: str, direction: str, bars_1h_self: list[dict]) -> dict | None:
    """Check if BTC is moving in alignment with this signal's direction.

    Returns: {correlation_30bar, btc_direction, alignment, penalty_pct}
    penalty_pct = how much to downweight this signal if BTC opposite
    """
    if symbol == "BTC_USDT" or not bars_1h_self:
        return None
    try:
        btc_bars = fetch_klines_cached("BTC_USDT", "Min60", 30)
    except Exception:
        return None
    if not btc_bars or len(btc_bars) < 10:
        return None
    closes_self = [b["c"] for b in bars_1h_self[-30:]]
    closes_btc = [b["c"] for b in btc_bars[-30:]]
    corr = compute_correlation(closes_btc, closes_self)
    btc_first = closes_btc[0] if closes_btc else 0
    btc_last = closes_btc[-1] if closes_btc else 0
    if btc_first <= 0:
        return None
    btc_change_pct = (btc_last - btc_first) / btc_first * 100
    btc_dir = "up" if btc_change_pct > 0.5 else "down" if btc_change_pct < -0.5 else "flat"

    aligned = (
        (direction == "LONG" and btc_dir in ("up", "flat"))
        or (direction == "SHORT" and btc_dir in ("down", "flat"))
    )
    # Penalty calculation
    penalty = 0
    if corr is not None and abs(corr) > 0.6:
        # Strong correlation — if BTC opposite, big penalty
        if not aligned:
            penalty = 15
    elif corr is not None and abs(corr) > 0.3 and not aligned:
        penalty = 7

    return {
        "correlation_30bar": round(corr, 3) if corr is not None else None,
        "btc_change_30bar_pct": round(btc_change_pct, 3),
        "btc_direction": btc_dir,
        "alignment": "aligned" if aligned else "conflict",
        "penalty_pct": penalty,
    }


def detect_market_regime(bars_4h: list[dict], atr_pct: float | None) -> dict:
    """Classify market regime: trending vs ranging × high-vol vs low-vol.

    Uses linear regression slope of last 30 closes + ATR percentage.
    """
    if not bars_4h or len(bars_4h) < 20:
        return {"regime": "unknown", "trend_strength": 0, "volatility": "unknown"}
    closes = [b["c"] for b in bars_4h[-30:]]
    n = len(closes)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(closes) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, closes))
    den = sum((x - mean_x) ** 2 for x in xs)
    slope = num / den if den > 0 else 0
    # Normalize slope as % per bar
    slope_pct = (slope / mean_y) * 100 if mean_y > 0 else 0
    abs_slope = abs(slope_pct)
    trend_strength = min(100, abs_slope * 50)  # heuristic scaling

    if abs_slope > 0.5:
        regime_trend = "trending_up" if slope > 0 else "trending_down"
    elif abs_slope > 0.2:
        regime_trend = "mild_up" if slope > 0 else "mild_down"
    else:
        regime_trend = "ranging"

    if atr_pct is None:
        vol_class = "unknown"
    elif atr_pct > 4.0:
        vol_class = "extreme"
    elif atr_pct > 2.5:
        vol_class = "high"
    elif atr_pct > 1.2:
        vol_class = "normal"
    else:
        vol_class = "compressed"

    return {
        "regime": regime_trend,
        "trend_strength": round(trend_strength, 1),
        "slope_pct_per_bar": round(slope_pct, 4),
        "volatility": vol_class,
        "atr_pct": atr_pct,
    }


def estimate_liquidation_zones(
    current_price: float,
    oi_value_usdt: float | None,
    funding_rate: float | None,
) -> dict | None:
    """Estimate where leveraged longs/shorts get liquidated.

    Approximation:
      - At 100x leverage, liquidation ~1% adverse
      - At 50x, ~2%
      - At 25x, ~4%
      - At 10x, ~10%
    Heavy funding indicates dominant side. Combine with OI to size clusters.
    """
    if current_price <= 0:
        return None
    LEV_TIERS = [
        {"lev": 100, "pct": 0.01, "weight": 0.10},
        {"lev": 50, "pct": 0.02, "weight": 0.20},
        {"lev": 25, "pct": 0.04, "weight": 0.30},
        {"lev": 10, "pct": 0.10, "weight": 0.40},
    ]
    # Funding bias: positive funding = longs dominate (cluster below); negative = shorts above
    long_share = 0.5
    if funding_rate is not None:
        if funding_rate > 0.0005:
            long_share = 0.65 + min(0.25, funding_rate * 100)
        elif funding_rate < -0.0005:
            long_share = 0.35 - min(0.25, abs(funding_rate) * 100)
    long_share = max(0.2, min(0.8, long_share))

    oi_total = oi_value_usdt or 0
    long_clusters = []
    short_clusters = []
    for tier in LEV_TIERS:
        long_price = current_price * (1 - tier["pct"])
        short_price = current_price * (1 + tier["pct"])
        long_clusters.append({
            "price": round(long_price, 8),
            "lev": tier["lev"],
            "est_value_usdt": round(oi_total * long_share * tier["weight"], 2) if oi_total else None,
            "pct_from_current": -round(tier["pct"] * 100, 2),
        })
        short_clusters.append({
            "price": round(short_price, 8),
            "lev": tier["lev"],
            "est_value_usdt": round(oi_total * (1 - long_share) * tier["weight"], 2) if oi_total else None,
            "pct_from_current": round(tier["pct"] * 100, 2),
        })

    return {
        "long_clusters": long_clusters,
        "short_clusters": short_clusters,
        "long_share_estimate": round(long_share * 100, 1),
        "dominant_side": "longs" if long_share > 0.55 else "shorts" if long_share < 0.45 else "balanced",
    }


def get_funding_history_cached(symbol: str, page_size: int = 50) -> list[dict]:
    if not ACCOUNTS:
        return []
    now = time.time()
    cached = _funding_hist_cache.get(symbol)
    if cached and (now - cached[0]) < _FUNDING_HIST_TTL:
        return cached[1]
    try:
        resp = ACCOUNTS[0].client.funding_rate_history(symbol, page_num=1, page_size=page_size)
        data = resp.get("data") if isinstance(resp, dict) else None
        if isinstance(data, dict):
            result = data.get("resultList") or []
        elif isinstance(data, list):
            result = data
        else:
            result = []
    except Exception:
        result = []
    _funding_hist_cache[symbol] = (now, result)
    return result


_oi_history: dict[str, list[tuple[float, float]]] = {}  # symbol -> [(ts, holdVol)]
_OI_HISTORY_MAX = 60  # keep last 60 samples


# ─── Quality coin filter ───
# Radar bisa entry 10-30 koin — diversification is fine. Filter quality strict.
TIER_1_SYMBOLS = {
    # Top market cap
    "BTC_USDT", "ETH_USDT", "SOL_USDT", "BNB_USDT", "XRP_USDT",
    "ADA_USDT", "DOGE_USDT", "AVAX_USDT", "LINK_USDT", "MATIC_USDT",
    "LTC_USDT", "ATOM_USDT", "NEAR_USDT", "FIL_USDT", "TRX_USDT",
    "DOT_USDT", "UNI_USDT", "AAVE_USDT", "ETC_USDT", "BCH_USDT",
    "TON_USDT", "HBAR_USDT", "ICP_USDT", "KAS_USDT", "RUNE_USDT",
    "TAO_USDT", "INJ_USDT", "TIA_USDT", "SUI_USDT", "SEI_USDT",
    "APT_USDT", "ARB_USDT", "OP_USDT", "STX_USDT", "MNT_USDT",
    # Mid-cap quality
    "FET_USDT", "RNDR_USDT", "ONDO_USDT", "PYTH_USDT", "JUP_USDT",
    "ETHFI_USDT", "ENA_USDT", "WLD_USDT", "STRK_USDT", "DYM_USDT",
    "MANTA_USDT", "ALT_USDT", "BLUR_USDT", "JTO_USDT", "ORDI_USDT",
    "SATS_USDT", "1000RATS_USDT", "1000SATS_USDT", "GMT_USDT",
    "GMX_USDT", "DYDX_USDT", "GALA_USDT", "FLOW_USDT", "EOS_USDT",
    "XLM_USDT", "ALGO_USDT", "EGLD_USDT", "XTZ_USDT", "VET_USDT",
    "THETA_USDT", "CHZ_USDT", "AXS_USDT", "SAND_USDT", "MANA_USDT",
    "GRT_USDT", "LDO_USDT", "MKR_USDT", "SNX_USDT", "COMP_USDT",
    "CRV_USDT", "SUSHI_USDT", "1INCH_USDT", "BAL_USDT",
    # High-volume memes (filtered by quality min volume)
    "PEPE_USDT", "FLOKI_USDT", "SHIB_USDT", "BONK_USDT", "WIF_USDT",
    "1000PEPE_USDT", "1000FLOKI_USDT", "1000SHIB_USDT",
    # Newer narratives that pass liquidity
    "POPCAT_USDT", "MEW_USDT", "NEIROETH_USDT", "MOODENG_USDT",
    "AI16Z_USDT", "VIRTUAL_USDT", "AIXBT_USDT", "GOAT_USDT",
}

# Min 24h notional volume (USDT) untuk dianggap "quality"
QUALITY_MIN_VOLUME_24H_USDT = 30_000_000  # $30M — wider net but still filters scams

_tickers_cache: tuple[float, dict] | None = None
_TICKERS_TTL_SECONDS = 30


def get_all_tickers() -> dict:
    """Fetch all symbol tickers in one call (for quality filter scan)."""
    global _tickers_cache
    now = time.time()
    if _tickers_cache and (now - _tickers_cache[0]) < _TICKERS_TTL_SECONDS:
        return _tickers_cache[1]
    any_client = ACCOUNTS[0].client
    try:
        resp = any_client.ticker()  # all tickers
    except Exception:
        return {}
    data = resp.get("data") if isinstance(resp, dict) else None
    out: dict[str, dict] = {}
    if isinstance(data, list):
        for t in data:
            sym = t.get("symbol")
            if sym:
                out[sym] = t
    _tickers_cache = (now, out)
    return out


def _compute_rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's RSI."""
    if len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses += -diff
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gain = max(diff, 0)
        loss = max(-diff, 0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _track_oi(symbol: str, hold_vol: float):
    """Track open interest history per symbol."""
    history = _oi_history.setdefault(symbol, [])
    history.append((time.time(), hold_vol))
    if len(history) > _OI_HISTORY_MAX:
        history.pop(0)


def _oi_delta_pct(symbol: str) -> float | None:
    """% change in OI over last ~5 minutes."""
    history = _oi_history.get(symbol, [])
    if len(history) < 2:
        return None
    now = time.time()
    # Find sample ~5min ago
    target_ts = now - 300
    older = None
    for ts, vol in history:
        if ts >= target_ts:
            older = (ts, vol)
            break
    if not older:
        older = history[0]
    latest = history[-1]
    if older[1] == 0:
        return None
    return ((latest[1] - older[1]) / older[1]) * 100


def compute_analytics(symbol: str, lite: bool = False) -> dict:
    """Counter-trend dip-buy analytics.

    Strategy bias: REWARD oversold + capitulation + discount; PENALIZE chasing momentum.
    Multi-timeframe RSI (15m/1h/4h/1d) + Bollinger lower touch + distance from recent high.
    Score 0-100. Threshold semantics:
      75+ = ACCUMULATE (dip-buy zone)
      85+ = SCREAMING BUY (extreme oversold)

    `lite=True` skips heavy MEXC API calls (orderbook depth, recent deals, OI/funding
    history). Use this during bulk signal scanning; full data is fetched when the
    user opens an individual symbol's analytics.
    """
    cache_dict = _lite_analytics_cache if lite else _analytics_cache
    cached = cache_dict.get(symbol)
    now = time.time()
    if cached and (now - cached[0]) < _ANALYTICS_TTL_SECONDS:
        return cached[1]
    # Full analytics cache is also acceptable for lite (it has more data)
    if lite:
        full_cached = _analytics_cache.get(symbol)
        if full_cached and (now - full_cached[0]) < _ANALYTICS_TTL_SECONDS:
            return full_cached[1]

    out: dict = {
        # ── NEW Phase 1+2+5: rich pattern data, MTF convergence, S/D zones,
        #     volume profile, liquidation cluster, macro context, orderbook heatmap
        "candle_patterns_rich": {},
        "primary_pattern_trigger": None,
        "wyckoff_spring_upthrust": None,
        "sd_zones_4h": None,
        "volume_profile_4h": None,
        "liquidation_cluster": None,
        "mtf_convergence": None,
        "oi_history_api": [],
        "long_short_ratio": None,
        "long_short_ratio_history": [],
        "funding_history": [],
        "funding_rate_7d_avg": None,
        "cumulative_delta": None,
        "orderbook_heatmap": None,
        # ── Phase 5 Group A: validity hardening
        "atr_4h": None,
        "atr_1h": None,
        "atr_pct_4h": None,
        "anchored_vwap_swing_low": None,
        "anchored_vwap_swing_high": None,
        "sl_invalidation": None,
        "rr_ratio": None,
        "tier_anchor_sources": None,
        # ── Phase 7: Multi-timeframe levels (HTF + LTF for entry accuracy)
        "sd_zones_1d": None,
        "volume_profile_1d": None,
        "sd_zones_1h": None,
        "volume_profile_1h": None,
        # ── Phase 7: Pattern confirmation + volume gate + liquidity grab + funding window
        "liquidity_grab_4h": None,
        "liquidity_grab_1h": None,
        "liquidity_sweep_15m": None,
        "volume_confirmation_4h": None,
        "volume_confirmation_1h": None,
        "funding_window": None,
        # ── Phase 8: macro/flow scoring impact
        "macro_score_adjustments": None,
        "funding_arb_signal": None,
        # ── Phase 5 Group B: macro/regime layer
        "spot_futures_basis": None,
        "market_regime": None,
        "liquidation_zones": None,
        "btc_correlation_alignment": None,
        # ── Phase 5 Group C: order flow deep
        "cvd_historical": None,
        # Multi-timeframe RSI
        "rsi_15m": None,
        "rsi_1h": None,
        "rsi_4h": None,
        "rsi_1d": None,
        "mtf_oversold_count": 0,  # how many TFs are oversold (<30)
        "mtf_overbought_count": 0,
        # Bollinger Bands (4h)
        "bb_lower_4h": None,
        "bb_middle_4h": None,
        "bb_upper_4h": None,
        "bb_position_4h": None,  # 0..1: where price sits relative to bands
        "bb_lower_touch": False,
        # Distance from highs
        "high_7d": None,
        "high_30d": None,
        "low_30d": None,
        "dist_from_7d_high_pct": None,
        "dist_from_30d_high_pct": None,
        # Capitulation: volume spike at low
        "volume_capitulation": False,
        "volume_24h_usdt": None,
        # OI & funding
        "oi_delta_5m_pct": None,
        "funding_rate_pct": None,
        "funding_trend_1h": None,
        # Orderbook
        "ob_imbalance_pct": None,
        "ob_bias": None,
        # EMA trend
        "ema_20_4h": None,
        "ema_50_4h": None,
        "trend_4h": None,  # "uptrend" | "downtrend" | "sideways"
        "price_vs_ema50_pct": None,
        # VWAP (NEW)
        "vwap_4h": None,
        "vwap_dist_pct": None,
        # Divergence + reversal
        "rsi_bullish_divergence_4h": False,
        "rsi_bearish_divergence_4h": False,
        "three_bar_reversal_1h": False,
        # MTF sequence score (NEW): bullish recovery cascade
        "mtf_sequence_bonus": 0,
        # Position sizing recommendation (NEW)
        "sizing_pct_equity": 0.0,
        # Hard gates (NEW) — must all be true for valid signal
        "gate_volume": False,  # passed volume filter
        "gate_not_overbought": False,  # not in MTF overbought
        "gate_discounted": False,  # not at peak
        "all_gates_pass": False,
        # Composite
        "confluence_score": 0,
        "confluence_breakdown": [],
        "verdict": "AVOID",
        "bias": "neutral",
        # NEW: signal direction & dual scoring
        "signal_direction": "NONE",  # "LONG" | "SHORT" | "NONE"
        "score_long": 0,
        "score_short": 0,
        "candle_patterns": {},  # per-TF dict
        "candle_pattern_summary": [],  # list of detected patterns with TF
        "entry_plan": None,  # {entry_price, zone, reasoning}
        # Lookback fix: low side too
        "low_7d": None,
        "dist_from_7d_low_pct": None,
        # Smart Money Concepts (NEW)
        "liquidity_sweep_4h": None,  # {bullish_sweep, bearish_sweep, strength}
        "liquidity_sweep_1h": None,
        "order_block_4h": None,  # {bullish_ob_zone, bearish_ob_zone}
        "fair_value_gap_4h": None,  # {bullish_fvg, bearish_fvg}
        "market_structure_4h": None,  # {bos_bullish, bos_bearish, structure, last_swing_high/low}
        # Wyckoff + Whale (NEW)
        "wyckoff_phase": None,  # {phase, confidence, ...}
        "whale_accumulation": None,  # {detected, intensity, oi_change_pct, ...}
    }

    # ─── Multi-timeframe RSI ───
    tf_closes = {}
    for interval, n in [("Min15", 60), ("Min60", 60), ("Hour4", 60), ("Day1", 40)]:
        bars = fetch_klines_cached(symbol, interval, n)
        closes = [b["c"] for b in bars]
        tf_closes[interval] = (closes, bars)

    rsi_15 = _compute_rsi(tf_closes["Min15"][0], 14) if len(tf_closes["Min15"][0]) >= 15 else None
    rsi_1h = _compute_rsi(tf_closes["Min60"][0], 14) if len(tf_closes["Min60"][0]) >= 15 else None
    rsi_4h = _compute_rsi(tf_closes["Hour4"][0], 14) if len(tf_closes["Hour4"][0]) >= 15 else None
    rsi_1d = _compute_rsi(tf_closes["Day1"][0], 14) if len(tf_closes["Day1"][0]) >= 15 else None

    out["rsi_15m"] = round(rsi_15, 2) if rsi_15 is not None else None
    out["rsi_1h"] = round(rsi_1h, 2) if rsi_1h is not None else None
    out["rsi_4h"] = round(rsi_4h, 2) if rsi_4h is not None else None
    out["rsi_1d"] = round(rsi_1d, 2) if rsi_1d is not None else None

    rsi_vals = [v for v in [rsi_15, rsi_1h, rsi_4h, rsi_1d] if v is not None]
    out["mtf_oversold_count"] = sum(1 for v in rsi_vals if v < 30)
    out["mtf_overbought_count"] = sum(1 for v in rsi_vals if v > 70)

    # ─── Bollinger Bands 4h ───
    closes_4h = tf_closes["Hour4"][0]
    bb = _bollinger_lower(closes_4h, 20, 2.0)
    if bb and closes_4h:
        lower, middle, upper = bb
        last_price = closes_4h[-1]
        out["bb_lower_4h"] = round(lower, 8)
        out["bb_middle_4h"] = round(middle, 8)
        out["bb_upper_4h"] = round(upper, 8)
        if upper > lower:
            out["bb_position_4h"] = round((last_price - lower) / (upper - lower), 4)
            # Touch = price within 5% of band width above lower band
            band_width = upper - lower
            if last_price <= lower + band_width * 0.05:
                out["bb_lower_touch"] = True

    # ─── Distance from recent highs (FIXED: proper lookback) ───
    # 7d high = 42 bars of 4h (= 168 hours = 7 days)
    bars_4h_for_7d = fetch_klines_cached(symbol, "Hour4", 42)
    if bars_4h_for_7d:
        recent_high_7d = max(b["h"] for b in bars_4h_for_7d)
        out["high_7d"] = round(recent_high_7d, 8)
        current = bars_4h_for_7d[-1]["c"]
        out["dist_from_7d_high_pct"] = round(((current - recent_high_7d) / recent_high_7d) * 100, 3)

    # 30d high + low = 30 bars of Day1 (HTF anchor)
    bars_1d_for_30d = fetch_klines_cached(symbol, "Day1", 30)
    if bars_1d_for_30d:
        recent_high_30d = max(b["h"] for b in bars_1d_for_30d)
        recent_low_30d = min(b["l"] for b in bars_1d_for_30d)
        out["high_30d"] = round(recent_high_30d, 8)
        out["low_30d"] = round(recent_low_30d, 8)
        current = bars_1d_for_30d[-1]["c"]
        out["dist_from_30d_high_pct"] = round(((current - recent_high_30d) / recent_high_30d) * 100, 3)

    # 7d low = lowest L of last 42 × 4h bars (for SHORT detection)
    if bars_4h_for_7d:
        recent_low_7d = min(b["l"] for b in bars_4h_for_7d)
        out["low_7d"] = round(recent_low_7d, 8)
        current = bars_4h_for_7d[-1]["c"]
        out["dist_from_7d_low_pct"] = round(((current - recent_low_7d) / recent_low_7d) * 100, 3)

    # ─── Candle patterns multi-TF ───
    patterns_15m = detect_candle_patterns(tf_closes["Min15"][1]) if tf_closes["Min15"][1] else {}
    patterns_1h = detect_candle_patterns(tf_closes["Min60"][1]) if tf_closes["Min60"][1] else {}
    patterns_4h = detect_candle_patterns(tf_closes["Hour4"][1]) if tf_closes["Hour4"][1] else {}
    patterns_1d = detect_candle_patterns(tf_closes["Day1"][1]) if tf_closes["Day1"][1] else {}
    out["candle_patterns"] = {
        "15m": patterns_15m,
        "1h": patterns_1h,
        "4h": patterns_4h,
        "1d": patterns_1d,
    }
    # Summary: list of (tf, pattern_name) active
    summary = []
    for tf, ps in [("15m", patterns_15m), ("1h", patterns_1h), ("4h", patterns_4h), ("1d", patterns_1d)]:
        for name, active in ps.items():
            if active:
                summary.append({"tf": tf, "pattern": name})
    out["candle_pattern_summary"] = summary

    # ─── Smart Money Concepts (4h primary, 1h confirmation) ───
    bars_4h_smc = tf_closes["Hour4"][1]
    bars_1h_smc = tf_closes["Min60"][1]
    if bars_4h_smc:
        out["liquidity_sweep_4h"] = detect_liquidity_sweep(bars_4h_smc, lookback=20)
        out["order_block_4h"] = detect_order_block(bars_4h_smc)
        out["fair_value_gap_4h"] = detect_fair_value_gap(bars_4h_smc)
        out["market_structure_4h"] = detect_market_structure(bars_4h_smc, lookback=30)
    if bars_1h_smc:
        out["liquidity_sweep_1h"] = detect_liquidity_sweep(bars_1h_smc, lookback=24)

    # ─── Wyckoff phase + Whale accumulation ───
    oi_history = _oi_history.get(symbol, [])
    if bars_4h_smc:
        out["wyckoff_phase"] = classify_wyckoff_phase(bars_4h_smc, oi_history)
    if bars_1h_smc:
        out["whale_accumulation"] = detect_whale_accumulation(bars_1h_smc, oi_history)

    # ═══════════════════════════════════════════════════════════════════
    # Phase 5 Group A: Cheap analytics MOVED HERE (before scoring)
    # so entry_plan can anchor tier prices to technical levels
    # ═══════════════════════════════════════════════════════════════════
    rich_patterns_early = {
        "15m": detect_candle_patterns_rich(tf_closes["Min15"][1]) if tf_closes["Min15"][1] else [],
        "1h": detect_candle_patterns_rich(tf_closes["Min60"][1]) if tf_closes["Min60"][1] else [],
        "4h": detect_candle_patterns_rich(tf_closes["Hour4"][1]) if tf_closes["Hour4"][1] else [],
        "1d": detect_candle_patterns_rich(tf_closes["Day1"][1]) if tf_closes["Day1"][1] else [],
    }
    out["candle_patterns_rich"] = rich_patterns_early

    spring_upthrust_data = None
    if bars_4h_smc:
        spring_upthrust_data = detect_wyckoff_spring_upthrust(bars_4h_smc, lookback=30)
        out["wyckoff_spring_upthrust"] = spring_upthrust_data

    sd_zones_data = None
    if bars_4h_smc:
        sd_zones_data = detect_supply_demand_zones(bars_4h_smc, lookback=60)
        out["sd_zones_4h"] = sd_zones_data

    vol_profile_data = None
    if bars_4h_smc:
        vol_profile_data = compute_volume_profile(bars_4h_smc, bins=24)
        out["volume_profile_4h"] = vol_profile_data

    # ─── Multi-TF: Daily + 1h analytics for HTF anchors + LTF precision ───
    bars_1d_smc = tf_closes["Day1"][1]
    bars_1h_full = tf_closes["Min60"][1]
    sd_zones_1d = None
    vol_profile_1d = None
    if bars_1d_smc and len(bars_1d_smc) >= 20:
        # Daily zones: 30 bars = 1 month context
        sd_zones_1d = detect_supply_demand_zones(bars_1d_smc, lookback=min(30, len(bars_1d_smc)))
        out["sd_zones_1d"] = sd_zones_1d
        vol_profile_1d = compute_volume_profile(bars_1d_smc, bins=20)
        out["volume_profile_1d"] = vol_profile_1d

    sd_zones_1h = None
    vol_profile_1h = None
    if bars_1h_full and len(bars_1h_full) >= 30:
        # 1h zones for tighter near-price entries
        sd_zones_1h = detect_supply_demand_zones(bars_1h_full, lookback=min(48, len(bars_1h_full)))
        out["sd_zones_1h"] = sd_zones_1h
        vol_profile_1h = compute_volume_profile(bars_1h_full, bins=20)
        out["volume_profile_1h"] = vol_profile_1h

    # ─── Phase 7: liquidity grab on 4h + 1h ───
    if bars_4h_smc and len(bars_4h_smc) >= 25:
        out["liquidity_grab_4h"] = detect_liquidity_grab(bars_4h_smc, lookback=20)
    if bars_1h_full and len(bars_1h_full) >= 25:
        out["liquidity_grab_1h"] = detect_liquidity_grab(bars_1h_full, lookback=20)

    # 15m sweep (multi-TF expansion)
    bars_15m = tf_closes["Min15"][1]
    if bars_15m and len(bars_15m) >= 25:
        out["liquidity_sweep_15m"] = detect_liquidity_sweep(bars_15m, lookback=20)

    # ─── Phase 7: volume confirmation ───
    if bars_4h_smc and len(bars_4h_smc) >= 25:
        out["volume_confirmation_4h"] = compute_volume_confirmation(bars_4h_smc, recent_n=3, baseline_n=20)
    if bars_1h_full and len(bars_1h_full) >= 25:
        out["volume_confirmation_1h"] = compute_volume_confirmation(bars_1h_full, recent_n=3, baseline_n=20)

    # ATR per TF (volatility — used for SL/TP placement)
    atr_4h = _atr(bars_4h_smc, 14) if bars_4h_smc else None
    atr_1h = _atr(bars_1h_smc, 14) if bars_1h_smc else None
    if bars_4h_smc and atr_4h:
        last_close = bars_4h_smc[-1]["c"]
        out["atr_4h"] = round(atr_4h, 8)
        out["atr_pct_4h"] = round(atr_4h / last_close * 100, 3) if last_close else None
    if atr_1h:
        out["atr_1h"] = round(atr_1h, 8)

    # Anchored VWAP from major swing low/high (institutional level)
    if bars_4h_smc and len(bars_4h_smc) >= 20:
        lows = [b["l"] for b in bars_4h_smc]
        highs = [b["h"] for b in bars_4h_smc]
        # Find lowest low + highest high indices in the full window
        anchor_low_idx = lows.index(min(lows))
        anchor_high_idx = highs.index(max(highs))
        vwap_from_low = _anchor_vwap(bars_4h_smc, anchor_low_idx)
        vwap_from_high = _anchor_vwap(bars_4h_smc, anchor_high_idx)
        if vwap_from_low is not None:
            out["anchored_vwap_swing_low"] = round(vwap_from_low, 8)
        if vwap_from_high is not None:
            out["anchored_vwap_swing_high"] = round(vwap_from_high, 8)

    # Keep refs for downstream
    bars_1h = tf_closes["Min60"][1]
    bars_4h = tf_closes["Hour4"][1]

    # ─── Capitulation: volume spike + price drop ───
    if len(bars_1h) >= 24:
        recent_vols = [b["v"] for b in bars_1h[-24:]]
        avg_vol = sum(recent_vols[:-1]) / max(1, len(recent_vols) - 1)
        last_vol = recent_vols[-1]
        last_bar = bars_1h[-1]
        was_red = last_bar["c"] < last_bar["o"]
        # Capitulation = vol > 2x average + red candle + below entry
        if avg_vol > 0 and last_vol > avg_vol * 2 and was_red:
            out["volume_capitulation"] = True

    # ─── Ticker-based stats (OI, volume) ───
    tickers = get_all_tickers()
    if symbol in tickers:
        tk = tickers[symbol]
        hold_vol = float(tk.get("holdVol") or 0)
        if hold_vol > 0:
            _track_oi(symbol, hold_vol)
            out["oi_delta_5m_pct"] = round(_oi_delta_pct(symbol) or 0, 3)
        vol_24h_usdt = float(tk.get("amount24") or 0)
        out["volume_24h_usdt"] = vol_24h_usdt

    # ─── Funding rate + 1h trend ───
    funding = get_funding_cached(symbol)
    if funding:
        out["funding_rate_pct"] = round(funding["rate"] * 100, 4)
        _track_funding(symbol, funding["rate"])
        out["funding_trend_1h"] = _funding_trend(symbol)

    # ─── Orderbook imbalance ───
    ob = _orderbook_imbalance(symbol)
    if ob:
        out["ob_imbalance_pct"] = ob["imbalance_pct"]
        out["ob_bias"] = ob["bias"]

    # ─── EMA trend filter (4h) — stricter threshold 1.5% gap ───
    closes_4h_full = tf_closes["Hour4"][0]
    if len(closes_4h_full) >= 50:
        ema20 = _ema(closes_4h_full, 20)
        ema50 = _ema(closes_4h_full, 50)
        if ema20 is not None and ema50 is not None:
            out["ema_20_4h"] = round(ema20, 8)
            out["ema_50_4h"] = round(ema50, 8)
            current = closes_4h_full[-1]
            out["price_vs_ema50_pct"] = round((current - ema50) / ema50 * 100, 3)
            ema_gap_pct = (ema20 - ema50) / ema50 * 100
            # Stricter thresholds: 1.5% gap + price confirmation
            if ema_gap_pct > 1.5 and current > ema20 * 0.995:
                out["trend_4h"] = "uptrend"
            elif ema_gap_pct < -1.5 and current < ema20 * 1.005:
                out["trend_4h"] = "downtrend"
            else:
                out["trend_4h"] = "sideways"

    # ─── VWAP (4h × 24 bars ~ 4 days) ───
    if len(bars_4h) >= 24:
        vwap_val = _vwap_4h(bars_4h, 24)
        if vwap_val is not None:
            out["vwap_4h"] = round(vwap_val, 8)
            current = bars_4h[-1]["c"]
            out["vwap_dist_pct"] = round((current - vwap_val) / vwap_val * 100, 3)

    # ─── RSI bullish divergence (4h) ───
    if len(closes_4h_full) >= 20:
        rsi_series = _rsi_series(closes_4h_full, 14)
        out["rsi_bullish_divergence_4h"] = _detect_bullish_divergence(
            closes_4h_full, rsi_series, lookback=20
        )
        out["rsi_bearish_divergence_4h"] = _detect_bearish_divergence(
            closes_4h_full, rsi_series, lookback=20
        )

    # ─── 3-bar reversal (1h) ───
    bars_1h_full = tf_closes["Min60"][1]
    if len(bars_1h_full) >= 4:
        out["three_bar_reversal_1h"] = _three_bar_reversal(bars_1h_full)

    # ═══════════════════════════════════════════════════════════════════
    # COUNTER-TREND DIP-BUY SCORING v2 — strict gates + no baseline
    # ═══════════════════════════════════════════════════════════════════
    score = 0
    breakdown: list[dict] = []
    oversold_n = out["mtf_oversold_count"]
    overbought_n = out["mtf_overbought_count"]
    dist_7d = out["dist_from_7d_high_pct"]
    bb_pos = out["bb_position_4h"]
    fr = out["funding_rate_pct"]
    rsi_4h_v = out["rsi_4h"] or 50
    rsi_1d_v = out["rsi_1d"] or 50

    # ─── HARD GATES (must all pass to even consider dip-buy) ───
    gate_volume = (
        out["volume_24h_usdt"] is not None
        and out["volume_24h_usdt"] >= QUALITY_MIN_VOLUME_24H_USDT
    )
    gate_not_overbought = rsi_4h_v <= 65 and rsi_1d_v <= 65 and overbought_n < 2
    gate_discounted = dist_7d is not None and dist_7d <= -3
    all_gates = gate_volume and gate_not_overbought and gate_discounted

    out["gate_volume"] = gate_volume
    out["gate_not_overbought"] = gate_not_overbought
    out["gate_discounted"] = gate_discounted
    out["all_gates_pass"] = all_gates

    # If gates fail, log reason + skip positive scoring
    if not gate_volume:
        breakdown.append({"name": "✗ GATE: thin volume (skipped)", "points": 0,
                          "value": f"${(out['volume_24h_usdt'] or 0)/1e6:.0f}M < $30M"})
    if not gate_not_overbought:
        breakdown.append({"name": "✗ GATE: RSI overbought (skipped)", "points": 0,
                          "value": f"4h={rsi_4h_v:.0f} 1d={rsi_1d_v:.0f}"})
    if not gate_discounted:
        breakdown.append({"name": "✗ GATE: too near peak (skipped)", "points": 0,
                          "value": f"{dist_7d or 0:.1f}% from 7d high"})

    if not all_gates:
        # Apply hard penalty if user wants dip-buy and gates fail
        if overbought_n >= 1:
            score -= 20
            breakdown.append({"name": "RSI overbought penalty (don't chase)", "points": -20,
                              "value": f"{overbought_n}/4 TFs"})
        if dist_7d is not None and dist_7d > -1:
            score -= 30
            breakdown.append({"name": "Near peak — CHASE TRAP", "points": -30,
                              "value": f"{dist_7d:.1f}% from 7d high"})
        if bb_pos is not None and bb_pos > 0.85:
            score -= 15
            breakdown.append({"name": "BB upper half (overheating)", "points": -15,
                              "value": f"pos {bb_pos:.2f}"})

        final_score = max(0, min(100, score + 30))
    else:
        # ─── ALL GATES PASS — count positive confluence ───

        # 1. MTF oversold (stricter — need 2+ for any reward)
        if oversold_n >= 3:
            score += 35
            breakdown.append({"name": f"✓ MTF deep oversold ({oversold_n}/4)",
                              "points": 35,
                              "value": f"15m={out['rsi_15m']} 1h={out['rsi_1h']} 4h={out['rsi_4h']} 1d={out['rsi_1d']}"})
        elif oversold_n == 2:
            score += 22
            breakdown.append({"name": "✓ MTF partial oversold (2/4)",
                              "points": 22,
                              "value": f"oversold TFs detected"})
        # 1 TF oversold = no reward (too easy to satisfy)

        # 2. BB lower touch (only counts in low/mid BB range)
        if out["bb_lower_touch"]:
            score += 22
            breakdown.append({"name": "✓ BB 4h lower touch",
                              "points": 22,
                              "value": f"@ {out['bb_lower_4h']}"})

        # 3. Distance from high (deep discount weights more)
        if dist_7d is not None:
            if dist_7d < -25:
                score += 25
                breakdown.append({"name": "✓ Deep discount 7d", "points": 25,
                                  "value": f"{dist_7d:.1f}%"})
            elif dist_7d < -15:
                score += 18
                breakdown.append({"name": "✓ Strong discount 7d", "points": 18,
                                  "value": f"{dist_7d:.1f}%"})
            elif dist_7d < -8:
                score += 10
                breakdown.append({"name": "Mild discount 7d", "points": 10,
                                  "value": f"{dist_7d:.1f}%"})

        # 4. Volume capitulation (stricter — need pre-discount too)
        if out["volume_capitulation"] and dist_7d is not None and dist_7d < -8:
            score += 18
            breakdown.append({"name": "✓ Capitulation (vol spike + already discounted)",
                              "points": 18, "value": "sellers exhausted"})
        elif out["volume_capitulation"]:
            breakdown.append({"name": "Capitulation (but not yet discounted)",
                              "points": 0, "value": "wait for further drop"})

        # 5. Funding rate (stricter thresholds)
        if fr is not None:
            if fr < -0.10:
                score += 20
                breakdown.append({"name": "✓ Funding extreme negative (shorts crowded)",
                                  "points": 20, "value": f"{fr:.4f}%"})
            elif fr < -0.05:
                score += 12
                breakdown.append({"name": "✓ Funding negative", "points": 12,
                                  "value": f"{fr:.4f}%"})

        # 6. OI declining (longs flushing)
        if out["oi_delta_5m_pct"] is not None:
            oi = out["oi_delta_5m_pct"]
            if oi < -3:
                score += 14
                breakdown.append({"name": "✓ OI dump (longs flushed)",
                                  "points": 14, "value": f"{oi:.2f}%"})
            elif oi < -1.5:
                score += 7
                breakdown.append({"name": "OI drift down", "points": 7,
                                  "value": f"{oi:.2f}%"})

        # 7. OB imbalance — context-aware (only matters if also oversold)
        if out["ob_imbalance_pct"] is not None and rsi_4h_v < 50:
            ob = out["ob_imbalance_pct"]
            if ob > 25:
                score += 10
                breakdown.append({"name": "✓ Bid wall (real demand at low)",
                                  "points": 10, "value": f"+{ob:.1f}%"})
            elif ob < -25:
                score -= 8
                breakdown.append({"name": "Heavy ask (more selling coming)",
                                  "points": -8, "value": f"{ob:.1f}%"})

        # 8. RSI bullish divergence (powerful signal — real bottom indicator)
        if out["rsi_bullish_divergence_4h"]:
            score += 20
            breakdown.append({"name": "✓ RSI 4h bullish divergence",
                              "points": 20, "value": "price LL + RSI HL"})

        # 9. 3-bar reversal — only reward when context is supportive
        if out["three_bar_reversal_1h"]:
            # Need oversold context OR near support (low BB position) to validate
            is_supportive = (
                oversold_n >= 1
                or (out["bb_position_4h"] is not None and out["bb_position_4h"] < 0.4)
                or (dist_7d is not None and dist_7d < -10)
            )
            if is_supportive:
                score += 12
                breakdown.append({"name": "✓ 3-bar reversal (with context)",
                                  "points": 12, "value": "green > prior reds + oversold/support"})
            else:
                breakdown.append({"name": "3-bar reversal (no context — noise)",
                                  "points": 0, "value": "ignore in mid-range"})

        # 10. MTF RSI sequencing (telescoping bullish shift)
        seq_bonus = _mtf_rsi_sequence_score(
            out["rsi_15m"], out["rsi_1h"], out["rsi_4h"], out["rsi_1d"], direction="LONG"
        )
        if seq_bonus > 0:
            out["mtf_sequence_bonus"] = seq_bonus
            score += seq_bonus
            breakdown.append({"name": "✓ MTF telescoping recovery",
                              "points": seq_bonus,
                              "value": "15m > 1h > 4h (turning up first)"})

        # 11. VWAP discount (price below VWAP = institutional cheap zone)
        if out.get("vwap_dist_pct") is not None:
            vd = out["vwap_dist_pct"]
            if vd < -5:
                score += 12
                breakdown.append({"name": "✓ Below VWAP -5% (institutional cheap)",
                                  "points": 12, "value": f"{vd:.2f}%"})
            elif vd < -2:
                score += 6
                breakdown.append({"name": "✓ Below VWAP", "points": 6,
                                  "value": f"{vd:.2f}%"})
            elif vd > 5:
                score -= 8
                breakdown.append({"name": "Above VWAP +5% (premium zone)",
                                  "points": -8, "value": f"{vd:.2f}%"})

        # 12. Bullish candle patterns multi-TF (expanded set, max +20)
        bullish_pattern_score = 0
        bullish_patterns_hit: list[str] = []
        bullish_pattern_names = {
            "bullish_engulfing", "hammer", "morning_star", "three_white_soldiers",
            "bullish_harami", "bullish_pin_bar", "tweezer_bottom",
            "dragonfly_doji", "piercing_line",
        }
        for entry_p in out["candle_pattern_summary"]:
            tf = entry_p["tf"]
            name = entry_p["pattern"]
            if name in bullish_pattern_names:
                pts = 5 if tf in ("4h", "1d") else 3 if tf == "1h" else 2
                bullish_pattern_score += pts
                bullish_patterns_hit.append(f"{name} {tf}")
        bullish_pattern_score = min(bullish_pattern_score, 20)
        if bullish_pattern_score > 0:
            score += bullish_pattern_score
            breakdown.append({"name": f"✓ Pola candle bullish ({len(bullish_patterns_hit)})",
                              "points": bullish_pattern_score,
                              "value": ", ".join(bullish_patterns_hit[:3])})

        # 13. SMC: Bullish liquidity sweep (anti-manipulation, real bottom signal)
        sweep_4h = out.get("liquidity_sweep_4h") or {}
        sweep_1h = out.get("liquidity_sweep_1h") or {}
        sweep_15m = out.get("liquidity_sweep_15m") or {}
        if sweep_4h.get("bullish_sweep"):
            sweep_pts = int(round(20 * sweep_4h.get("sweep_strength", 0.5)))
            score += sweep_pts
            breakdown.append({"name": "✓ Liquidity sweep BULL 4h (stop hunt + reverse)",
                              "points": sweep_pts,
                              "value": f"strength {sweep_4h.get('sweep_strength', 0)}"})
        elif sweep_1h.get("bullish_sweep"):
            sweep_pts = int(round(10 * sweep_1h.get("sweep_strength", 0.5)))
            score += sweep_pts
            breakdown.append({"name": "✓ Liquidity sweep BULL 1h", "points": sweep_pts,
                              "value": f"strength {sweep_1h.get('sweep_strength', 0)}"})
        elif sweep_15m.get("bullish_sweep"):
            # Lower-TF sweep — small bonus, often noise but cumulative
            score += 4
            breakdown.append({"name": "✓ Sweep BULL 15m (LTF timing)", "points": 4,
                              "value": f"strength {sweep_15m.get('sweep_strength', 0)}"})

        # Phase 7: Liquidity grab — strongest reversal signal
        grab_4h = out.get("liquidity_grab_4h") or {}
        grab_1h = out.get("liquidity_grab_1h") or {}
        if grab_4h.get("bullish_grab"):
            score += 18
            breakdown.append({"name": "✓ Liquidity grab BULL 4h (sweep+reject same bar)",
                              "points": 18,
                              "value": f"rejection {grab_4h.get('rejection_pct', 0)}%"})
        elif grab_1h.get("bullish_grab"):
            score += 10
            breakdown.append({"name": "✓ Liquidity grab BULL 1h",
                              "points": 10,
                              "value": f"rejection {grab_1h.get('rejection_pct', 0)}%"})

        # Phase 7: Volume confirmation gate
        vc4 = out.get("volume_confirmation_4h") or {}
        if vc4.get("confirmed"):
            score += 6
            breakdown.append({"name": "✓ Volume confirmed (above baseline)",
                              "points": 6,
                              "value": f"{vc4.get('ratio', 0):.2f}× avg"})

        # 14. SMC: Bullish FVG below (price magnet from above)
        fvg = out.get("fair_value_gap_4h") or {}
        if fvg.get("bullish_fvg"):
            score += 8
            zone = fvg["bullish_fvg"]
            breakdown.append({"name": "✓ Bullish FVG 4h unfilled",
                              "points": 8,
                              "value": f"@ {zone['low']}-{zone['high']}"})

        # 15. SMC: Market structure break bullish (BOS)
        struct = out.get("market_structure_4h") or {}
        if struct.get("bos_bullish"):
            score += 10
            breakdown.append({"name": "✓ Break of Structure 4h bull (BOS)",
                              "points": 10,
                              "value": f"broke above {struct.get('last_swing_high')}"})

        # 16. Wyckoff: Accumulation phase = strong dip-buy context
        wy = out.get("wyckoff_phase") or {}
        if wy.get("phase") == "accumulation":
            wy_pts = 15 if wy.get("confidence", 0) >= 70 else 8
            score += wy_pts
            breakdown.append({"name": "✓ Wyckoff: Accumulation phase",
                              "points": wy_pts,
                              "value": f"confidence {wy.get('confidence')}%"})
        elif wy.get("phase") == "capitulation":
            score += 12
            breakdown.append({"name": "✓ Wyckoff: Capitulation (smart money buying)",
                              "points": 12, "value": "post-flush"})

        # 17. Whale stealth accumulation
        whale = out.get("whale_accumulation") or {}
        if whale.get("detected"):
            whale_pts = 15 if whale.get("intensity", 0) > 50 else 8
            score += whale_pts
            breakdown.append({"name": "✓ Whale stealth accumulation",
                              "points": whale_pts,
                              "value": f"OI +{whale.get('oi_change_pct')}% price flat"})

        # 10. Trend filter — don't dip-buy active downtrend
        if out["trend_4h"] == "downtrend":
            score -= 12
            breakdown.append({"name": "Still in 4h downtrend (risky)",
                              "points": -12, "value": "wait sideways/reversal"})
        elif out["trend_4h"] == "sideways":
            score += 5
            breakdown.append({"name": "✓ 4h consolidation (good context)",
                              "points": 5, "value": "sideways"})

        # 11. Funding trend (deepening negative = building reversal)
        if out["funding_trend_1h"] == "falling" and fr is not None and fr < 0:
            score += 8
            breakdown.append({"name": "✓ Funding deepening negative",
                              "points": 8, "value": "1h trend"})

        final_score = max(0, min(100, score))  # no baseline

    out["confluence_score"] = final_score
    out["confluence_breakdown"] = breakdown
    out["score_long"] = final_score  # LONG-side score saved separately

    # ═══════════════════════════════════════════════════════════════════
    # SHORT signal scoring — counter-trend SHORT at top
    # ═══════════════════════════════════════════════════════════════════
    short_score = 0
    short_breakdown: list[dict] = []
    dist_7d_low = out.get("dist_from_7d_low_pct")

    # SHORT hard gates: not oversold + already pumped + volume
    short_gate_volume = gate_volume
    short_gate_not_oversold = rsi_4h_v >= 35 and rsi_1d_v >= 35 and oversold_n < 2
    short_gate_elevated = dist_7d_low is not None and dist_7d_low >= 5
    short_all_gates = short_gate_volume and short_gate_not_oversold and short_gate_elevated

    if short_all_gates:
        # 1. MTF overbought
        if overbought_n >= 3:
            short_score += 35
            short_breakdown.append({"name": f"✓ MTF deep overbought ({overbought_n}/4)",
                                    "points": 35, "value": f"4h={out['rsi_4h']} 1d={out['rsi_1d']}"})
        elif overbought_n == 2:
            short_score += 22
            short_breakdown.append({"name": "✓ MTF partial overbought (2/4)",
                                    "points": 22, "value": "overbought TFs"})

        # 2. BB upper touch (mirror of lower)
        if bb_pos is not None and bb_pos > 0.95:
            short_score += 22
            short_breakdown.append({"name": "✓ BB 4h upper touch", "points": 22,
                                    "value": f"pos {bb_pos:.2f}"})

        # 3. Already pumped from 7d low
        if dist_7d_low is not None:
            if dist_7d_low > 25:
                short_score += 25
                short_breakdown.append({"name": "✓ Pumped deep (jauh dari 7d low)",
                                        "points": 25, "value": f"+{dist_7d_low:.1f}%"})
            elif dist_7d_low > 15:
                short_score += 18
                short_breakdown.append({"name": "✓ Pumped sehat (jauh dari 7d low)",
                                        "points": 18, "value": f"+{dist_7d_low:.1f}%"})
            elif dist_7d_low > 8:
                short_score += 10
                short_breakdown.append({"name": "Mild pump", "points": 10,
                                        "value": f"+{dist_7d_low:.1f}%"})

        # 4. Funding hot (longs crowded)
        if fr is not None:
            if fr > 0.15:
                short_score += 20
                short_breakdown.append({"name": "✓ Funding ekstrem positif (long ramai)",
                                        "points": 20, "value": f"{fr:.4f}%"})
            elif fr > 0.10:
                short_score += 12
                short_breakdown.append({"name": "✓ Funding positif (long crowded)",
                                        "points": 12, "value": f"{fr:.4f}%"})

        # 5. OI surging (late longs)
        if out["oi_delta_5m_pct"] is not None:
            oi = out["oi_delta_5m_pct"]
            if oi > 5:
                short_score += 14
                short_breakdown.append({"name": "✓ OI lonjakan (long telat)",
                                        "points": 14, "value": f"+{oi:.2f}%"})
            elif oi > 2:
                short_score += 7
                short_breakdown.append({"name": "OI naik", "points": 7,
                                        "value": f"+{oi:.2f}%"})

        # 6. OB ask wall — sell pressure context (only matters in overbought)
        if out["ob_imbalance_pct"] is not None and rsi_4h_v > 50:
            ob = out["ob_imbalance_pct"]
            if ob < -25:
                short_score += 10
                short_breakdown.append({"name": "✓ Ask wall berat", "points": 10,
                                        "value": f"{ob:.1f}%"})

        # 7. VWAP premium
        if out.get("vwap_dist_pct") is not None:
            vd = out["vwap_dist_pct"]
            if vd > 5:
                short_score += 12
                short_breakdown.append({"name": "✓ Above VWAP +5% (premium)",
                                        "points": 12, "value": f"+{vd:.2f}%"})

        # 8. Trend uptrend = penalty (jangan short uptrend); sideways = OK
        if out["trend_4h"] == "uptrend":
            short_score -= 12
            short_breakdown.append({"name": "Masih uptrend 4h (jangan short)",
                                    "points": -12, "value": "wait turn"})
        elif out["trend_4h"] == "sideways":
            short_score += 5
            short_breakdown.append({"name": "✓ Sideways 4h (good context)",
                                    "points": 5, "value": "consolidation"})

        # 9. Bearish candle patterns (expanded)
        bearish_score = 0
        bearish_hits = []
        bearish_pattern_names = {
            "bearish_engulfing", "shooting_star", "evening_star", "three_black_crows",
            "bearish_harami", "bearish_pin_bar", "tweezer_top",
            "gravestone_doji", "dark_cloud_cover",
        }
        for entry_p in out["candle_pattern_summary"]:
            tf = entry_p["tf"]
            name = entry_p["pattern"]
            if name in bearish_pattern_names:
                pts = 5 if tf in ("4h", "1d") else 3 if tf == "1h" else 2
                bearish_score += pts
                bearish_hits.append(f"{name} {tf}")
        bearish_score = min(bearish_score, 20)
        if bearish_score > 0:
            short_score += bearish_score
            short_breakdown.append({"name": f"✓ Pola candle bearish ({len(bearish_hits)})",
                                    "points": bearish_score,
                                    "value": ", ".join(bearish_hits[:3])})

        # 10. SMC bearish liquidity sweep (incl 15m)
        sweep_4h_s = out.get("liquidity_sweep_4h") or {}
        sweep_1h_s = out.get("liquidity_sweep_1h") or {}
        sweep_15m_s = out.get("liquidity_sweep_15m") or {}
        if sweep_4h_s.get("bearish_sweep"):
            pts = int(round(20 * sweep_4h_s.get("sweep_strength", 0.5)))
            short_score += pts
            short_breakdown.append({"name": "✓ Liquidity sweep BEAR 4h (high taken, reverse)",
                                    "points": pts, "value": f"strength {sweep_4h_s.get('sweep_strength', 0)}"})
        elif sweep_1h_s.get("bearish_sweep"):
            pts = int(round(10 * sweep_1h_s.get("sweep_strength", 0.5)))
            short_score += pts
            short_breakdown.append({"name": "✓ Liquidity sweep BEAR 1h", "points": pts,
                                    "value": f"strength {sweep_1h_s.get('sweep_strength', 0)}"})
        elif sweep_15m_s.get("bearish_sweep"):
            short_score += 4
            short_breakdown.append({"name": "✓ Sweep BEAR 15m (LTF timing)", "points": 4,
                                    "value": f"strength {sweep_15m_s.get('sweep_strength', 0)}"})

        # Phase 7: Bearish liquidity grab — strongest reversal
        grab_4h_s = out.get("liquidity_grab_4h") or {}
        grab_1h_s = out.get("liquidity_grab_1h") or {}
        if grab_4h_s.get("bearish_grab"):
            short_score += 18
            short_breakdown.append({"name": "✓ Liquidity grab BEAR 4h (sweep+reject)",
                                    "points": 18,
                                    "value": f"rejection {grab_4h_s.get('rejection_pct', 0)}%"})
        elif grab_1h_s.get("bearish_grab"):
            short_score += 10
            short_breakdown.append({"name": "✓ Liquidity grab BEAR 1h", "points": 10,
                                    "value": f"rejection {grab_1h_s.get('rejection_pct', 0)}%"})

        # Phase 7: Volume confirmation (mirrors LONG)
        vc4_s = out.get("volume_confirmation_4h") or {}
        if vc4_s.get("confirmed"):
            short_score += 6
            short_breakdown.append({"name": "✓ Volume confirmed (above baseline)",
                                    "points": 6,
                                    "value": f"{vc4_s.get('ratio', 0):.2f}× avg"})

        # 11. SMC bearish FVG above (price magnet from below)
        fvg_s = out.get("fair_value_gap_4h") or {}
        if fvg_s.get("bearish_fvg"):
            short_score += 8
            zone = fvg_s["bearish_fvg"]
            short_breakdown.append({"name": "✓ Bearish FVG 4h unfilled",
                                    "points": 8, "value": f"@ {zone['low']}-{zone['high']}"})

        # 12. Market structure break bearish (BOS)
        struct_s = out.get("market_structure_4h") or {}
        if struct_s.get("bos_bearish"):
            short_score += 10
            short_breakdown.append({"name": "✓ Break of Structure 4h bear",
                                    "points": 10,
                                    "value": f"broke below {struct_s.get('last_swing_low')}"})

        # 13. Wyckoff distribution = SHORT context
        wy_s = out.get("wyckoff_phase") or {}
        if wy_s.get("phase") == "distribution":
            pts = 15 if wy_s.get("confidence", 0) >= 70 else 8
            short_score += pts
            short_breakdown.append({"name": "✓ Wyckoff: Distribution phase",
                                    "points": pts, "value": f"confidence {wy_s.get('confidence')}%"})

        # 14. RSI bearish divergence (mirror of LONG version)
        if out.get("rsi_bearish_divergence_4h"):
            short_score += 14
            short_breakdown.append({"name": "✓ RSI bearish divergence 4h",
                                    "points": 14, "value": "price HH but RSI LH"})

        # 15. MTF telescoping bearish shift (mirror of LONG telescope)
        seq_bonus_s = _mtf_rsi_sequence_score(
            out["rsi_15m"], out["rsi_1h"], out["rsi_4h"], out["rsi_1d"], direction="SHORT"
        )
        if seq_bonus_s > 0:
            short_score += seq_bonus_s
            short_breakdown.append({"name": "✓ MTF telescoping distribution",
                                    "points": seq_bonus_s,
                                    "value": "15m < 1h < 4h (turning down first)"})

        short_final = max(0, min(100, short_score))
    else:
        short_final = 0
        if not short_gate_volume:
            short_breakdown.append({"name": "✗ GATE: thin volume", "points": 0, "value": "skipped"})
        if not short_gate_not_oversold:
            short_breakdown.append({"name": "✗ GATE: lagi oversold", "points": 0,
                                    "value": "tidak cocok short"})
        if not short_gate_elevated:
            short_breakdown.append({"name": "✗ GATE: belum cukup pump", "points": 0,
                                    "value": "perlu jauh dari 7d low"})

    out["score_short"] = short_final

    # ═══ Pick direction ═══
    long_s = out["score_long"]
    short_s = out["score_short"]
    if long_s >= 25 and long_s > short_s + 10:
        out["signal_direction"] = "LONG"
        out["confluence_score"] = long_s
    elif short_s >= 25 and short_s > long_s + 10:
        out["signal_direction"] = "SHORT"
        out["confluence_score"] = short_s
        out["confluence_breakdown"] = short_breakdown  # swap to short rationale
    else:
        out["signal_direction"] = "NONE"
        out["confluence_score"] = max(long_s, short_s)

    # ═══════════════════════════════════════════════════════════════════
    # BUG FIX: compute primary_pattern_trigger + funding_window + macro
    # adjustments BEFORE verdict + entry_plan (was after, causing inconsistency)
    # ═══════════════════════════════════════════════════════════════════
    direction = out["signal_direction"]

    # Primary pattern trigger (uses rich_patterns_early which is computed earlier)
    if direction in ("LONG", "SHORT"):
        TF_PRIORITY_EARLY = {"1d": 4, "4h": 3, "1h": 2, "15m": 1}
        candidates_early: list[tuple[int, dict, str]] = []
        for tf, plist in rich_patterns_early.items():
            for p in plist:
                if direction == "LONG" and p.get("bullish") is False:
                    continue
                if direction == "SHORT" and p.get("bullish") is True:
                    continue
                pri = TF_PRIORITY_EARLY.get(tf, 0) * 10 - p.get("bar_index_from_now", 0)
                candidates_early.append((pri, p, tf))
        if candidates_early:
            candidates_early.sort(key=lambda x: -x[0])
            _, best_p, best_tf = candidates_early[0]
            out["primary_pattern_trigger"] = {
                "tf": best_tf,
                "pattern": best_p["pattern"],
                "bullish": best_p.get("bullish"),
                "bar_index_from_now": best_p["bar_index_from_now"],
                "confirmed": best_p.get("confirmed", False),
                "confirmation_close": best_p.get("confirmation_close"),
                "close": best_p["close"],
                "high": best_p["high"],
                "low": best_p["low"],
                "trigger_price": best_p["trigger_price"],
            }

    # Funding window awareness
    out["funding_window"] = compute_funding_window_status(funding)

    # Spot/futures basis (always compute — uses cached spot ticker)
    cp_for_basis = bars_4h_smc[-1]["c"] if bars_4h_smc else None
    try:
        if cp_for_basis:
            out["spot_futures_basis"] = get_spot_futures_basis(symbol, cp_for_basis)
    except Exception:
        pass

    # Macro/flow score adjustments — applied BEFORE verdict & entry_plan
    macro_adjustments_pre: list[dict] = []
    funding_arb_signal_pre = None
    if direction in ("LONG", "SHORT"):
        # Deribit P/C ratio
        try:
            deribit_data_pre = _cached_external("deribit_BTC", 600, lambda: None) or {}
            pc_ratio_pre = deribit_data_pre.get("put_call_oi_ratio")
            if pc_ratio_pre is not None:
                if pc_ratio_pre > 1.2 and direction == "LONG":
                    macro_adjustments_pre.append({
                        "source": "deribit_pc_ratio", "name": "Deribit P/C tinggi (bearish sentiment)",
                        "value": f"{pc_ratio_pre:.2f}", "score_delta": -10, "applies_to": "LONG",
                    })
                elif pc_ratio_pre < 0.7 and direction == "SHORT":
                    macro_adjustments_pre.append({
                        "source": "deribit_pc_ratio", "name": "Deribit P/C rendah (bullish sentiment)",
                        "value": f"{pc_ratio_pre:.2f}", "score_delta": -10, "applies_to": "SHORT",
                    })
        except Exception:
            pass

        basis_pre = out.get("spot_futures_basis")
        if basis_pre and basis_pre.get("basis_pct") is not None:
            bp = basis_pre["basis_pct"]
            if bp > 0.5 and direction == "LONG":
                macro_adjustments_pre.append({
                    "source": "basis", "name": "Contango kuat (leverage long crowded)",
                    "value": f"{bp:+.3f}%", "score_delta": -8, "applies_to": "LONG",
                })
            elif bp < -0.5 and direction == "SHORT":
                macro_adjustments_pre.append({
                    "source": "basis", "name": "Backwardation kuat (leverage short crowded)",
                    "value": f"{bp:+.3f}%", "score_delta": -8, "applies_to": "SHORT",
                })

        pattern_trig_pre = out.get("primary_pattern_trigger") or {}
        if pattern_trig_pre and not pattern_trig_pre.get("confirmed"):
            if pattern_trig_pre.get("bar_index_from_now", 0) == 0:
                macro_adjustments_pre.append({
                    "source": "pattern_unconfirmed", "name": "Pattern belum dikonfirmasi (bar berjalan)",
                    "value": pattern_trig_pre.get("pattern", ""),
                    "score_delta": 0, "applies_to": direction,
                })

        vc4_pre = out.get("volume_confirmation_4h") or {}
        if vc4_pre.get("ratio") is not None and not vc4_pre.get("confirmed"):
            macro_adjustments_pre.append({
                "source": "volume_low", "name": "Volume 4h di bawah baseline",
                "value": f"{vc4_pre.get('ratio', 0):.2f}× avg",
                "score_delta": -5, "applies_to": direction,
            })

        fw_pre = out["funding_window"]
        if fw_pre and fw_pre.get("near_settlement"):
            macro_adjustments_pre.append({
                "source": "funding_window", "name": "Mendekati settle funding",
                "value": f"{fw_pre.get('minutes_to_settle', 0):.0f} mnt",
                "score_delta": -7, "applies_to": direction,
            })

    if funding and funding.get("rate") is not None:
        fr_pre = funding["rate"]
        if fr_pre > 0.0005:
            funding_arb_signal_pre = {
                "type": "short_perp_long_spot",
                "funding_rate_pct": round(fr_pre * 100, 4),
                "annualized_pct": round(fr_pre * 3 * 365 * 100, 2),
                "description": (
                    f"Funding {fr_pre*100:.3f}%/8h ({fr_pre*3*365*100:.1f}% annualized). "
                    "Long spot + short perp = collect funding."
                ),
            }
        elif fr_pre < -0.0005:
            funding_arb_signal_pre = {
                "type": "long_perp_short_spot",
                "funding_rate_pct": round(fr_pre * 100, 4),
                "annualized_pct": round(fr_pre * 3 * 365 * 100, 2),
                "description": (
                    f"Funding {fr_pre*100:.3f}%/8h. "
                    "Short spot + long perp = collect inverse funding."
                ),
            }

    out["macro_score_adjustments"] = macro_adjustments_pre
    out["funding_arb_signal"] = funding_arb_signal_pre

    # Apply macro adjustments to confluence_score BEFORE verdict
    if direction in ("LONG", "SHORT") and macro_adjustments_pre:
        total_delta_pre = sum(a["score_delta"] for a in macro_adjustments_pre)
        if total_delta_pre != 0:
            out["confluence_score"] = max(0, min(100, out["confluence_score"] + total_delta_pre))
            out["confluence_breakdown"].append({
                "name": f"Macro/flow adjustments ({len(macro_adjustments_pre)})",
                "points": total_delta_pre,
                "value": ", ".join(a["source"] for a in macro_adjustments_pre),
            })

    # ─── Verdict + sizing — direction-aware (now using post-adjustment score) ───
    fs = out["confluence_score"]

    if direction == "NONE" or fs < 25:
        out["verdict"] = "HINDARI" if fs < 20 else "BELUM SAATNYA"
        out["verdict_detail"] = "Belum ada setup valid (LONG maupun SHORT)"
        out["bias"] = "neutral"
        out["sizing_pct_equity"] = 0.0
        out["entry_plan"] = None
    else:
        # Tier name + direction
        if fs >= 80:
            tier = "BORONG"
            tier_detail = "Setup ekstrem — masuk gede"
            sz = 5.0
        elif fs >= 70:
            tier = "AKUMULASI KUAT"
            tier_detail = "Confluence kuat + konfirmasi pembalikan"
            sz = 3.0
        elif fs >= 60:
            tier = "AKUMULASI"
            tier_detail = "Sinyal valid — masuk bertahap"
            sz = 2.0
        elif fs >= 45:
            tier = "MASUK TIPIS"
            tier_detail = "Ada potensi — coba kecil dulu"
            sz = 1.0
        else:
            tier = "SABAR"
            tier_detail = "Belum cukup kuat"
            sz = 0.0

        out["verdict"] = f"{tier} {direction}"
        out["verdict_detail"] = tier_detail
        out["bias"] = "bullish" if direction == "LONG" else "bearish"
        out["sizing_pct_equity"] = sz

        # ─────────────────────────────────────────────────────────
        # Multi-tier entry plan v2 — direction-validated + rationale
        # FIX: Tier prices MUST move in adverse direction from radar.
        #      LONG averages DOWN (each tier lower price).
        #      SHORT averages UP (each tier higher price).
        # Enforce minimum spacing (5%, 10%, 15%) — never let SR levels
        # produce nonsense like SHORT tier below current.
        # ─────────────────────────────────────────────────────────
        bars_4h_last = tf_closes["Hour4"][1]
        # ── BUG FIX: use LIVE ticker fairPrice, not stale 4h close ──
        # 4h close can be up to 4 hours stale, making tier spacing inaccurate.
        live_tickers = get_all_tickers()
        live_tk = live_tickers.get(symbol, {})
        try:
            live_price = float(live_tk.get("fairPrice") or live_tk.get("lastPrice") or 0)
        except Exception:
            live_price = 0
        current_price = (
            live_price if live_price > 0
            else (bars_4h_last[-1]["c"] if bars_4h_last else None)
        )
        raw_sr = get_sr_cached(symbol)

        def _sr_price(label: str):
            return next((s["price"] for s in raw_sr if s["label"] == label), None)

        top_factors = sorted(
            [b for b in out["confluence_breakdown"] if b["points"] > 0],
            key=lambda b: -b["points"],
        )[:5]
        reasoning_list = [f"{f['name']} ({f['value']})" for f in top_factors]

        is_long = direction == "LONG"
        cp = current_price or 1.0

        # ── Adaptive spacing based on ATR (was hardcoded 5/10/15%) ──
        # Volatile coins (high ATR%) need wider tier spacing; stable coins tighter.
        # Floor: 2%/4%/8%. Cap: 8%/16%/25%. Multiplier: ATR% × {1.2, 2.4, 4.0}
        atr_pct = out.get("atr_pct_4h") or 2.0
        sp1 = max(0.02, min(0.08, (atr_pct * 1.2) / 100))
        sp2 = max(0.04, min(0.16, (atr_pct * 2.4) / 100))
        sp3 = max(0.08, min(0.25, (atr_pct * 4.0) / 100))
        SPACINGS = [0.0, sp1, sp2, sp3]

        def _pick_validated_level(candidates: list[tuple[str, float | None]],
                                  pct_floor: float) -> tuple[str | None, float]:
            """Pick best level that satisfies direction constraint.

            For LONG: tier price must be <= current_price × (1 - pct_floor).
            For SHORT: tier price must be >= current_price × (1 + pct_floor).
            Falls back to percentage-based floor if no candidate qualifies.
            """
            valid: list[tuple[str, float]] = []
            for label, p in candidates:
                if p is None:
                    continue
                if is_long:
                    # LONG: lower than current by at least pct_floor
                    if p <= cp * (1 - pct_floor):
                        valid.append((label, p))
                else:
                    # SHORT: higher than current by at least pct_floor
                    if p >= cp * (1 + pct_floor):
                        valid.append((label, p))
            if valid:
                # Pick closest to radar (most likely retest)
                if is_long:
                    best = max(valid, key=lambda x: x[1])  # highest support below
                else:
                    best = min(valid, key=lambda x: x[1])  # lowest resistance above
                return best[0], best[1]
            # Fallback: pure percentage from current
            fallback_price = cp * (1 - pct_floor) if is_long else cp * (1 + pct_floor)
            return "pct fallback", fallback_price

        # ═══════════════════════════════════════════════════════════════
        # Phase 5 Group A: TECHNICAL TIER ANCHORING
        # Build candidate pool from ALL real technical levels (not just pivots)
        # ═══════════════════════════════════════════════════════════════
        bb_lower = out["bb_lower_4h"]
        bb_upper = out["bb_upper_4h"]
        poc = (vol_profile_data or {}).get("poc") if vol_profile_data else None
        vah = (vol_profile_data or {}).get("vah") if vol_profile_data else None
        val = (vol_profile_data or {}).get("val") if vol_profile_data else None
        hvn_list = (vol_profile_data or {}).get("hvn") or []
        demand_zones = (sd_zones_data or {}).get("demand_zones") or []
        supply_zones = (sd_zones_data or {}).get("supply_zones") or []
        ob_4h = out.get("order_block_4h") or {}
        fvg_4h = out.get("fair_value_gap_4h") or {}
        bull_ob_zone = ob_4h.get("bullish_ob_zone")
        bear_ob_zone = ob_4h.get("bearish_ob_zone")
        bull_fvg_zone = fvg_4h.get("bullish_fvg")
        bear_fvg_zone = fvg_4h.get("bearish_fvg")
        spring_low = (spring_upthrust_data or {}).get("spring_low") if spring_upthrust_data else None
        upthrust_high = (spring_upthrust_data or {}).get("upthrust_high") if spring_upthrust_data else None
        anchored_vwap_lo = out.get("anchored_vwap_swing_low")
        anchored_vwap_hi = out.get("anchored_vwap_swing_high")

        # ── Multi-timeframe anchors: HTF Daily (major S/R) + 4h (current) + 1h (refinement) ──
        # Pull daily + 1h levels
        dz_1d = (sd_zones_1d or {}).get("demand_zones") or []
        sz_1d = (sd_zones_1d or {}).get("supply_zones") or []
        poc_1d = (vol_profile_1d or {}).get("poc") if vol_profile_1d else None
        val_1d = (vol_profile_1d or {}).get("val") if vol_profile_1d else None
        vah_1d = (vol_profile_1d or {}).get("vah") if vol_profile_1d else None
        hvn_1d = (vol_profile_1d or {}).get("hvn") or []

        dz_1h = (sd_zones_1h or {}).get("demand_zones") or []
        sz_1h = (sd_zones_1h or {}).get("supply_zones") or []
        poc_1h = (vol_profile_1h or {}).get("poc") if vol_profile_1h else None

        # Build LONG support candidates — HTF Daily first (priority for far tiers), then 4h, then 1h
        long_anchors: list[tuple[str, float | None]] = [
            # ─── 1h refinement (closest, for near-tier precision) ───
            ("1h Demand Zone fresh", dz_1h[0]["mid"] if dz_1h else None),
            ("1h POC", poc_1h),
            # ─── 4h core (current) ───
            ("4h Demand Zone fresh", demand_zones[0]["mid"] if demand_zones else None),
            ("4h Demand Zone 2nd", demand_zones[1]["mid"] if len(demand_zones) > 1 else None),
            ("4h VAL (volume area low)", val),
            ("4h POC", poc),
            ("4h Bullish OB mid",
                (bull_ob_zone["high"] + bull_ob_zone["low"]) / 2 if bull_ob_zone else None),
            ("4h Bullish FVG mid",
                (bull_fvg_zone["high"] + bull_fvg_zone["low"]) / 2 if bull_fvg_zone else None),
            ("Wyckoff Spring low", spring_low),
            ("Anchor VWAP swing-low", anchored_vwap_lo),
            ("4h HVN cluster (closest below)",
                min((n["price"] for n in hvn_list if n["price"] < cp), default=None) if hvn_list else None),
            ("BB lower 4h", bb_lower),
            # ─── Daily HTF (for far booster tier, major levels) ───
            ("1D Demand Zone fresh", dz_1d[0]["mid"] if dz_1d else None),
            ("1D Demand Zone 2nd", dz_1d[1]["mid"] if len(dz_1d) > 1 else None),
            ("1D VAL", val_1d),
            ("1D POC", poc_1d),
            ("1D HVN (closest below)",
                min((n["price"] for n in hvn_1d if n["price"] < cp), default=None) if hvn_1d else None),
            # ─── Classic pivots ───
            ("S1 pivot", _sr_price("S1")),
            ("S2 pivot", _sr_price("S2")),
            ("Fib 38.2", _sr_price("Fib 38.2")),
            ("Fib 50.0", _sr_price("Fib 50.0")),
            ("Fib 61.8", _sr_price("Fib 61.8")),
            ("7d low", out["low_7d"]),
            ("30d low (HTF)", out.get("low_30d")),
        ]

        # Build SHORT resistance candidates — same MTF structure
        short_anchors: list[tuple[str, float | None]] = [
            # 1h refinement
            ("1h Supply Zone fresh", sz_1h[0]["mid"] if sz_1h else None),
            ("1h POC", poc_1h),
            # 4h core
            ("4h Supply Zone fresh", supply_zones[0]["mid"] if supply_zones else None),
            ("4h Supply Zone 2nd", supply_zones[1]["mid"] if len(supply_zones) > 1 else None),
            ("4h VAH (volume area high)", vah),
            ("4h POC", poc),
            ("4h Bearish OB mid",
                (bear_ob_zone["high"] + bear_ob_zone["low"]) / 2 if bear_ob_zone else None),
            ("4h Bearish FVG mid",
                (bear_fvg_zone["high"] + bear_fvg_zone["low"]) / 2 if bear_fvg_zone else None),
            ("Wyckoff Upthrust high", upthrust_high),
            ("Anchor VWAP swing-high", anchored_vwap_hi),
            ("4h HVN cluster (closest above)",
                min((n["price"] for n in hvn_list if n["price"] > cp), default=None) if hvn_list else None),
            ("BB upper 4h", bb_upper),
            # Daily HTF
            ("1D Supply Zone fresh", sz_1d[0]["mid"] if sz_1d else None),
            ("1D Supply Zone 2nd", sz_1d[1]["mid"] if len(sz_1d) > 1 else None),
            ("1D VAH", vah_1d),
            ("1D POC", poc_1d),
            ("1D HVN (closest above)",
                min((n["price"] for n in hvn_1d if n["price"] > cp), default=None) if hvn_1d else None),
            # Classic pivots
            ("R1 pivot", _sr_price("R1")),
            ("R2 pivot", _sr_price("R2")),
            ("7d high", out["high_7d"]),
            ("30d high (HTF)", out["high_30d"]),
        ]

        anchors_pool = long_anchors if is_long else short_anchors

        def _pick_tier_anchored(used_labels: set[str], pct_floor: float) -> tuple[str | None, float]:
            """Pick best technical anchor that satisfies direction + spacing, prefer closer."""
            valid: list[tuple[str, float]] = []
            for label, p in anchors_pool:
                if p is None or label in used_labels:
                    continue
                if is_long and p <= cp * (1 - pct_floor):
                    valid.append((label, p))
                elif (not is_long) and p >= cp * (1 + pct_floor):
                    valid.append((label, p))
            if valid:
                # Prefer closest to current price (most likely retest)
                best = max(valid, key=lambda x: x[1]) if is_long else min(valid, key=lambda x: x[1])
                return best[0], best[1]
            fallback_price = cp * (1 - pct_floor) if is_long else cp * (1 + pct_floor)
            return "% fallback", fallback_price

        # Pick tiers, ensuring no duplicate anchor across tiers
        tier_radar_price = cp
        used_anchors: set[str] = set()
        u1_label, tier_utama1_price = _pick_tier_anchored(used_anchors, SPACINGS[1])
        used_anchors.add(u1_label or "")
        u2_label, tier_utama2_price = _pick_tier_anchored(used_anchors, SPACINGS[2])
        used_anchors.add(u2_label or "")
        b_label, tier_booster_price = _pick_tier_anchored(used_anchors, SPACINGS[3])
        used_anchors.add(b_label or "")

        out["tier_anchor_sources"] = {
            "utama1": u1_label,
            "utama2": u2_label,
            "booster": b_label,
        }

        # Per-tier rationale dengan technical reference yang real
        # SMC context for rationale enrichment
        wyckoff_phase = (out.get("wyckoff_phase") or {}).get("phase") or "neutral"
        whale = (out.get("whale_accumulation") or {}).get("detected") or False
        sweep_bull_4h = (out.get("liquidity_sweep_4h") or {}).get("bullish_sweep") or False
        sweep_bear_4h = (out.get("liquidity_sweep_4h") or {}).get("bearish_sweep") or False

        def _radar_rationale() -> str:
            parts = []
            if is_long:
                if sweep_bull_4h:
                    parts.append("liquidity sweep 4h baru saja terjadi (stop hunt = whale beli)")
                if wyckoff_phase == "accumulation":
                    parts.append("Wyckoff accumulation phase")
                if whale:
                    parts.append("whale stealth accumulation detected")
            else:
                if sweep_bear_4h:
                    parts.append("liquidity sweep BEAR 4h (high taken = whale jual)")
                if wyckoff_phase == "distribution":
                    parts.append("Wyckoff distribution phase")
            if not parts:
                parts.append(f"confluence {fs}/100 valid sekarang")
            return "Probe entry tipis. " + "; ".join(parts) + "."

        def _utama1_rationale(label: str | None, price: float) -> str:
            dist_pct = abs(price - cp) / cp * 100
            return (
                f"Average di {label or 'level support/resistance'} ({price:.4f}) — "
                f"{'turun' if is_long else 'naik'} ~{dist_pct:.1f}% dari radar. "
                f"Lev 50x = liq aman, total margin nambah modest."
            )

        def _utama2_rationale(label: str | None, price: float) -> str:
            dist_pct = abs(price - cp) / cp * 100
            return (
                f"Tier kedua di {label or 'support/resistance deeper'} ({price:.4f}) — "
                f"{'turun' if is_long else 'naik'} ~{dist_pct:.1f}%. "
                f"Size lebih besar karena harga lebih jauh dari fair value."
            )

        def _booster_rationale(label: str | None, price: float) -> str:
            dist_pct = abs(price - cp) / cp * 100
            return (
                f"Capitulation tier di {label or 'extreme zone'} ({price:.4f}) — "
                f"{'turun' if is_long else 'naik'} ~{dist_pct:.1f}%. "
                f"Snowball averaging. Aktifkan cuma kalau market crash benar-benar extreme."
            )

        # Phase 9.3: Dynamic leverage per confidence
        # Score 80+ = full base lev. 65-79 = 75%. 50-64 = 60%. <50 = 50%.
        if fs >= 80:
            lev_mult = 1.0
            lev_band = "high_conviction"
        elif fs >= 65:
            lev_mult = 0.75
            lev_band = "strong"
        elif fs >= 50:
            lev_mult = 0.60
            lev_band = "moderate"
        else:
            lev_mult = 0.50
            lev_band = "weak"

        def _adj_lev(base_lev: int) -> int:
            return max(5, int(base_lev * lev_mult))

        tiers_data = [
            {
                "name": "RADAR",
                "role": "radar",
                "price": tier_radar_price,
                "size_pct_equity": 0.1,
                "lev": _adj_lev(100),
                "lev_base": 100,
                "lev_mult": lev_mult,
                "trigger_label": "Sinyal valid sekarang",
                "trigger_at": "market",
                "rationale": _radar_rationale(),
            },
            {
                "name": "UTAMA 1",
                "role": "main_1",
                "price": tier_utama1_price,
                "size_pct_equity": 2.0,
                "lev": _adj_lev(50),
                "lev_base": 50,
                "lev_mult": lev_mult,
                "trigger_label": f"Retest {u1_label}",
                "trigger_at": u1_label,
                "rationale": _utama1_rationale(u1_label, tier_utama1_price),
            },
            {
                "name": "UTAMA 2",
                "role": "main_2",
                "price": tier_utama2_price,
                "size_pct_equity": 3.0,
                "lev": _adj_lev(50),
                "lev_base": 50,
                "lev_mult": lev_mult,
                "trigger_label": f"Retest {u2_label}",
                "trigger_at": u2_label,
                "rationale": _utama2_rationale(u2_label, tier_utama2_price),
            },
            {
                "name": "BOOSTER",
                "role": "booster",
                "price": tier_booster_price,
                "size_pct_equity": 5.0,
                "lev": _adj_lev(50),
                "lev_base": 50,
                "lev_mult": lev_mult,
                "trigger_label": f"Capitulation di {b_label}",
                "trigger_at": b_label,
                "rationale": _booster_rationale(b_label, tier_booster_price),
            },
        ]

        # Expose dynamic lev band in output
        out["dynamic_lev_band"] = lev_band
        out["dynamic_lev_mult"] = lev_mult

        # Compute cumulative weighted average price + total exposure
        total_size_pct = sum(t["size_pct_equity"] for t in tiers_data)
        if total_size_pct > 0:
            weighted_avg = sum(
                t["price"] * t["size_pct_equity"] for t in tiers_data if t["price"]
            ) / total_size_pct
        else:
            weighted_avg = tier_radar_price

        # Adverse price scenario: kalau semua tier kena dan price terus
        # bergerak 5% melawan booster, berapa rugi total equity?
        worst_case_price = (
            tier_booster_price * 0.95 if is_long else tier_booster_price * 1.05
        )
        worst_pct_move = abs(worst_case_price - weighted_avg) / weighted_avg
        weighted_lev = sum(
            t["lev"] * t["size_pct_equity"] for t in tiers_data
        ) / total_size_pct
        # Math:
        #   exposure_fraction = total_size_pct / 100
        #   loss_fraction = exposure_fraction × leverage × worst_pct_move
        #   loss_pct_equity = loss_fraction × 100 = total_size_pct × leverage × worst_pct_move
        worst_case_loss_pct_equity = total_size_pct * weighted_lev * worst_pct_move

        # ═══════════════════════════════════════════════════════════════
        # Phase 5 Group A: TECHNICAL TP LADDER + SL INVALIDATION + R:R
        # TP1 = nearest opposite zone/VAH/VAL
        # TP2 = next major resistance/support OR 2-3R distance
        # TP3 = far untested zone OR 7d high/low OR major HVN cluster
        # SL = beyond last spring/upthrust/swing + 1.5×ATR buffer
        # ═══════════════════════════════════════════════════════════════
        base = weighted_avg if weighted_avg else cp
        atr_for_buffer = atr_4h if atr_4h else (cp * 0.01)  # fallback 1%

        def _pick_tp_anchor(pool: list[tuple[str, float | None]], min_dist_pct: float,
                            prefer: str = "closest") -> tuple[str | None, float | None]:
            """Pick TP from pool, must be in profit direction from base, min distance."""
            valid: list[tuple[str, float]] = []
            for label, p in pool:
                if p is None:
                    continue
                if is_long and p >= base * (1 + min_dist_pct):
                    valid.append((label, p))
                elif (not is_long) and p <= base * (1 - min_dist_pct):
                    valid.append((label, p))
            if not valid:
                return None, None
            if prefer == "closest":
                best = min(valid, key=lambda x: x[1]) if is_long else max(valid, key=lambda x: x[1])
            else:  # "furthest"
                best = max(valid, key=lambda x: x[1]) if is_long else min(valid, key=lambda x: x[1])
            return best[0], best[1]

        if is_long:
            tp_pool_near = [
                ("VAH", vah),
                ("POC (jika di atas)", poc if (poc and poc > base) else None),
                ("Bearish OB mid",
                    (bear_ob_zone["high"] + bear_ob_zone["low"]) / 2 if bear_ob_zone else None),
                ("Anchor VWAP swing-high", anchored_vwap_hi),
                ("BB upper 4h", bb_upper),
                ("R1 pivot", _sr_price("R1")),
            ]
            tp_pool_far = [
                ("Supply Zone fresh", supply_zones[0]["mid"] if supply_zones else None),
                ("R2 pivot", _sr_price("R2")),
                ("7d high", out["high_7d"]),
            ]
            tp_pool_extreme = [
                ("Supply Zone 2nd", supply_zones[1]["mid"] if len(supply_zones) > 1 else None),
                ("30d high", out["high_30d"]),
                ("HVN cluster (highest)",
                    max((n["price"] for n in hvn_list), default=None) if hvn_list else None),
            ]
        else:
            tp_pool_near = [
                ("VAL", val),
                ("POC (jika di bawah)", poc if (poc and poc < base) else None),
                ("Bullish OB mid",
                    (bull_ob_zone["high"] + bull_ob_zone["low"]) / 2 if bull_ob_zone else None),
                ("Anchor VWAP swing-low", anchored_vwap_lo),
                ("BB lower 4h", bb_lower),
                ("S1 pivot", _sr_price("S1")),
            ]
            tp_pool_far = [
                ("Demand Zone fresh", demand_zones[0]["mid"] if demand_zones else None),
                ("S2 pivot", _sr_price("S2")),
                ("7d low", out["low_7d"]),
            ]
            tp_pool_extreme = [
                ("Demand Zone 2nd", demand_zones[1]["mid"] if len(demand_zones) > 1 else None),
                ("HVN cluster (lowest)",
                    min((n["price"] for n in hvn_list), default=None) if hvn_list else None),
            ]

        tp1_label, tp1_price = _pick_tp_anchor(tp_pool_near, 0.03, "closest")
        tp2_label, tp2_price = _pick_tp_anchor(tp_pool_far, 0.08, "closest")
        tp3_label, tp3_price = _pick_tp_anchor(tp_pool_extreme, 0.15, "furthest")

        # Fallback if no technical level available — use 1.5×ATR / 3×ATR / 6×ATR
        if tp1_price is None:
            tp1_price = base * (1 + 1.5 * atr_for_buffer / base) if is_long else base * (1 - 1.5 * atr_for_buffer / base)
            tp1_label = "1.5×ATR"
        if tp2_price is None:
            tp2_price = base * (1 + 3.0 * atr_for_buffer / base) if is_long else base * (1 - 3.0 * atr_for_buffer / base)
            tp2_label = "3×ATR"
        if tp3_price is None:
            tp3_price = base * (1 + 6.0 * atr_for_buffer / base) if is_long else base * (1 - 6.0 * atr_for_buffer / base)
            tp3_label = "6×ATR"

        # Enforce ordering: TP1 < TP2 < TP3 (long) or reverse (short)
        # If technical levels are out of order, sort them by distance
        tps_with_labels = [
            (tp1_price, tp1_label),
            (tp2_price, tp2_label),
            (tp3_price, tp3_label),
        ]
        if is_long:
            tps_with_labels.sort(key=lambda x: x[0])
        else:
            tps_with_labels.sort(key=lambda x: -x[0])
        (tp1_price, tp1_label), (tp2_price, tp2_label), (tp3_price, tp3_label) = tps_with_labels

        # ─── SL Invalidation level ───
        # Logic: nearest LOGICAL invalidation from entry.
        #   LONG: below first demand zone low / spring low / nearest swing low
        #   SHORT: above first supply zone high / upthrust high / nearest swing high
        # Buffer: +1.5× ATR. Cap distance at 8% to avoid absurd SLs.
        SL_MAX_PCT = 0.08  # max 8% from entry
        if is_long:
            sl_candidates = []
            if demand_zones:
                sl_candidates.append(("Below fresh demand zone", demand_zones[0]["low"]))
            if spring_low is not None:
                sl_candidates.append(("Below Wyckoff spring low", spring_low))
            structure_4h = out.get("market_structure_4h") or {}
            last_swing_low = structure_4h.get("last_swing_low")
            if last_swing_low is not None:
                sl_candidates.append(("Below last 4h swing low", last_swing_low))
            # Pick HIGHEST candidate that's BELOW entry (tightest valid SL)
            valid_sls = [(lbl, p) for lbl, p in sl_candidates if p is not None and p < tier_radar_price]
            if valid_sls:
                lbl, anchor = max(valid_sls, key=lambda x: x[1])
                sl_invalidation = anchor - 1.5 * atr_for_buffer
                sl_reason = f"{lbl} − 1.5×ATR"
            else:
                # Pure ATR-based: 3× ATR below entry
                sl_invalidation = tier_radar_price - 3.0 * atr_for_buffer
                sl_reason = "3×ATR below entry (no structural anchor)"
            # Cap at SL_MAX_PCT
            min_sl = tier_radar_price * (1 - SL_MAX_PCT)
            if sl_invalidation < min_sl:
                sl_invalidation = min_sl
                sl_reason += f" (capped at -{int(SL_MAX_PCT*100)}%)"
        else:
            sl_candidates = []
            if supply_zones:
                sl_candidates.append(("Above fresh supply zone", supply_zones[0]["high"]))
            if upthrust_high is not None:
                sl_candidates.append(("Above Wyckoff upthrust high", upthrust_high))
            structure_4h = out.get("market_structure_4h") or {}
            last_swing_high = structure_4h.get("last_swing_high")
            if last_swing_high is not None:
                sl_candidates.append(("Above last 4h swing high", last_swing_high))
            valid_sls = [(lbl, p) for lbl, p in sl_candidates if p is not None and p > tier_radar_price]
            if valid_sls:
                lbl, anchor = min(valid_sls, key=lambda x: x[1])
                sl_invalidation = anchor + 1.5 * atr_for_buffer
                sl_reason = f"{lbl} + 1.5×ATR"
            else:
                sl_invalidation = tier_radar_price + 3.0 * atr_for_buffer
                sl_reason = "3×ATR above entry (no structural anchor)"
            max_sl = tier_radar_price * (1 + SL_MAX_PCT)
            if sl_invalidation > max_sl:
                sl_invalidation = max_sl
                sl_reason += f" (capped at +{int(SL_MAX_PCT*100)}%)"

        # R:R per signal — distance from radar entry to TP1 vs to SL
        risk = abs(tier_radar_price - sl_invalidation) if sl_invalidation else None
        reward_tp1 = abs((tp1_price or 0) - tier_radar_price) if tp1_price else None
        reward_tp2 = abs((tp2_price or 0) - tier_radar_price) if tp2_price else None
        reward_tp3 = abs((tp3_price or 0) - tier_radar_price) if tp3_price else None
        rr_tp1 = reward_tp1 / risk if (risk and risk > 0 and reward_tp1) else None
        rr_tp2 = reward_tp2 / risk if (risk and risk > 0 and reward_tp2) else None
        rr_tp3 = reward_tp3 / risk if (risk and risk > 0 and reward_tp3) else None

        out["sl_invalidation"] = {
            "price": round(sl_invalidation, 8) if sl_invalidation else None,
            "reason": sl_reason,
            "distance_pct": round(abs(tier_radar_price - sl_invalidation) / tier_radar_price * 100, 3)
                if sl_invalidation else None,
        }
        out["rr_ratio"] = {
            "tp1": round(rr_tp1, 2) if rr_tp1 is not None else None,
            "tp2": round(rr_tp2, 2) if rr_tp2 is not None else None,
            "tp3": round(rr_tp3, 2) if rr_tp3 is not None else None,
            "risk_pct": round(risk / tier_radar_price * 100, 3) if (risk and tier_radar_price) else None,
        }

        plan: dict = {
            "direction": direction,
            "current_price": current_price,
            "entry_price": tier_radar_price,
            "entry_zone_label": "Tier 1 RADAR aktif sekarang" if fs >= 60 else "Tunggu confluence lebih kuat",
            "reasoning": reasoning_list,
            "stop_plus_hint": "Aktifkan SL+ setelah profit ≥+1000% margin (Radar 100x = +10% price), trail di belakang +500% margin.",
            "tiers": tiers_data,
            # NEW: cascade projection
            "cascade_projection": {
                "weighted_avg_price": round(weighted_avg, 8) if weighted_avg else None,
                "total_size_pct_equity": round(total_size_pct, 2),
                "worst_case_price": round(worst_case_price, 8) if worst_case_price else None,
                "worst_case_loss_pct_equity": round(worst_case_loss_pct_equity, 2),
                "explanation": (
                    "Kalau SEMUA tier kena dan price terus melawan sampai 5% di luar booster, "
                    f"estimasi rugi {round(worst_case_loss_pct_equity, 2)}% equity. "
                    "TP ladder dihitung dari weighted-average price (lebih realistik)."
                ),
            },
            "tp_ladder": [
                {
                    "tp": 1,
                    "price": tp1_price,
                    "pct_price": round((tp1_price - base) / base * 100, 2) if tp1_price else 0,
                    "pct_margin_100x": round(abs(tp1_price - base) / base * 100 * 100, 0) if tp1_price else 0,
                    "close_pct": 33,
                    "reason": f"TP1 di {tp1_label} (RR {rr_tp1:.2f}R)" if rr_tp1 else f"TP1 di {tp1_label}",
                },
                {
                    "tp": 2,
                    "price": tp2_price,
                    "pct_price": round((tp2_price - base) / base * 100, 2) if tp2_price else 0,
                    "pct_margin_100x": round(abs(tp2_price - base) / base * 100 * 100, 0) if tp2_price else 0,
                    "close_pct": 33,
                    "reason": f"TP2 di {tp2_label} (RR {rr_tp2:.2f}R)" if rr_tp2 else f"TP2 di {tp2_label}",
                },
                {
                    "tp": 3,
                    "price": tp3_price,
                    "pct_price": round((tp3_price - base) / base * 100, 2) if tp3_price else 0,
                    "pct_margin_100x": round(abs(tp3_price - base) / base * 100 * 100, 0) if tp3_price else 0,
                    "close_pct": 34,
                    "reason": f"TP3 di {tp3_label} (RR {rr_tp3:.2f}R)" if rr_tp3 else f"TP3 di {tp3_label}",
                },
            ],
            # Phase 5 Group A: Stop loss invalidation + R:R
            "sl_invalidation": out.get("sl_invalidation"),
            "rr_ratio": out.get("rr_ratio"),
            "tier_anchor_sources": out.get("tier_anchor_sources"),
        }
        out["entry_plan"] = plan

    # ═══════════════════════════════════════════════════════════════════
    # Phase 1+2+5: Macro context + primary pattern + MTF convergence
    # (cheap analytics already computed pre-scoring above)
    # ═══════════════════════════════════════════════════════════════════

    rich_patterns = rich_patterns_early
    direction = out["signal_direction"]
    # primary_pattern_trigger already computed pre-verdict (bug fix above)

    # MEXC API macro context: OI history, L/S ratio, funding history
    # Heavy fetches skipped in lite mode (bulk signal scan)
    if not lite:
        # MEXC public API doesn't expose OI history endpoint reliably — fall back to
        # internal polling-based history (_oi_history dict) tracked from ticker.holdVol
        try:
            oi_api = get_oi_history_api_cached(symbol, count=96)
            if oi_api:
                out["oi_history_api"] = oi_api[-30:]
            else:
                internal = _oi_history.get(symbol, [])
                out["oi_history_api"] = [
                    {"timestamp": int(t * 1000), "holdVol": v} for t, v in internal[-30:]
                ]
        except Exception:
            internal = _oi_history.get(symbol, [])
            out["oi_history_api"] = [
                {"timestamp": int(t * 1000), "holdVol": v} for t, v in internal[-30:]
            ]

        try:
            lsr_list = get_long_short_ratio_cached(symbol, count=48)
            out["long_short_ratio"] = lsr_list[-1] if lsr_list else None
            out["long_short_ratio_history"] = lsr_list[-30:] if lsr_list else []
        except Exception:
            out["long_short_ratio"] = None
            out["long_short_ratio_history"] = []

        try:
            funding_hist = get_funding_history_cached(symbol, page_size=21)
            out["funding_history"] = funding_hist[:21] if funding_hist else []
            if funding_hist:
                rates: list[float] = []
                for f in funding_hist[:21]:
                    r = f.get("fundingRate")
                    if r is None:
                        continue
                    try:
                        rates.append(float(r))
                    except Exception:
                        continue
                if rates:
                    out["funding_rate_7d_avg"] = round(sum(rates) / len(rates) * 100, 4)
        except Exception:
            pass

    # Liquidation cluster (cheap — uses internal OI tracker, no new API call)
    if bars_1h_smc:
        fr_decimal = (funding["rate"] if funding else None)
        out["liquidation_cluster"] = detect_liquidation_cluster(
            bars_1h_smc, oi_history, fr_decimal,
        )

    # Cumulative delta + orderbook heatmap — skipped in lite mode
    if not lite:
        try:
            out["cumulative_delta"] = cumulative_delta_proxy(symbol)
        except Exception:
            out["cumulative_delta"] = None
        try:
            out["orderbook_heatmap"] = orderbook_heatmap(symbol, depth=50)
        except Exception:
            out["orderbook_heatmap"] = None
        # CVD historical from kline (always works) + enriched with deals for last bar
        try:
            if bars_1h_smc:
                deals_data = None
                if ACCOUNTS:
                    try:
                        resp = ACCOUNTS[0].client.deals(symbol, limit=100)
                        deals_data = resp.get("data") if isinstance(resp, dict) else None
                        if not isinstance(deals_data, list):
                            deals_data = None
                    except Exception:
                        deals_data = None
                out["cvd_historical"] = cvd_historical_per_bar(bars_1h_smc, deals_data)
        except Exception:
            out["cvd_historical"] = None

    # BTC correlation check — cheap, runs in lite mode too (uses cached klines)
    if direction in ("LONG", "SHORT"):
        try:
            out["btc_correlation_alignment"] = btc_correlation_check(
                symbol, direction, bars_1h_smc or []
            )
        except Exception:
            out["btc_correlation_alignment"] = None

    # MTF convergence — only meaningful when direction is set
    if direction in ("LONG", "SHORT"):
        out["mtf_convergence"] = compute_mtf_convergence(
            out.get("trend_4h"),
            out.get("liquidity_sweep_4h"),
            out.get("market_structure_4h"),
            rich_patterns.get("15m", []),
            rich_patterns.get("1h", []),
            rich_patterns.get("4h", []),
            direction,
        )

    # ═══════════════════════════════════════════════════════════════════
    # Phase 5 Group B: Macro / Regime / Basis / Liquidation zones
    # ═══════════════════════════════════════════════════════════════════
    cp_now = bars_4h[-1]["c"] if bars_4h else None

    # Market regime classification
    out["market_regime"] = detect_market_regime(bars_4h_smc, out.get("atr_pct_4h"))

    if not lite:
        # Spot/Futures basis (only fetch in full mode — separate API endpoint)
        try:
            out["spot_futures_basis"] = get_spot_futures_basis(symbol, cp_now)
        except Exception:
            out["spot_futures_basis"] = None

        # Liquidation zones estimation — real OI USDT = hold_vol × contract_size × price
        try:
            oi_usdt = None
            if symbol in get_all_tickers():
                tk = get_all_tickers()[symbol]
                hold_vol = float(tk.get("holdVol") or 0)
                if hold_vol > 0 and cp_now:
                    contract = get_contract_cached(symbol)
                    contract_size = float(contract.get("contractSize") or 1)
                    oi_usdt = hold_vol * contract_size * cp_now
            fr_decimal = funding["rate"] if funding else None
            if cp_now:
                out["liquidation_zones"] = estimate_liquidation_zones(
                    cp_now, oi_usdt, fr_decimal
                )
        except Exception:
            out["liquidation_zones"] = None

    cache_dict[symbol] = (now, out)
    return out


def scan_quality_symbols() -> list[str]:
    """Return ALL MEXC futures symbols passing 24h volume threshold.

    No tier-1 whitelist — scan everything that has sufficient liquidity.
    """
    tickers = get_all_tickers()
    out = []
    for sym, tk in tickers.items():
        if not sym.endswith("_USDT"):
            continue  # Only USDT-margined
        vol = float(tk.get("amount24") or 0)
        if vol < QUALITY_MIN_VOLUME_24H_USDT:
            continue
        out.append(sym)
    return sorted(out)


def get_funding_cached(symbol: str) -> dict:
    """Funding rate + next settle time per symbol."""
    now = time.time()
    cached = _funding_cache.get(symbol)
    if cached and (now - cached[0]) < _FUNDING_TTL_SECONDS:
        return cached[1]
    any_client = ACCOUNTS[0].client
    try:
        resp = any_client.funding_rate(symbol)
    except Exception:
        return {}
    data = resp.get("data") if isinstance(resp, dict) else None
    out = {}
    if isinstance(data, dict):
        out = {
            "rate": float(data.get("fundingRate") or 0),
            "next_settle_ms": int(data.get("nextSettleTime") or 0),
            "collect_cycle_hours": int(data.get("collectCycle") or 8),
            "max_rate": float(data.get("maxFundingRate") or 0),
            "min_rate": float(data.get("minFundingRate") or 0),
        }
    _funding_cache[symbol] = (now, out)
    return out


def get_sparkline_cached(symbol: str) -> list[list[float]]:
    """Return last 96 candles of 15m (24h coverage) as [[time_ms, close, vol], ...]."""
    now = time.time()
    cached = _sparkline_cache.get(symbol)
    if cached and (now - cached[0]) < _SPARKLINE_TTL_SECONDS:
        return cached[1]
    any_client = ACCOUNTS[0].client
    try:
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - (24 * 3600 * 1000)  # 24h
        resp = any_client.klines(
            symbol=symbol, interval="Min15", start_time_ms=start_ms, end_time_ms=now_ms
        )
    except Exception:
        return []
    data = resp.get("data") if isinstance(resp, dict) else None
    out: list[list[float]] = []
    if isinstance(data, dict):
        times = data.get("time") or []
        closes = data.get("close") or []
        vols = data.get("vol") or []
        for i, (t, c) in enumerate(zip(times, closes)):
            try:
                v = float(vols[i]) if i < len(vols) else 0.0
                out.append([int(t) * 1000, float(c), v])
            except (ValueError, TypeError):
                continue
        # Keep only last 96
        out = out[-96:]
    _sparkline_cache[symbol] = (now, out)
    return out


def get_sr_cached(symbol: str) -> list[dict]:
    now = time.time()
    cached = _sr_cache.get(symbol)
    if cached and (now - cached[0]) < _SR_TTL_SECONDS:
        return cached[1]
    levels = compute_pivot_levels(symbol)
    _sr_cache[symbol] = (now, levels)
    return levels


def fetch_stop_orders_by_position(
    cli: MexcFuturesClient, active_position_ids: set[int]
) -> dict[int, dict]:
    try:
        resp = cli._request(
            "GET",
            "/api/v1/private/stoporder/list/orders",
            params={"page_num": 1, "page_size": 200, "is_finished": 0},
            private=True,
        )
    except Exception:
        return {}
    stops = (resp.get("data") or []) if isinstance(resp, dict) else []
    by_pos: dict[int, dict] = {}
    for s in stops:
        if s.get("state") != 1:
            continue
        try:
            pid = int(s.get("positionId") or 0)
        except (TypeError, ValueError):
            continue
        if pid not in active_position_ids:
            continue
        bucket = by_pos.setdefault(pid, {"tp_prices": [], "sl_prices": [], "order_ids": []})
        tp_raw = s.get("takeProfitPrice")
        sl_raw = s.get("stopLossPrice")
        try:
            tp_val = float(tp_raw) if tp_raw not in (None, "", 0, "0") else 0.0
        except (TypeError, ValueError):
            tp_val = 0.0
        try:
            sl_val = float(sl_raw) if sl_raw not in (None, "", 0, "0") else 0.0
        except (TypeError, ValueError):
            sl_val = 0.0
        if tp_val > 0:
            bucket["tp_prices"].append(tp_val)
        if sl_val > 0:
            bucket["sl_prices"].append(sl_val)
        bucket["order_ids"].append(s.get("id"))
    return by_pos


# ═══════════════════════════════════════════════════════════════════
# Per-account snapshot builder
# ═══════════════════════════════════════════════════════════════════

# Per-account snapshot cache (frontend polls /api/snapshot every 2-5s,
# /api/risk/* also calls build_account_snapshot — cache 3s to avoid duplicate work).
_account_snapshot_cache: dict[str, tuple[float, dict]] = {}
_ACCOUNT_SNAPSHOT_TTL = 10.0  # > typical snapshot duration so risk endpoints hit cache


def build_account_snapshot(acc: AccountEntry) -> dict:
    now = time.time()
    cached = _account_snapshot_cache.get(acc.id)
    if cached and (now - cached[0]) < _ACCOUNT_SNAPSHOT_TTL:
        return cached[1]
    result = _build_account_snapshot_uncached(acc)
    _account_snapshot_cache[acc.id] = (now, result)
    return result


def _build_account_snapshot_uncached(acc: AccountEntry) -> dict:
    """Fetch & enrich data for a single account."""
    cli = acc.client
    asset_resp = cli.asset("USDT").get("data", {}) or {}
    positions_resp = cli.open_positions().get("data", []) or []
    pos_ids = {int(p["positionId"]) for p in positions_resp if p.get("positionId")}
    stops_by_pos = fetch_stop_orders_by_position(cli, pos_ids)

    # Fetch ALL tickers once (cached 30s) — avoids per-position rate limit
    all_tickers = get_all_tickers()

    enriched: list[dict] = []
    for p in positions_resp:
        symbol = p["symbol"]
        ticker = all_tickers.get(symbol) or {}
        contract = get_contract_cached(symbol)

        entry = float(p.get("holdAvgPrice") or 0)
        mark = float(ticker.get("fairPrice") or ticker.get("lastPrice") or entry)
        vol = float(p.get("holdVol") or 0)
        lev = int(p.get("leverage") or 1)
        liq = float(p.get("liquidatePrice") or 0)
        im = float(p.get("im") or 0)
        realised = float(p.get("realised") or 0)
        margin_ratio = float(p.get("marginRatio") or 0)
        contract_size = float(contract.get("contractSize") or 1)
        side = "LONG" if p.get("positionType") == 1 else "SHORT"
        open_type = "isolated" if p.get("openType") == 1 else "cross"
        notional = vol * contract_size * mark

        if entry > 0:
            price_delta_pct = (mark - entry) / entry * 100
            if side == "SHORT":
                price_delta_pct = -price_delta_pct
        else:
            price_delta_pct = 0.0

        notional_change = (mark - entry) if side == "LONG" else (entry - mark)
        unrealized = notional_change * vol * contract_size
        net_pnl = unrealized + realised
        pnl_pct_real = price_delta_pct
        pnl_pct_lev = (net_pnl / im * 100) if im > 0 else 0.0

        if liq > 0 and mark > 0:
            buffer_pct = ((mark - liq) / mark * 100) if side == "LONG" else ((liq - mark) / mark * 100)
        else:
            buffer_pct = None

        pid = int(p.get("positionId") or 0)
        stop_bucket = stops_by_pos.get(pid, {})
        tp_prices = sorted(stop_bucket.get("tp_prices", []))
        sl_prices = sorted(stop_bucket.get("sl_prices", []))

        nearest_tp = None
        if tp_prices:
            if side == "LONG":
                above = [x for x in tp_prices if x > mark]
                nearest_tp = min(above) if above else max(tp_prices)
            else:
                below = [x for x in tp_prices if x < mark]
                nearest_tp = max(below) if below else min(tp_prices)
        farthest_tp = (max(tp_prices) if side == "LONG" else min(tp_prices)) if tp_prices else None

        nearest_sl = None
        if sl_prices:
            if side == "LONG":
                below = [x for x in sl_prices if x < mark]
                nearest_sl = max(below) if below else min(sl_prices)
            else:
                above = [x for x in sl_prices if x > mark]
                nearest_sl = min(above) if above else max(sl_prices)

        tp_dist_pct = None
        if nearest_tp and mark > 0:
            d = (nearest_tp - mark) / mark * 100
            tp_dist_pct = d if side == "LONG" else -d
        sl_dist_pct = None
        if nearest_sl and mark > 0:
            d = (mark - nearest_sl) / mark * 100
            sl_dist_pct = d if side == "LONG" else -d

        funding = get_funding_cached(symbol)
        sparkline = get_sparkline_cached(symbol)
        raw_sr = get_sr_cached(symbol)
        # Cross-signal enrichment: compute analytics for this symbol
        try:
            sym_analytics = compute_analytics(symbol)
        except Exception:
            sym_analytics = None
        sr_levels = []
        for lvl in raw_sr:
            price_val = lvl["price"]
            if mark > 0 and price_val > 0:
                d = (price_val - mark) / mark * 100
                dist = d if side == "LONG" else -d
            else:
                dist = 0.0
            sr_levels.append(
                {
                    "label": lvl["label"],
                    "price": price_val,
                    "kind": lvl["kind"],
                    "distance_pct": round(dist, 4),
                }
            )

        enriched.append(
            {
                "coin": contract.get("baseCoin") or symbol.split("_")[0],
                "icon_url": contract.get("baseCoinIconUrl") or None,
                "symbol": symbol,
                "side": side,
                "open_type": open_type,
                "lev": lev,
                "margin": round(im, 6),
                "notional": round(notional, 4),
                "price": mark,
                "entry": entry,
                "price_delta_pct": round(price_delta_pct, 4),
                "pnl_usdt": round(net_pnl, 4),
                "pnl_unrealized": round(unrealized, 4),
                "pnl_realised": round(realised, 4),
                "pnl_pct_real": round(pnl_pct_real, 4),
                "pnl_pct_lev": round(pnl_pct_lev, 4),
                "margin_ratio": round(margin_ratio * 100, 4),
                "liq_price": liq if liq > 0 else None,
                "buffer_pct": round(buffer_pct, 4) if buffer_pct is not None else None,
                "tp_price": nearest_tp,
                "tp_price_farthest": farthest_tp,
                "tp_count": len(tp_prices),
                "tp_dist_pct": round(tp_dist_pct, 4) if tp_dist_pct is not None else None,
                "tp_all": tp_prices,
                "sl_price": nearest_sl,
                "sl_count": len(sl_prices),
                "sl_dist_pct": round(sl_dist_pct, 4) if sl_dist_pct is not None else None,
                "sl_all": sl_prices,
                "sr_levels": sr_levels,
                "funding": funding,
                "sparkline": sparkline,
                "signal_score": sym_analytics.get("confluence_score") if sym_analytics else None,
                "signal_verdict": sym_analytics.get("verdict") if sym_analytics else None,
                "signal_oversold_n": sym_analytics.get("mtf_oversold_count") if sym_analytics else None,
                "signal_overbought_n": sym_analytics.get("mtf_overbought_count") if sym_analytics else None,
                "signal_bb_lower": sym_analytics.get("bb_lower_touch") if sym_analytics else None,
                "signal_dist_7d_high": sym_analytics.get("dist_from_7d_high_pct") if sym_analytics else None,
                "position_id": pid,
                "create_time": p.get("createTime"),
                "update_time": p.get("updateTime"),
                "account_id": acc.id,
                "account_name": acc.name,
                "account_color": acc.color,
            }
        )

    # Detect closures: compare current position_ids to last seen
    current_ids = {p["position_id"]: p for p in enriched}
    last_seen = _previous_position_ids.get(acc.id, {})
    for prev_pid, prev_snap in last_seen.items():
        if prev_pid not in current_ids:
            # Position closed since last poll
            _closed_positions_log.append(
                {
                    "ts": int(time.time() * 1000),
                    "account_id": acc.id,
                    "account_name": acc.name,
                    "symbol": prev_snap.get("symbol"),
                    "side": prev_snap.get("side"),
                    "coin": prev_snap.get("coin"),
                    "icon_url": prev_snap.get("icon_url"),
                    "lev": prev_snap.get("lev"),
                    "entry": prev_snap.get("entry"),
                    "exit_estimate": prev_snap.get("price"),
                    "pnl_final": prev_snap.get("pnl_usdt"),
                    "pnl_unrealized_last": prev_snap.get("pnl_unrealized"),
                    "pnl_realised_last": prev_snap.get("pnl_realised"),
                    "margin_used": prev_snap.get("margin"),
                }
            )
            if len(_closed_positions_log) > _CLOSED_LOG_MAX:
                _closed_positions_log.pop(0)
    _previous_position_ids[acc.id] = current_ids

    # Cache equity for cascade orchestrator
    acc._cached_equity = float(asset_resp.get("equity") or 0)

    return {
        "account": {
            "id": acc.id,
            "name": acc.name,
            "color": acc.color,
            "category": acc.category,
            "equity": float(asset_resp.get("equity") or 0),
            "available": float(asset_resp.get("availableBalance") or 0),
            # MEXC web's "Saldo Dompet" label = equity − unrealized (NOT cashBalance API field).
            # cashBalance API returns the available-after-margin portion only.
            "cash": float(asset_resp.get("equity") or 0) - float(asset_resp.get("unrealized") or 0),
            "position_margin": float(asset_resp.get("positionMargin") or 0),
            "unrealized": float(asset_resp.get("unrealized") or 0),
            "frozen": float(asset_resp.get("frozenBalance") or 0),
        },
        "positions": enriched,
    }


# ═══════════════════════════════════════════════════════════════════
# FastAPI
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(title="MEXC Futures Dashboard")


DIST = ROOT / "ui-web" / "dist"
LEGACY_INDEX = ROOT / "ui" / "index.html"


_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.get("/")
def index():
    spa_index = DIST / "index.html"
    if spa_index.exists():
        return FileResponse(spa_index, headers=_NO_CACHE_HEADERS)
    if LEGACY_INDEX.exists():
        return FileResponse(LEGACY_INDEX, headers=_NO_CACHE_HEADERS)
    return JSONResponse({"detail": "no index"}, status_code=404)


_signals_threshold = 50  # new strict scoring — 50+ = real dip-buy candidate


@app.get("/api/signals")
def get_signals(min_score: int = Query(default=_signals_threshold, ge=0, le=100)):
    """Scan quality symbols, compute confluence, return top entry candidates (paper mode).

    Uses lite analytics (skips heavy MEXC API per-symbol calls) and a thread pool
    to keep scan fast. Full data is fetched when user expands a signal.
    """
    started = time.time()
    symbols = scan_quality_symbols()
    from concurrent.futures import ThreadPoolExecutor

    def _compute(sym: str) -> tuple[str, dict]:
        try:
            return sym, compute_analytics(sym, lite=True)
        except Exception:
            return sym, {}

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=6) as ex:  # reduced from 12 to avoid rate-limit
        for sym, a in ex.map(_compute, symbols):
            results[sym] = a

    out = []
    for sym in symbols:
        a = results.get(sym) or {}
        if not a:
            continue
        direction = a.get("signal_direction", "NONE")
        if a["confluence_score"] >= min_score and direction != "NONE":
            # Phase 5 Group E: log to journal
            try:
                record_signal_event(sym, a)
            except Exception:
                pass
            out.append(
                {
                    "symbol": sym,
                    "direction": direction,
                    "confluence_score": a["confluence_score"],
                    "score_long": a.get("score_long", 0),
                    "score_short": a.get("score_short", 0),
                    "breakdown": a["confluence_breakdown"],
                    "verdict": a.get("verdict"),
                    "rsi_15m": a.get("rsi_15m"),
                    "rsi_1h": a.get("rsi_1h"),
                    "rsi_4h": a.get("rsi_4h"),
                    "rsi_1d": a.get("rsi_1d"),
                    "mtf_oversold_count": a.get("mtf_oversold_count", 0),
                    "mtf_overbought_count": a.get("mtf_overbought_count", 0),
                    "bb_lower_touch": a.get("bb_lower_touch", False),
                    "dist_from_7d_high_pct": a.get("dist_from_7d_high_pct"),
                    "dist_from_7d_low_pct": a.get("dist_from_7d_low_pct"),
                    "volume_capitulation": a.get("volume_capitulation", False),
                    "oi_delta_5m_pct": a.get("oi_delta_5m_pct"),
                    "funding_rate_pct": a.get("funding_rate_pct"),
                    "volume_24h_usdt": a.get("volume_24h_usdt"),
                    "trend_4h": a.get("trend_4h"),
                    "rsi_bullish_divergence_4h": a.get("rsi_bullish_divergence_4h", False),
                    "rsi_bearish_divergence_4h": a.get("rsi_bearish_divergence_4h", False),
                    "three_bar_reversal_1h": a.get("three_bar_reversal_1h", False),
                    "candle_pattern_summary": a.get("candle_pattern_summary", []),
                    "entry_plan": a.get("entry_plan"),
                    "sizing_pct_equity": a.get("sizing_pct_equity", 0),
                    # Phase 1+2 enrichments
                    "primary_pattern_trigger": a.get("primary_pattern_trigger"),
                    "mtf_convergence": a.get("mtf_convergence"),
                    "wyckoff_spring_upthrust": a.get("wyckoff_spring_upthrust"),
                    "wyckoff_phase": a.get("wyckoff_phase"),
                    "liquidity_sweep_4h": a.get("liquidity_sweep_4h"),
                    "liquidation_cluster": a.get("liquidation_cluster"),
                    "sd_zones_4h": a.get("sd_zones_4h"),
                    "volume_profile_4h": a.get("volume_profile_4h"),
                    "long_short_ratio": a.get("long_short_ratio"),
                    "funding_rate_7d_avg": a.get("funding_rate_7d_avg"),
                    "cumulative_delta": a.get("cumulative_delta"),
                    "orderbook_heatmap": a.get("orderbook_heatmap"),
                    # Phase 5 Group A/B/C/D enrichments
                    "sl_invalidation": a.get("sl_invalidation"),
                    "rr_ratio": a.get("rr_ratio"),
                    "tier_anchor_sources": a.get("tier_anchor_sources"),
                    "atr_4h": a.get("atr_4h"),
                    "atr_pct_4h": a.get("atr_pct_4h"),
                    "anchored_vwap_swing_low": a.get("anchored_vwap_swing_low"),
                    "anchored_vwap_swing_high": a.get("anchored_vwap_swing_high"),
                    "market_regime": a.get("market_regime"),
                    "spot_futures_basis": a.get("spot_futures_basis"),
                    "liquidation_zones": a.get("liquidation_zones"),
                    "cvd_historical": a.get("cvd_historical"),
                    "btc_correlation_alignment": a.get("btc_correlation_alignment"),
                    # Phase 7+8 enrichments
                    "liquidity_grab_4h": a.get("liquidity_grab_4h"),
                    "liquidity_grab_1h": a.get("liquidity_grab_1h"),
                    "liquidity_sweep_15m": a.get("liquidity_sweep_15m"),
                    "volume_confirmation_4h": a.get("volume_confirmation_4h"),
                    "funding_window": a.get("funding_window"),
                    "macro_score_adjustments": a.get("macro_score_adjustments"),
                    "funding_arb_signal": a.get("funding_arb_signal"),
                    # Phase 9.3
                    "dynamic_lev_band": a.get("dynamic_lev_band"),
                    "dynamic_lev_mult": a.get("dynamic_lev_mult"),
                    # Phase 7 multi-TF data
                    "sd_zones_1d": a.get("sd_zones_1d"),
                    "sd_zones_1h": a.get("sd_zones_1h"),
                    "volume_profile_1d": a.get("volume_profile_1d"),
                    "volume_profile_1h": a.get("volume_profile_1h"),
                }
            )
    # Sort by confluence desc
    out.sort(key=lambda x: -x["confluence_score"])
    return JSONResponse(
        {
            "ts": int(time.time() * 1000),
            "latency_ms": int((time.time() - started) * 1000),
            "min_score_threshold": min_score,
            "scanned_count": len(symbols),
            "signal_count": len(out),
            "signals": out[:20],  # top 20
        }
    )


@app.get("/api/analytics/{symbol}")
def get_analytics(symbol: str):
    """Get analysis for specific symbol (used by AnalysisCard)."""
    return JSONResponse({"symbol": symbol, **compute_analytics(symbol)})


# ═══════════════════════════════════════════════════════════════════
# Phase 5 Group B: /api/macro — global market regime endpoint
# ═══════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════
# Phase 6 Group H: Cascade Orchestrator — auto entry/TP/SL/SL+
# ═══════════════════════════════════════════════════════════════════
def _cascade_market_price(symbol: str) -> float | None:
    """Latest mark price — WS realtime first, REST fallback."""
    # Phase 16: try WebSocket cache first (instant)
    ws_price = WS_CLIENT.get_price(symbol)
    if ws_price and ws_price > 0:
        return ws_price
    # Fallback: REST get_all_tickers (cached 30s)
    tickers = get_all_tickers()
    if symbol in tickers:
        tk = tickers[symbol]
        try:
            return float(tk.get("fairPrice") or tk.get("lastPrice") or 0) or None
        except Exception:
            return None
    return None


def _cascade_account_provider(account_id: str) -> AccountEntry | None:
    for a in ACCOUNTS:
        if a.id == account_id:
            return a
    return None


def _cascade_executor_factory(acc: AccountEntry) -> CascadeExecutor:
    return CascadeExecutor(acc)


# Configure + start orchestrator
CASCADE_ORCHESTRATOR.configure(
    market_price_provider=_cascade_market_price,
    account_provider=_cascade_account_provider,
    executor_factory=_cascade_executor_factory,
)


@app.on_event("startup")
def _startup_cascade():
    CASCADE_ORCHESTRATOR.start()
    # Phase 16: start WebSocket realtime client
    WS_CLIENT.start()


@app.on_event("shutdown")
def _shutdown_cascade():
    CASCADE_ORCHESTRATOR.stop()
    WS_CLIENT.stop()


@app.get("/api/ws/status")
def get_ws_status():
    """WebSocket realtime client status (connection, cache size, message stats)."""
    return JSONResponse(WS_CLIENT.status())


class CascadeStartRequest(BaseModel):
    symbol: str
    account_id: str
    mode: str = "paper"  # "paper" | "live"
    size_multiplier: float = 1.0


@app.post("/api/cascade/start")
def cascade_start(req: CascadeStartRequest):
    """Start a cascade for the given symbol on the given account.
    Pulls latest analytics to get entry_plan + SL + tier definitions.
    """
    a = compute_analytics(req.symbol, lite=False)
    if not a.get("entry_plan"):
        raise HTTPException(status_code=400, detail="symbol has no valid entry plan")
    signal_payload = {
        "symbol": req.symbol,
        "signal_direction": a.get("signal_direction"),
        "confluence_score": a.get("confluence_score", 0),
        "entry_plan": a.get("entry_plan"),
    }
    try:
        mode = CascadeMode(req.mode)
    except Exception:
        raise HTTPException(status_code=400, detail=f"invalid mode: {req.mode}")
    try:
        cascade = CASCADE_ORCHESTRATOR.create_from_signal(
            signal_payload, req.account_id, mode=mode, size_multiplier=req.size_multiplier
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return JSONResponse({"ok": True, "cascade": _serialize_cascade(cascade)})


@app.get("/api/cascade/active")
def cascade_active():
    """List all currently-running cascades."""
    cascades = CASCADE_ORCHESTRATOR.list_active()
    return JSONResponse({
        "count": len(cascades),
        "live_enabled": CASCADE_LIVE_ENABLED,
        "items": [_serialize_cascade(c) for c in cascades],
    })


@app.get("/api/cascade/all")
def cascade_all():
    """All cascades incl. terminal states (recent history)."""
    cascades = CASCADE_ORCHESTRATOR.list_all()
    return JSONResponse({
        "count": len(cascades),
        "items": [_serialize_cascade(c) for c in cascades],
    })


@app.post("/api/cascade/{cascade_id}/cancel")
def cascade_cancel(cascade_id: str):
    c = CASCADE_ORCHESTRATOR.cancel(cascade_id, reason="api_cancel")
    if not c:
        raise HTTPException(status_code=404, detail="cascade not found")
    return JSONResponse({"ok": True, "cascade": _serialize_cascade(c)})


class CascadeModeReq(BaseModel):
    mode: str


@app.post("/api/cascade/{cascade_id}/mode")
def cascade_set_mode(cascade_id: str, req: CascadeModeReq):
    try:
        mode = CascadeMode(req.mode)
    except Exception:
        raise HTTPException(status_code=400, detail=f"invalid mode: {req.mode}")
    try:
        c = CASCADE_ORCHESTRATOR.set_mode(cascade_id, mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not c:
        raise HTTPException(status_code=404, detail="cascade not found")
    return JSONResponse({"ok": True, "cascade": _serialize_cascade(c)})


@app.post("/api/cascade/kill-switch")
def cascade_kill_switch():
    """Emergency: cancel all LIVE cascades + close their positions."""
    n = CASCADE_ORCHESTRATOR.kill_all_live()
    return JSONResponse({"ok": True, "cancelled_count": n})


@app.get("/api/cascade/journal")
def cascade_journal(limit: int = Query(default=200, ge=1, le=2000)):
    return JSONResponse({"count": limit, "entries": cascade_list_journal(limit)})


@app.get("/api/cascade/performance")
def cascade_performance():
    return JSONResponse(cascade_performance_metrics())


def _serialize_cascade(c) -> dict:
    from dataclasses import asdict
    return asdict(c)


# ═══════════════════════════════════════════════════════════════════
# Phase 5 Group E: Risk endpoints
# ═══════════════════════════════════════════════════════════════════
@app.get("/api/risk/portfolio")
def get_portfolio_risk():
    """Portfolio heat metric + heat-based size recommendation + correlation cluster."""
    # Parallel snapshot fetch (was sequential, slow)
    all_positions: list[dict] = []
    total_equity = 0.0
    per_account: list[dict] = []

    def _portfolio_fetch(acc):
        try:
            snap = build_account_snapshot(acc)
            positions = snap.get("positions", [])
            equity = float(snap.get("account", {}).get("equity") or 0)
            heat = compute_portfolio_heat(positions, equity)
            return (positions, equity, {"account_id": acc.id, "account_name": acc.name, **heat})
        except Exception:
            return ([], 0.0, None)

    if ACCOUNTS:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(ACCOUNTS))) as ex:
            results = list(ex.map(_portfolio_fetch, ACCOUNTS))
        for positions, equity, ah in results:
            all_positions.extend(positions)
            total_equity += equity
            if ah:
                per_account.append(ah)
    heat = compute_portfolio_heat(all_positions, total_equity)

    # Phase 9.1: Heat-based size auto-reduction recommendation
    h_pct = heat.get("total_heat_pct", 0)
    if h_pct >= 25:
        size_multiplier = 0.0
        size_rec = "BLOCKED — heat melebihi 25%, jangan tambah posisi baru"
    elif h_pct >= 20:
        size_multiplier = 0.3
        size_rec = "Reduce 70% — heat tinggi, cuma probe entry kecil"
    elif h_pct >= 15:
        size_multiplier = 0.6
        size_rec = "Reduce 40% — heat moderate-high"
    elif h_pct >= 8:
        size_multiplier = 0.85
        size_rec = "Slight reduce 15% — heat moderate"
    else:
        size_multiplier = 1.0
        size_rec = "Full size OK — heat aman"

    # Phase 9.4: Correlation cluster — group symbols by correlation
    correlation_clusters: list[dict] = []
    if all_positions:
        try:
            symbol_returns: dict[str, list[float]] = {}
            for p in all_positions:
                sym = p.get("symbol")
                if not sym or sym in symbol_returns:
                    continue
                try:
                    bars = fetch_klines_cached(sym, "Min60", 30)
                    closes = [b["c"] for b in bars[-30:]]
                    if len(closes) >= 10:
                        symbol_returns[sym] = closes
                except Exception:
                    continue
            # BUG FIX: union-find for transitive correlation clusters
            # If A↔B (>0.65) and B↔C (>0.65) but A↔C (<0.65), C should still cluster with A via B
            symbols = list(symbol_returns.keys())
            parent: dict[str, str] = {s: s for s in symbols}

            def _find(x: str) -> str:
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            def _union(a: str, b: str) -> None:
                ra, rb = _find(a), _find(b)
                if ra != rb:
                    parent[ra] = rb

            # Compute all pairwise correlations once, union pairs above threshold
            for i, sym_a in enumerate(symbols):
                for sym_b in symbols[i + 1:]:
                    corr = compute_correlation(symbol_returns[sym_a], symbol_returns[sym_b])
                    if corr is not None and corr > 0.65:
                        _union(sym_a, sym_b)

            # Group by root parent
            groups: dict[str, list[str]] = {}
            for s in symbols:
                root = _find(s)
                groups.setdefault(root, []).append(s)
            for members in groups.values():
                if len(members) >= 2:
                    correlation_clusters.append({"symbols": members, "size": len(members)})
        except Exception:
            pass

    raw_count = len({p.get("symbol") for p in all_positions if p.get("symbol")})
    effective_count = raw_count - sum(c["size"] - 1 for c in correlation_clusters)

    return JSONResponse({
        "ts": int(time.time() * 1000),
        "total_equity": round(total_equity, 2),
        "heat": heat,
        "per_account": per_account,
        "size_recommendation": {
            "multiplier": size_multiplier,
            "reason": size_rec,
        },
        "correlation": {
            "raw_position_count": raw_count,
            "effective_position_count": max(1, effective_count) if raw_count > 0 else 0,
            "clusters": correlation_clusters,
        },
    })


@app.get("/api/risk/kelly")
def get_kelly_recommendation():
    """Kelly Criterion sizing based on journal history (stub — needs outcomes)."""
    journal = read_signal_journal(limit=500)
    # Without outcomes recorded, return baseline
    # When outcomes (win/loss) are recorded, this will give real Kelly
    win_rate = 0.55  # default assumption until journal has outcomes
    avg_r_win = 2.2
    avg_r_loss = 1.0
    if journal:
        rrs = [j.get("rr_tp1") for j in journal if j.get("rr_tp1") is not None]
        if rrs:
            avg_r_win = sum(rrs) / len(rrs)
    return JSONResponse(compute_kelly_sizing(win_rate, avg_r_win, avg_r_loss))


@app.get("/api/risk/journal")
def get_signal_journal(limit: int = Query(default=100, ge=1, le=500)):
    """Recent signal triggers logged."""
    return JSONResponse({
        "ts": int(time.time() * 1000),
        "count": min(limit, len(read_signal_journal(limit))),
        "entries": read_signal_journal(limit),
    })


_daily_pnl_log: dict[str, float] = {}  # date string -> realised PnL today

def _daily_pnl_key() -> str:
    from datetime import datetime
    return datetime.utcnow().strftime("%Y-%m-%d")


@app.get("/api/risk/circuit-breaker")
def get_circuit_breaker():
    """Daily loss circuit breaker + Phase 9.2 loss cooldown detection."""
    # Parallel account snapshot fetch (was sequential — too slow)
    daily_realised = 0.0
    total_equity = 0.0

    def _fetch(acc):
        try:
            snap = build_account_snapshot(acc)
            return (
                float(snap.get("totals", {}).get("pnl_realised") or 0),
                float(snap.get("account", {}).get("equity") or 0),
            )
        except Exception:
            return (0.0, 0.0)

    if ACCOUNTS:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(ACCOUNTS))) as ex:
            for pnl, eq in ex.map(_fetch, ACCOUNTS):
                daily_realised += pnl
                total_equity += eq
    daily_pct = (daily_realised / total_equity * 100) if total_equity > 0 else 0
    THRESHOLD_PCT = -3.0
    tripped = daily_pct < THRESHOLD_PCT

    # Phase 9.2: Loss cooldown — BUG FIX: include all outcomes (WIN/LOSS/BE/CANCELLED)
    # so streak breaks correctly on non-loss events
    cooldown_active = False
    cooldown_reason = None
    cooldown_until_ms = None
    try:
        journal = cascade_list_journal(500)
        # Include ALL close events; sort desc by close ts
        all_closes = [e for e in journal if e.get("event") == "close" and e.get("outcome")]
        all_closes.sort(key=lambda x: -(x.get("closed_ts_ms") or 0))
        now_ms = int(time.time() * 1000)
        last_6h_ms = now_ms - 6 * 3600 * 1000
        recent_outcomes = [
            e for e in all_closes
            if (e.get("closed_ts_ms") or 0) >= last_6h_ms
        ]
        if recent_outcomes:
            consecutive_losses = 0
            last_loss_ts = None
            for e in recent_outcomes:
                outcome = e.get("outcome")
                if outcome == "LOSS":
                    consecutive_losses += 1
                    if last_loss_ts is None:
                        last_loss_ts = e.get("closed_ts_ms") or now_ms
                else:
                    # WIN, BREAKEVEN, or CANCELLED breaks the loss streak
                    break

            if consecutive_losses >= 3 and last_loss_ts:
                cooldown_until_ms = last_loss_ts + 12 * 3600 * 1000
                if now_ms < cooldown_until_ms:
                    cooldown_active = True
                    cooldown_reason = "3+ kerugian beruntun (cooldown 12 jam)"
                else:
                    cooldown_until_ms = None
            elif consecutive_losses >= 2 and last_loss_ts:
                cooldown_until_ms = last_loss_ts + 4 * 3600 * 1000
                if now_ms < cooldown_until_ms:
                    cooldown_active = True
                    cooldown_reason = "2 kerugian beruntun (cooldown 4 jam)"
                else:
                    cooldown_until_ms = None
    except Exception:
        pass

    recommendation = "operating normally"
    if tripped:
        recommendation = "PAUSE signals — daily loss limit hit"
    elif cooldown_active:
        recommendation = f"COOLDOWN — {cooldown_reason}"

    return JSONResponse({
        "ts": int(time.time() * 1000),
        "daily_realised": round(daily_realised, 4),
        "daily_pct_equity": round(daily_pct, 3),
        "threshold_pct": THRESHOLD_PCT,
        "tripped": tripped,
        "cooldown_active": cooldown_active,
        "cooldown_reason": cooldown_reason,
        "cooldown_until_ms": cooldown_until_ms,
        "minutes_until_cooldown_ends": (
            round((cooldown_until_ms - int(time.time() * 1000)) / 60000, 1)
            if cooldown_until_ms else None
        ),
        "recommendation": recommendation,
    })


@app.get("/api/risk/pattern-winrate")
def get_pattern_winrate():
    """Phase 14/15: Win rate aggregation from BOTH cascade journal AND
    MEXC closed positions history. Grouped by direction, score band, and pattern name.
    """
    # Combine cascade journal closes + actual MEXC closed positions
    journal = cascade_list_journal(2000)
    cascade_closes = [e for e in journal if e.get("event") == "close"]

    # MEXC closed positions (real account history) — use last 200
    mexc_closes: list[dict] = []
    try:
        # _closed_positions_log holds recent MEXC closure detection
        for c in _closed_positions_log[-200:]:
            mexc_closes.append({
                "symbol": c.get("symbol"),
                "direction": c.get("side"),
                "realized_pnl_usdt": float(c.get("pnl_final") or 0),
                "score": 50,
                "source": "mexc_real",
            })
    except Exception:
        pass

    all_closes = cascade_closes + mexc_closes
    if not all_closes:
        return JSONResponse({
            "total_closed": 0,
            "by_direction": {},
            "by_score_band": {},
            "by_pattern": {},
            "note": "Belum ada trade closed (cascade journal kosong + MEXC history kosong)",
        })

    # By direction
    direction_stats: dict[str, dict] = {}
    for c in all_closes:
        d = c.get("direction") or "UNK"
        if d not in direction_stats:
            direction_stats[d] = {"wins": 0, "losses": 0, "total_pnl": 0.0}
        pnl = float(c.get("realized_pnl_usdt") or 0)
        direction_stats[d]["total_pnl"] += pnl
        if pnl > 0:
            direction_stats[d]["wins"] += 1
        elif pnl < 0:
            direction_stats[d]["losses"] += 1
    for d in direction_stats:
        total = direction_stats[d]["wins"] + direction_stats[d]["losses"]
        direction_stats[d]["win_rate"] = round(
            direction_stats[d]["wins"] / total * 100, 1
        ) if total > 0 else 0
        direction_stats[d]["total_pnl"] = round(direction_stats[d]["total_pnl"], 4)

    # By score band — only cascade closes (MEXC doesn't have our score)
    score_bands: dict[str, dict] = {}
    for c in cascade_closes:
        s = c.get("score", 0)
        band = (
            "premium_80+" if s >= 80
            else "strong_65-79" if s >= 65
            else "moderate_50-64" if s >= 50
            else "weak_<50"
        )
        if band not in score_bands:
            score_bands[band] = {"wins": 0, "losses": 0, "total_pnl": 0.0, "trades": 0}
        score_bands[band]["trades"] += 1
        pnl = float(c.get("realized_pnl_usdt") or 0)
        score_bands[band]["total_pnl"] += pnl
        if pnl > 0:
            score_bands[band]["wins"] += 1
        elif pnl < 0:
            score_bands[band]["losses"] += 1
    for b in score_bands:
        total = score_bands[b]["wins"] + score_bands[b]["losses"]
        score_bands[b]["win_rate"] = round(
            score_bands[b]["wins"] / total * 100, 1
        ) if total > 0 else 0
        score_bands[b]["total_pnl"] = round(score_bands[b]["total_pnl"], 4)

    # By pattern (cascade closes that have notes with pattern info, OR enrich via symbol-history)
    pattern_stats: dict[str, dict] = {}
    for c in cascade_closes:
        # Try to extract pattern from notes (Phase 7 added primary pattern at cascade creation)
        pattern_name = None
        for note in c.get("notes") or []:
            # Look for pattern reference like "primary pattern: hammer 4h"
            if "pattern" in note.lower():
                lower = note.lower()
                for pat in ("bullish_engulfing", "bearish_engulfing", "hammer", "shooting_star",
                            "bullish_pin_bar", "bearish_pin_bar", "dragonfly_doji", "gravestone_doji",
                            "morning_star", "evening_star", "three_white_soldiers", "three_black_crows",
                            "piercing_line", "dark_cloud_cover", "tweezer_bottom", "tweezer_top",
                            "bullish_harami", "bearish_harami"):
                    if pat in lower:
                        pattern_name = pat
                        break
                break
        if not pattern_name:
            continue
        if pattern_name not in pattern_stats:
            pattern_stats[pattern_name] = {"wins": 0, "losses": 0, "trades": 0, "total_pnl": 0.0}
        pattern_stats[pattern_name]["trades"] += 1
        pnl = float(c.get("realized_pnl_usdt") or 0)
        pattern_stats[pattern_name]["total_pnl"] += pnl
        if pnl > 0:
            pattern_stats[pattern_name]["wins"] += 1
        elif pnl < 0:
            pattern_stats[pattern_name]["losses"] += 1
    for p in pattern_stats:
        total = pattern_stats[p]["wins"] + pattern_stats[p]["losses"]
        pattern_stats[p]["win_rate"] = round(
            pattern_stats[p]["wins"] / total * 100, 1
        ) if total > 0 else 0
        pattern_stats[p]["total_pnl"] = round(pattern_stats[p]["total_pnl"], 4)

    return JSONResponse({
        "total_closed": len(all_closes),
        "cascade_closes": len(cascade_closes),
        "mexc_closes": len(mexc_closes),
        "by_direction": direction_stats,
        "by_score_band": score_bands,
        "by_pattern": pattern_stats,
    })


# ═══════════════════════════════════════════════════════════════════
# Phase 6 Group I: External Data Integrations
# Deribit options + CoinGecko + Fear&Greed + CryptoPanic + Binance
# All free / no-auth endpoints. Cached aggressively to respect rate limits.
# ═══════════════════════════════════════════════════════════════════

def _http_get_json(url: str, timeout: int = 8) -> dict | list | None:
    """Generic HTTP GET → JSON helper. Uses DoH for ISP DNS-hijack bypass."""
    try:
        from urllib.request import Request, urlopen
        from urllib.parse import urlparse
        from mexc_futures_engine.dns import resolve_a_records_doh, override_getaddrinfo

        host = urlparse(url).hostname or ""
        overrides: dict[str, str] = {}
        # Only use DoH for known-hijacked external domains
        if host in _EXTERNAL_DOH_HOSTS:
            cached_ip = _doh_ip_cache.get(host)
            now = time.time()
            if not cached_ip or (now - cached_ip[0]) > 3600:
                try:
                    ips = resolve_a_records_doh(host, "https://1.1.1.1/dns-query")
                    if ips:
                        _doh_ip_cache[host] = (now, ips[0])
                except Exception:
                    pass
            if host in _doh_ip_cache:
                overrides[host] = _doh_ip_cache[host][1]

        req = Request(url, headers={"User-Agent": "Mozilla/5.0 mexc-engine/1.0"})
        if overrides:
            with override_getaddrinfo(overrides):
                with urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode())
        else:
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
    except Exception:
        return None


# Hosts that the ISP DNS-hijacks → must resolve via DoH
_EXTERNAL_DOH_HOSTS = {
    "www.deribit.com",
    "fapi.binance.com",
    "api.binance.com",
    "api.coingecko.com",
    "api.alternative.me",
    "cryptopanic.com",
    "api.mexc.com",  # spot API may also be hijacked
    "api.llama.fi",
    "coins.llama.fi",
}
_doh_ip_cache: dict[str, tuple[float, str]] = {}


_external_cache: dict[str, tuple[float, dict | list]] = {}


def _cached_external(key: str, ttl: int, fetcher) -> dict | list | None:
    now = time.time()
    entry = _external_cache.get(key)
    if entry and (now - entry[0]) < ttl:
        return entry[1]
    val = fetcher()
    if val is not None:
        _external_cache[key] = (now, val)
    elif entry:
        return entry[1]  # serve stale on fetch failure
    return val


@app.get("/api/external/fear-greed")
def get_fear_greed():
    """Alternative.me Fear & Greed Index (free)."""
    def fetch():
        data = _http_get_json("https://api.alternative.me/fng/?limit=7&format=json")
        if not data or not isinstance(data, dict):
            return None
        items = data.get("data", [])
        if not items:
            return None
        cur = items[0]
        return {
            "current": int(cur.get("value", 0)),
            "classification": cur.get("value_classification"),
            "timestamp": int(cur.get("timestamp", 0)) * 1000,
            "history": [
                {"value": int(d["value"]), "ts": int(d["timestamp"]) * 1000,
                 "class": d.get("value_classification")}
                for d in items[:7]
            ],
        }
    data = _cached_external("fng", 1800, fetch)
    return JSONResponse(data or {"current": None})


@app.get("/api/external/coingecko-global")
def get_coingecko_global():
    """CoinGecko global stats: real BTC dominance + total market cap."""
    def fetch():
        d = _http_get_json("https://api.coingecko.com/api/v3/global")
        if not d or "data" not in d:
            return None
        g = d["data"]
        return {
            "total_market_cap_usd": g.get("total_market_cap", {}).get("usd"),
            "total_volume_24h_usd": g.get("total_volume", {}).get("usd"),
            "btc_dominance_pct": g.get("market_cap_percentage", {}).get("btc"),
            "eth_dominance_pct": g.get("market_cap_percentage", {}).get("eth"),
            "active_cryptocurrencies": g.get("active_cryptocurrencies"),
            "market_cap_change_24h_usd_pct": g.get("market_cap_change_percentage_24h_usd"),
            "updated_at": g.get("updated_at"),
        }
    data = _cached_external("coingecko_global", 300, fetch)
    return JSONResponse(data or {})


@app.get("/api/external/deribit-options")
def get_deribit_options(currency: str = Query(default="BTC")):
    """Deribit BTC/ETH options stats: put/call ratio + max pain + summary.

    Endpoint: public/get_book_summary_by_currency for raw options.
    """
    def fetch():
        cur = currency.upper()
        d = _http_get_json(
            f"https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency={cur}&kind=option"
        )
        if not d or "result" not in d:
            return None
        items = d["result"]
        if not items:
            return None
        # Aggregate puts vs calls
        call_oi = 0.0
        put_oi = 0.0
        call_vol = 0.0
        put_vol = 0.0
        strike_oi: dict[float, dict] = {}  # strike → {call_oi, put_oi}
        for opt in items:
            name = opt.get("instrument_name", "")
            # Format: BTC-26DEC25-100000-C / ...-P
            parts = name.split("-")
            if len(parts) != 4:
                continue
            try:
                strike = float(parts[2])
            except Exception:
                continue
            kind = parts[3]
            oi = float(opt.get("open_interest", 0) or 0)
            vol = float(opt.get("volume", 0) or 0)
            if strike not in strike_oi:
                strike_oi[strike] = {"call_oi": 0, "put_oi": 0}
            if kind == "C":
                call_oi += oi
                call_vol += vol
                strike_oi[strike]["call_oi"] += oi
            elif kind == "P":
                put_oi += oi
                put_vol += vol
                strike_oi[strike]["put_oi"] += oi

        # Put/Call ratio
        pc_ratio_oi = put_oi / call_oi if call_oi > 0 else None
        pc_ratio_vol = put_vol / call_vol if call_vol > 0 else None

        # Max pain: strike where total option holders lose the most (sum of ITM call payoff + put payoff is minimum)
        # Simplified: strike with maximum combined OI (proxy for "pinned" strike)
        max_pain_strike = None
        max_pinned = 0
        sorted_strikes = sorted(strike_oi.items(), key=lambda x: -(x[1]["call_oi"] + x[1]["put_oi"]))
        if sorted_strikes:
            max_pain_strike = sorted_strikes[0][0]
            max_pinned = sorted_strikes[0][1]["call_oi"] + sorted_strikes[0][1]["put_oi"]

        # Top 5 strikes by OI
        top_strikes = [
            {"strike": s, "total_oi": v["call_oi"] + v["put_oi"], "call_oi": v["call_oi"], "put_oi": v["put_oi"]}
            for s, v in sorted_strikes[:5]
        ]
        return {
            "currency": cur,
            "put_call_oi_ratio": round(pc_ratio_oi, 3) if pc_ratio_oi is not None else None,
            "put_call_vol_ratio": round(pc_ratio_vol, 3) if pc_ratio_vol is not None else None,
            "total_call_oi": round(call_oi, 2),
            "total_put_oi": round(put_oi, 2),
            "max_pain_strike": max_pain_strike,
            "max_pain_oi": round(max_pinned, 2),
            "top_strikes_by_oi": top_strikes,
            "interpretation": (
                "bearish_sentiment" if pc_ratio_oi and pc_ratio_oi > 1.2
                else "bullish_sentiment" if pc_ratio_oi and pc_ratio_oi < 0.7
                else "neutral"
            ),
        }
    data = _cached_external(f"deribit_{currency.upper()}", 600, fetch)
    return JSONResponse(data or {})


@app.get("/api/external/cryptopanic")
def get_cryptopanic_news(currencies: str = Query(default="")):
    """CryptoPanic free public news feed (no API key needed for basic endpoint)."""
    def fetch():
        params = "?public=true"
        if currencies:
            params += f"&currencies={currencies}"
        d = _http_get_json(f"https://cryptopanic.com/api/v1/posts/{params}")
        if not d or "results" not in d:
            return None
        items = []
        for r in d.get("results", [])[:30]:
            items.append({
                "title": r.get("title"),
                "url": r.get("url"),
                "published_at": r.get("published_at"),
                "source": (r.get("source") or {}).get("title"),
                "currencies": [c.get("code") for c in r.get("currencies", []) if c.get("code")],
                "votes": r.get("votes", {}),
            })
        return {"count": len(items), "items": items}
    data = _cached_external(f"cryptopanic_{currencies}", 300, fetch)
    return JSONResponse(data or {"count": 0, "items": []})


@app.get("/api/external/binance-funding")
def get_binance_funding(symbol: str = Query(default="BTCUSDT")):
    """Binance public futures: aggregated funding + OI for cross-validation."""
    def fetch():
        fr_data = _http_get_json(
            f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={symbol}"
        )
        oi_data = _http_get_json(
            f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}"
        )
        lsr_data = _http_get_json(
            f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={symbol}&period=5m&limit=12"
        )
        out: dict = {}
        if isinstance(fr_data, dict):
            try:
                out["funding_rate"] = float(fr_data.get("lastFundingRate", 0))
                out["next_funding_ms"] = int(fr_data.get("nextFundingTime", 0))
                out["mark_price"] = float(fr_data.get("markPrice", 0))
                out["index_price"] = float(fr_data.get("indexPrice", 0))
            except Exception:
                pass
        if isinstance(oi_data, dict):
            try:
                out["open_interest"] = float(oi_data.get("openInterest", 0))
            except Exception:
                pass
        if isinstance(lsr_data, list) and lsr_data:
            try:
                out["long_short_ratio"] = float(lsr_data[-1].get("longShortRatio", 0))
                out["long_account_pct"] = float(lsr_data[-1].get("longAccount", 0)) * 100
                out["short_account_pct"] = float(lsr_data[-1].get("shortAccount", 0)) * 100
                out["lsr_history"] = [
                    {"ts": int(x["timestamp"]), "ratio": float(x["longShortRatio"])}
                    for x in lsr_data
                ]
            except Exception:
                pass
        return out
    data = _cached_external(f"binance_{symbol}", 60, fetch)
    return JSONResponse(data or {})


@app.get("/api/external/defillama")
def get_defillama_global():
    """DeFi Llama — total DEX volume + DeFi TVL (free public API)."""
    def fetch():
        out: dict[str, Any] = {}
        # DEX volume aggregate
        dex = _http_get_json("https://api.llama.fi/overview/dexs?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true")
        if isinstance(dex, dict):
            try:
                out["dex_total_24h_volume_usd"] = float(dex.get("total24h", 0))
                out["dex_total_7d_volume_usd"] = float(dex.get("total7d", 0))
                out["dex_change_24h_pct"] = float(dex.get("change_1d", 0))
                out["dex_change_7d_pct"] = float(dex.get("change_7d", 0))
            except Exception:
                pass
        # DeFi TVL aggregate
        tvl = _http_get_json("https://api.llama.fi/v2/historicalChainTvl")
        if isinstance(tvl, list) and len(tvl) > 7:
            try:
                latest = tvl[-1]
                prev_24h = tvl[-2] if len(tvl) >= 2 else None
                prev_7d = tvl[-7] if len(tvl) >= 7 else None
                latest_tvl = float(latest.get("tvl", 0))
                out["defi_total_tvl_usd"] = latest_tvl
                if prev_24h:
                    p24 = float(prev_24h.get("tvl", 0))
                    if p24 > 0:
                        out["defi_tvl_change_24h_pct"] = round((latest_tvl - p24) / p24 * 100, 3)
                if prev_7d:
                    p7 = float(prev_7d.get("tvl", 0))
                    if p7 > 0:
                        out["defi_tvl_change_7d_pct"] = round((latest_tvl - p7) / p7 * 100, 3)
            except Exception:
                pass
        return out if out else None
    data = _cached_external("defillama_global", 600, fetch)
    return JSONResponse(data or {})


@app.get("/api/external/all")
def get_external_all():
    """Aggregate all external data in one shot."""
    return JSONResponse({
        "ts": int(time.time() * 1000),
        "fear_greed": (get_fear_greed().body and json.loads(get_fear_greed().body)) or {},
        "coingecko_global": (get_coingecko_global().body and json.loads(get_coingecko_global().body)) or {},
        "deribit_btc": (get_deribit_options("BTC").body and json.loads(get_deribit_options("BTC").body)) or {},
        "deribit_eth": (get_deribit_options("ETH").body and json.loads(get_deribit_options("ETH").body)) or {},
        "binance_btc": (get_binance_funding("BTCUSDT").body and json.loads(get_binance_funding("BTCUSDT").body)) or {},
    })


# ═══════════════════════════════════════════════════════════════════
# Phase 6 Group J: Backtest engine — replay historical klines, simulate
# signal generation, compute realized PnL with our entry/TP/SL rules.
# ═══════════════════════════════════════════════════════════════════

def _simulated_signal_score(window_bars: list[dict]) -> dict | None:
    """Phase 15: lightweight version of compute_analytics scoring, runnable on historical
    window. Returns {direction, score, sl_pct, tp1_pct, tp2_pct, tp3_pct} or None if no signal.

    Replicates KEY gates + scoring components from compute_analytics:
    - MTF RSI alignment (using same window at multiple "TF" approximations)
    - BB position
    - Distance from recent high/low
    - Candle pattern detection on last bar
    - Liquidity sweep / grab
    """
    if len(window_bars) < 50:
        return None

    closes = [b["c"] for b in window_bars]
    cur_close = closes[-1]
    cur_bar = window_bars[-1]

    # RSI series (proxy MTF: 14-period on 1x, 4x, 12x intervals — approximating 4h)
    rsi_1 = _compute_rsi(closes, 14)
    rsi_4 = _compute_rsi(closes[::4][-30:], 14) if len(closes) >= 60 else None
    rsi_12 = _compute_rsi(closes[::12][-30:], 14) if len(closes) >= 180 else None
    if rsi_1 is None:
        return None

    # BB
    bb = _bollinger_lower(closes, 20, 2.0)
    bb_pos = None
    bb_lower_touch = False
    if bb:
        lower, _middle, upper = bb
        if upper > lower:
            bb_pos = (cur_close - lower) / (upper - lower)
            if cur_close <= lower + (upper - lower) * 0.05:
                bb_lower_touch = True

    # Distance from window high/low
    win_high = max(b["h"] for b in window_bars[-42:])
    win_low = min(b["l"] for b in window_bars[-42:])
    dist_high = (cur_close - win_high) / win_high * 100
    dist_low = (cur_close - win_low) / win_low * 100

    # Liquidity sweep at last bar
    sweep = detect_liquidity_sweep(window_bars[-25:], lookback=20)
    grab = detect_liquidity_grab(window_bars[-25:], lookback=20)
    patterns = detect_candle_patterns_rich(window_bars[-5:])
    bullish_count = sum(1 for p in patterns if p.get("bullish") is True)
    bearish_count = sum(1 for p in patterns if p.get("bullish") is False)

    # Score LONG
    long_s = 0
    if rsi_1 < 30:
        long_s += 25
    elif rsi_1 < 40:
        long_s += 12
    if bb_lower_touch:
        long_s += 18
    if dist_high < -5:
        long_s += 12
    elif dist_high < -2:
        long_s += 5
    if sweep.get("bullish_sweep"):
        long_s += 15
    if grab.get("bullish_grab"):
        long_s += 18
    if bullish_count > bearish_count:
        long_s += 10
    if rsi_4 is not None and rsi_4 < 35:
        long_s += 12

    # Score SHORT
    short_s = 0
    if rsi_1 > 70:
        short_s += 25
    elif rsi_1 > 60:
        short_s += 12
    if bb_pos is not None and bb_pos > 0.95:
        short_s += 18
    if dist_low > 8:
        short_s += 12
    if sweep.get("bearish_sweep"):
        short_s += 15
    if grab.get("bearish_grab"):
        short_s += 18
    if bearish_count > bullish_count:
        short_s += 10
    if rsi_4 is not None and rsi_4 > 65:
        short_s += 12

    # Pick direction
    if long_s >= 25 and long_s > short_s + 10:
        direction = "LONG"
        score = long_s
    elif short_s >= 25 and short_s > long_s + 10:
        direction = "SHORT"
        score = short_s
    else:
        return None

    # ATR for tier sizing
    atr = _atr(window_bars, 14)
    atr_pct = (atr / cur_close * 100) if atr and cur_close > 0 else 2.0
    sl_pct = max(0.02, min(0.08, atr_pct * 1.5 / 100))
    tp1_pct = sl_pct * 1.5  # 1.5R
    tp2_pct = sl_pct * 3.0  # 3R
    tp3_pct = sl_pct * 5.0  # 5R

    return {
        "direction": direction,
        "score": score,
        "entry": cur_close,
        "sl_pct": sl_pct,
        "tp1_pct": tp1_pct,
        "tp2_pct": tp2_pct,
        "tp3_pct": tp3_pct,
        "ts": int(cur_bar.get("t", 0)),
    }


@app.get("/api/backtest/{symbol}")
def run_backtest(
    symbol: str,
    bars: int = Query(default=200, ge=50, le=500),
    interval: str = Query(default="Hour4"),
    leverage: int = Query(default=50, ge=1, le=125),
    size_pct: float = Query(default=2.0, ge=0.1, le=20),
    min_score: int = Query(default=45, ge=20, le=100),
):
    """Phase 15: Backtest using full engine-like scoring at each historical bar.

    For each bar: simulate compute_analytics-style scoring (RSI MTF + BB + dist + sweep +
    grab + patterns), pick direction if score ≥ min_score, simulate trade with 3-tier TP
    (1.5R, 3R, 5R) closing 33% each. Use ATR-based SL.

    leverage: effective lev per trade (default 50x = utama tier)
    size_pct: % equity per trade (default 2%)
    min_score: only enter when scored above this threshold (default 45)
    """
    klines = fetch_klines_cached(symbol, interval, bars)
    if not klines or len(klines) < 50:
        return JSONResponse({"error": "insufficient kline data (need 50+ bars)"})

    trades: list[dict] = []
    equity = 1000.0
    open_trade: dict | None = None
    equity_curve: list[float] = []
    lev_mult = leverage * (size_pct / 100.0)
    skipped_low_score = 0
    skipped_open_trade = 0

    for i in range(50, len(klines)):
        bar = klines[i]
        window = klines[: i + 1]

        # ─── Close open trade if SL/TP hit ───
        if open_trade:
            is_long = open_trade["dir"] == "LONG"
            # Check TPs in order: TP1, TP2, TP3, SL
            exit_reason = None
            exit_price = None
            close_pct = 0
            if is_long:
                if bar["l"] <= open_trade["sl"]:
                    exit_reason = "SL"
                    exit_price = open_trade["sl"]
                    close_pct = open_trade["remaining_pct"]
                elif not open_trade.get("tp1_hit") and bar["h"] >= open_trade["tp1"]:
                    exit_reason = "TP1"
                    exit_price = open_trade["tp1"]
                    close_pct = 33
                    open_trade["tp1_hit"] = True
                    open_trade["sl"] = open_trade["entry"]  # move SL to BE
                elif open_trade.get("tp1_hit") and not open_trade.get("tp2_hit") and bar["h"] >= open_trade["tp2"]:
                    exit_reason = "TP2"
                    exit_price = open_trade["tp2"]
                    close_pct = 33
                    open_trade["tp2_hit"] = True
                elif open_trade.get("tp2_hit") and bar["h"] >= open_trade["tp3"]:
                    exit_reason = "TP3"
                    exit_price = open_trade["tp3"]
                    close_pct = open_trade["remaining_pct"]
            else:  # SHORT
                if bar["h"] >= open_trade["sl"]:
                    exit_reason = "SL"
                    exit_price = open_trade["sl"]
                    close_pct = open_trade["remaining_pct"]
                elif not open_trade.get("tp1_hit") and bar["l"] <= open_trade["tp1"]:
                    exit_reason = "TP1"
                    exit_price = open_trade["tp1"]
                    close_pct = 33
                    open_trade["tp1_hit"] = True
                    open_trade["sl"] = open_trade["entry"]
                elif open_trade.get("tp1_hit") and not open_trade.get("tp2_hit") and bar["l"] <= open_trade["tp2"]:
                    exit_reason = "TP2"
                    exit_price = open_trade["tp2"]
                    close_pct = 33
                    open_trade["tp2_hit"] = True
                elif open_trade.get("tp2_hit") and bar["l"] <= open_trade["tp3"]:
                    exit_reason = "TP3"
                    exit_price = open_trade["tp3"]
                    close_pct = open_trade["remaining_pct"]

            if exit_reason:
                price_move = ((exit_price - open_trade["entry"]) / open_trade["entry"]) * 100
                if not is_long:
                    price_move = -price_move
                pnl_partial = price_move * lev_mult * (close_pct / 100)
                equity = max(0.0, equity * (1 + pnl_partial / 100))
                open_trade["remaining_pct"] -= close_pct
                open_trade.setdefault("legs", []).append({
                    "reason": exit_reason, "price": exit_price, "pnl_pct": pnl_partial,
                    "ts": int(bar.get("t", 0)),
                })
                if open_trade["remaining_pct"] <= 0 or exit_reason == "SL":
                    # Trade fully closed
                    open_trade["pnl_pct"] = sum(l["pnl_pct"] for l in open_trade["legs"])
                    open_trade["outcome"] = (
                        "WIN" if open_trade["pnl_pct"] > 0
                        else "LOSS" if open_trade["pnl_pct"] < 0
                        else "BE"
                    )
                    trades.append(open_trade)
                    open_trade = None

        # ─── Open new trade if score-based signal triggers and no open ───
        if open_trade is None:
            signal = _simulated_signal_score(window)
            if signal and signal["score"] >= min_score:
                entry = signal["entry"]
                is_long = signal["direction"] == "LONG"
                sl = entry * (1 - signal["sl_pct"]) if is_long else entry * (1 + signal["sl_pct"])
                tp1 = entry * (1 + signal["tp1_pct"]) if is_long else entry * (1 - signal["tp1_pct"])
                tp2 = entry * (1 + signal["tp2_pct"]) if is_long else entry * (1 - signal["tp2_pct"])
                tp3 = entry * (1 + signal["tp3_pct"]) if is_long else entry * (1 - signal["tp3_pct"])
                open_trade = {
                    "dir": signal["direction"],
                    "score": signal["score"],
                    "entry": entry,
                    "sl": sl,
                    "tp1": tp1,
                    "tp2": tp2,
                    "tp3": tp3,
                    "remaining_pct": 100,
                    "ts": int(bar.get("t", 0)),
                }
            elif signal:
                skipped_low_score += 1
        else:
            skipped_open_trade += 1

        equity_curve.append(round(equity, 4))

    # Close any remaining open trade at last close
    if open_trade is not None:
        last_close = klines[-1]["c"]
        is_long = open_trade["dir"] == "LONG"
        price_move = ((last_close - open_trade["entry"]) / open_trade["entry"]) * 100
        if not is_long:
            price_move = -price_move
        pnl_partial = price_move * lev_mult * (open_trade["remaining_pct"] / 100)
        open_trade.setdefault("legs", []).append({
            "reason": "EOD",
            "price": last_close,
            "pnl_pct": pnl_partial,
            "ts": int(klines[-1].get("t", 0)),
        })
        open_trade["pnl_pct"] = sum(l["pnl_pct"] for l in open_trade["legs"])
        open_trade["outcome"] = "WIN" if open_trade["pnl_pct"] > 0 else "LOSS" if open_trade["pnl_pct"] < 0 else "BE"
        trades.append(open_trade)
        open_trade = None

    # Metrics
    pnls = [t["pnl_pct"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    n = len(pnls)
    win_rate = len(wins) / n * 100 if n else 0
    total_pnl = sum(pnls)
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    expectancy = total_pnl / n if n else 0
    # MDD on equity curve
    peak = equity_curve[0] if equity_curve else 1000
    max_dd = 0.0
    for v in equity_curve:
        peak = max(peak, v)
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

    return JSONResponse({
        "symbol": symbol,
        "interval": interval,
        "bars_scanned": bars,
        "trades": trades,
        "metrics": {
            "total_trades": n,
            "win_rate_pct": round(win_rate, 2),
            "total_return_pct": round((equity - 1000) / 1000 * 100, 3),
            "expectancy_pct": round(expectancy, 4),
            "avg_win_pct": round(avg_win, 3),
            "avg_loss_pct": round(avg_loss, 3),
            "max_drawdown_pct": round(max_dd, 3),
            "final_equity": round(equity, 2),
        },
        "equity_curve": equity_curve[-100:],
    })


@app.get("/api/macro")
def get_macro_context():
    """Global market regime — uses REAL CoinGecko data when available, falls back to MEXC proxy."""
    dom_proxy = get_btc_dominance_proxy() or {}

    # Try CoinGecko (real global) first via cached external — actively fetch if not cached
    def _fetch_cg():
        d = _http_get_json("https://api.coingecko.com/api/v3/global")
        if not d or "data" not in d:
            return None
        g = d["data"]
        return {
            "btc_dominance_pct": g.get("market_cap_percentage", {}).get("btc"),
            "eth_dominance_pct": g.get("market_cap_percentage", {}).get("eth"),
            "market_cap_change_24h_usd_pct": g.get("market_cap_change_percentage_24h_usd"),
            "total_market_cap_usd": g.get("total_market_cap", {}).get("usd"),
        }
    cg_data = _cached_external("coingecko_global", 300, _fetch_cg) or {}
    real_btc_dom = cg_data.get("btc_dominance_pct")
    real_eth_dom = cg_data.get("eth_dominance_pct")
    real_mcap_chg = cg_data.get("market_cap_change_24h_usd_pct")

    # Compose: prefer real, fallback proxy
    btc_dominance = {
        "btc_dominance_pct": real_btc_dom if real_btc_dom is not None else dom_proxy.get("btc_dominance_pct"),
        "btc_dominance_source": "coingecko" if real_btc_dom is not None else "mexc_proxy",
        "eth_dominance_pct": real_eth_dom,
        "eth_btc_ratio": dom_proxy.get("eth_btc_ratio"),
        "btc_change_24h_pct": dom_proxy.get("btc_change_24h_pct"),
        "global_mcap_change_24h_pct": real_mcap_chg,
        "top10_share_pct": dom_proxy.get("top10_share_pct"),
    }

    # BTC regime — use compute_analytics in lite mode for BTC itself
    btc_lite = compute_analytics("BTC_USDT", lite=True)
    btc_regime = btc_lite.get("market_regime") or {}
    btc_trend_4h = btc_lite.get("trend_4h")
    btc_rsi_4h = btc_lite.get("rsi_4h")

    # Alt season indicator from ETH/BTC ratio
    eth_btc = btc_dominance.get("eth_btc_ratio")
    alt_season = None
    if eth_btc is not None:
        if eth_btc > 0.045:
            alt_season = "alt_season_likely"
        elif eth_btc > 0.035:
            alt_season = "neutral"
        else:
            alt_season = "btc_season"

    # Market mood from BTC change + regime + global mcap
    btc_change = btc_dominance.get("btc_change_24h_pct") or 0
    if btc_change < -3 and btc_trend_4h == "downtrend":
        market_mood = "risk_off"
    elif btc_change > 3 and btc_trend_4h == "uptrend":
        market_mood = "risk_on"
    elif btc_regime.get("regime") in ("trending_up", "mild_up"):
        market_mood = "constructive"
    elif btc_regime.get("regime") in ("trending_down", "mild_down"):
        market_mood = "defensive"
    else:
        market_mood = "neutral"

    return JSONResponse({
        "ts": int(time.time() * 1000),
        "btc_dominance": btc_dominance,
        "btc_regime": btc_regime,
        "btc_trend_4h": btc_trend_4h,
        "btc_rsi_4h": btc_rsi_4h,
        "alt_season": alt_season,
        "market_mood": market_mood,
    })


@app.get("/api/closed-positions")
def closed_positions(limit: int = Query(default=20, ge=1, le=200)):
    """Return recent position closures detected by the backend monitor."""
    items = list(reversed(_closed_positions_log[-limit:]))
    return JSONResponse({"count": len(items), "items": items})


@app.get("/api/categories")
def list_categories():
    """Return distinct categories currently used + recommended presets."""
    used = {a.category for a in ACCOUNTS if a.category}
    presets = {"utama", "radar", "booster", "hedge", "test"}
    all_cats = sorted(used | presets)
    return JSONResponse({"categories": all_cats, "used": sorted(used)})


@app.get("/api/accounts")
def list_accounts():
    return JSONResponse(
        {
            "accounts": [
                {"id": a.id, "name": a.name, "color": a.color, "category": a.category}
                for a in ACCOUNTS
            ]
        }
    )


@app.get("/api/snapshot")
def snapshot(accounts: str | None = Query(default=None)):
    started = time.time()

    if accounts:
        selected_ids = [s.strip() for s in accounts.split(",") if s.strip()]
        selected = [ACCOUNTS_BY_ID[i] for i in selected_ids if i in ACCOUNTS_BY_ID]
    else:
        selected = ACCOUNTS

    # Parallel fetch per account
    per_account: list[dict] = []
    if selected:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(selected))) as ex:
            futures = {ex.submit(build_account_snapshot, a): a for a in selected}
            for fut in concurrent.futures.as_completed(futures):
                try:
                    per_account.append(fut.result())
                except Exception as e:
                    a = futures[fut]
                    per_account.append(
                        {
                            "account": {"id": a.id, "name": a.name, "color": a.color, "error": str(e)},
                            "positions": [],
                        }
                    )

    # Merge positions across accounts (preserve original input order by account id)
    per_account.sort(key=lambda x: [a.id for a in ACCOUNTS].index(x["account"]["id"]) if x["account"]["id"] in [a.id for a in ACCOUNTS] else 999)

    all_positions: list[dict] = []
    counter = 1
    for entry in per_account:
        for pos in entry["positions"]:
            pos["no"] = counter
            counter += 1
            all_positions.append(pos)

    # Aggregate totals + account-level breakdown
    total_pnl_unrealized = sum(p["pnl_unrealized"] for p in all_positions)
    total_pnl_realised = sum(p["pnl_realised"] for p in all_positions)
    total_margin = sum(p["margin"] for p in all_positions)
    total_notional = sum(p["notional"] for p in all_positions)

    account_summaries = [
        {
            "id": e["account"]["id"],
            "name": e["account"]["name"],
            "color": e["account"]["color"],
            "category": e["account"].get("category", "utama"),
            "equity": e["account"].get("equity", 0.0),
            "available": e["account"].get("available", 0.0),
            "cash": e["account"].get("cash", 0.0),  # cashBalance from MEXC API
            "unrealized": e["account"].get("unrealized", 0.0),
            "position_margin": e["account"].get("position_margin", 0.0),
            "frozen": e["account"].get("frozen", 0.0),
            "position_count": len(e["positions"]),
            "error": e["account"].get("error"),
        }
        for e in per_account
    ]

    agg_account = {
        "equity": sum(s["equity"] for s in account_summaries),
        "available": sum(s["available"] for s in account_summaries),
        "cash": sum(s["cash"] for s in account_summaries),  # sum of cashBalances — actual MEXC wallet balance
        "position_margin": sum(s["position_margin"] for s in account_summaries),
        "unrealized": sum(s["unrealized"] for s in account_summaries),
        "frozen": sum(s["frozen"] for s in account_summaries),
    }

    return JSONResponse(
        {
            "ts": int(time.time() * 1000),
            "latency_ms": int((time.time() - started) * 1000),
            "selected_account_ids": [a.id for a in selected],
            "accounts": account_summaries,
            "account": agg_account,
            "totals": {
                "pnl_unrealized": round(total_pnl_unrealized, 4),
                "pnl_realised": round(total_pnl_realised, 4),
                "pnl_net": round(total_pnl_unrealized + total_pnl_realised, 4),
                "margin": round(total_margin, 4),
                "notional": round(total_notional, 4),
                "pos_count": len(all_positions),
            },
            "positions": all_positions,
        }
    )


# ─── Accounts CRUD ──────────────────────────────────────────────

class AccountIn(BaseModel):
    id: str = Field(min_length=1, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=60)
    color: str = "violet"
    category: str = "utama"
    access_key: str = Field(min_length=4)
    secret_key: str = Field(min_length=4)
    strategy: dict | None = None


class AccountPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    color: str | None = None
    category: str | None = None
    access_key: str | None = Field(default=None, min_length=4)
    secret_key: str | None = Field(default=None, min_length=4)
    strategy: dict | None = None


def _validate_color(c: str) -> str:
    return c if c in ALLOWED_COLORS else "violet"


def _test_connection(access_key: str, secret_key: str) -> dict:
    """Lightweight credential check: call /asset USDT via temp client."""
    base = MexcSettings.from_env()
    test_settings = MexcSettings(
        access_key=access_key,
        secret_key=secret_key,
        base_url=base.base_url,
        recv_window=base.recv_window,
        use_doh_dns=base.use_doh_dns,
        doh_url=base.doh_url,
        live_trading_enabled=False,
        live_confirm="",
        live_mutation_phase_enabled=False,
        state_db=base.state_db,
        strategy_allowed_sides=base.strategy_allowed_sides,
    )
    test_client = MexcFuturesClient(test_settings)
    try:
        resp = test_client.asset("USDT")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {str(e)[:200]}")
    if not isinstance(resp, dict) or not resp.get("success"):
        msg = resp.get("message") if isinstance(resp, dict) else str(resp)
        raise HTTPException(status_code=400, detail=f"MEXC rejected credentials: {msg}")
    data = resp.get("data", {}) or {}
    return {
        "success": True,
        "equity": float(data.get("equity") or 0),
        "available": float(data.get("availableBalance") or 0),
    }


@app.post("/api/accounts/test")
def test_account(creds: dict):
    """Validate credentials without saving."""
    ak = creds.get("access_key")
    sk = creds.get("secret_key")
    if not ak or not sk:
        raise HTTPException(status_code=400, detail="access_key and secret_key required")
    return _test_connection(ak, sk)


@app.post("/api/accounts")
def create_account(payload: AccountIn):
    existing = _read_accounts_file()
    if any(a.get("id") == payload.id for a in existing):
        raise HTTPException(status_code=409, detail=f"Account id '{payload.id}' already exists")
    # Validate credentials work before saving
    try:
        _test_connection(payload.access_key, payload.secret_key)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {e}")
    new_entry = {
        "id": payload.id,
        "name": payload.name,
        "color": _validate_color(payload.color),
        "category": (payload.category or "utama").strip() or "utama",
        "access_key": payload.access_key,
        "secret_key": payload.secret_key,
    }
    existing.append(new_entry)
    _write_accounts_file(existing)
    _reload_account_manager()
    return {"ok": True, "id": payload.id}


@app.patch("/api/accounts/{account_id}")
def update_account(account_id: str, payload: AccountPatch):
    existing = _read_accounts_file()
    found = None
    for a in existing:
        if a.get("id") == account_id:
            found = a
            break
    if not found:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")
    if payload.name is not None:
        found["name"] = payload.name
    if payload.color is not None:
        found["color"] = _validate_color(payload.color)
    if payload.category is not None:
        found["category"] = payload.category.strip() or "utama"
    if payload.access_key is not None or payload.secret_key is not None:
        new_ak = payload.access_key or found["access_key"]
        new_sk = payload.secret_key or found["secret_key"]
        _test_connection(new_ak, new_sk)  # validate
        found["access_key"] = new_ak
        found["secret_key"] = new_sk
    _write_accounts_file(existing)
    _reload_account_manager()
    return {"ok": True, "id": account_id}


class RenameIdPayload(BaseModel):
    new_id: str = Field(min_length=1, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")


@app.post("/api/accounts/{account_id}/rename-id")
def rename_account_id(account_id: str, payload: RenameIdPayload):
    """Change account's primary ID (validate uniqueness)."""
    existing = _read_accounts_file()
    if payload.new_id == account_id:
        return {"ok": True, "id": account_id, "noop": True}
    if any(a.get("id") == payload.new_id for a in existing):
        raise HTTPException(status_code=409, detail=f"ID '{payload.new_id}' already exists")
    found = False
    for a in existing:
        if a.get("id") == account_id:
            a["id"] = payload.new_id
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")
    _write_accounts_file(existing)
    _reload_account_manager()
    return {"ok": True, "old_id": account_id, "new_id": payload.new_id}


class CategoryRenamePayload(BaseModel):
    old_name: str = Field(min_length=1, max_length=40)
    new_name: str = Field(min_length=1, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")


@app.post("/api/categories/rename")
def rename_category(payload: CategoryRenamePayload):
    """Bulk rename category across all accounts using it."""
    existing = _read_accounts_file()
    if payload.old_name == payload.new_name:
        return {"ok": True, "noop": True}
    updated = 0
    for a in existing:
        if a.get("category") == payload.old_name:
            a["category"] = payload.new_name
            updated += 1
    if updated == 0:
        raise HTTPException(status_code=404, detail=f"Category '{payload.old_name}' not in use")
    _write_accounts_file(existing)
    _reload_account_manager()
    return {"ok": True, "old": payload.old_name, "new": payload.new_name, "updated": updated}


@app.delete("/api/accounts/{account_id}")
def delete_account(account_id: str):
    existing = _read_accounts_file()
    new_list = [a for a in existing if a.get("id") != account_id]
    if len(new_list) == len(existing):
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found")
    if not new_list:
        raise HTTPException(status_code=400, detail="Cannot delete the last account")
    _write_accounts_file(new_list)
    _reload_account_manager()
    return {"ok": True, "id": account_id, "remaining": len(new_list)}


# Mount built React assets (must be after all /api routes).
if (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{full_path:path}")
def spa_catchall(full_path: str):
    if full_path.startswith("api"):
        return JSONResponse({"detail": "not found"}, status_code=404)
    spa_index = DIST / "index.html"
    if spa_index.exists():
        return FileResponse(spa_index, headers=_NO_CACHE_HEADERS)
    return JSONResponse({"detail": "spa not built"}, status_code=404)


if __name__ == "__main__":
    import uvicorn

    print(f"Loaded {len(ACCOUNTS)} account(s): {[a.id for a in ACCOUNTS]}")
    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="warning")
