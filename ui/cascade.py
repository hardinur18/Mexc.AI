"""
Cascade Execution Engine — multi-tier DCA pyramid orchestrator.

Strategy: scan signals → user enables cascade (PAPER default) → watchdog polls
price → fills tiers as price visits → places TPs → arms break-even SL after TP1
→ trails SL+ as profit grows → exits on SL or all-TP.

Modes:
  PAPER (default, no real orders, fully simulated PnL)
  LIVE (real MEXC orders — requires explicit toggle per cascade + feature flag)

Persistence: cascades append-only journal at /tmp/mexc_cascades.jsonl
(re-loaded into memory on server restart for open cascades)

Safety:
  - LIVE mode disabled globally unless CASCADE_LIVE_ENABLED=1 env var
  - per-cascade size cap (5% equity default)
  - per-account daily new-cascade cap
  - kill switch endpoint cancels all live cascades
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

CASCADE_JOURNAL = Path("/tmp/mexc_cascade_journal.jsonl")
CASCADE_STATE_FILE = Path("/tmp/mexc_cascade_state.json")
CASCADE_LIVE_ENABLED = os.environ.get("CASCADE_LIVE_ENABLED", "0") == "1"

# Safety limits
MAX_NEW_CASCADES_PER_ACCOUNT_PER_DAY = 8
MAX_TOTAL_SIZE_PCT_EQUITY_PER_CASCADE = 12.0  # sum of all tiers max
MAX_LIVE_CASCADES_ACTIVE_PER_ACCOUNT = 6


class CascadeState(str, Enum):
    PENDING = "pending"
    RADAR_FILLED = "radar_filled"
    U1_FILLED = "u1_filled"
    U2_FILLED = "u2_filled"
    BOOSTER_FILLED = "booster_filled"
    PARTIAL_TP1 = "partial_tp1"
    PARTIAL_TP2 = "partial_tp2"
    TRAILING = "trailing"
    CLOSED_WIN = "closed_win"
    CLOSED_LOSS = "closed_loss"
    CLOSED_BREAKEVEN = "closed_be"
    CANCELLED = "cancelled"
    ERROR = "error"


class CascadeMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


TERMINAL_STATES = {
    CascadeState.CLOSED_WIN,
    CascadeState.CLOSED_LOSS,
    CascadeState.CLOSED_BREAKEVEN,
    CascadeState.CANCELLED,
    CascadeState.ERROR,
}


@dataclass
class TierFill:
    role: str  # radar | main_1 | main_2 | booster
    name: str  # display name
    target_price: float
    size_usdt: float
    lev: int
    filled: bool = False
    fill_price: float | None = None
    fill_ts_ms: int | None = None
    order_id: str | None = None


@dataclass
class TpFill:
    tp_num: int
    target_price: float
    close_pct: int
    filled: bool = False
    fill_ts_ms: int | None = None
    pnl_usdt: float | None = None
    order_id: str | None = None


@dataclass
class Cascade:
    id: str
    symbol: str
    direction: str  # LONG | SHORT
    score: int
    started_ts_ms: int
    state: str  # CascadeState value
    mode: str  # CascadeMode value
    account_id: str
    account_name: str
    tiers: list[dict]  # serialized TierFill
    tps: list[dict]  # serialized TpFill
    sl_price: float
    sl_original: float
    sl_breakeven_armed: bool = False
    sl_trail_armed: bool = False
    sl_reason: str = ""
    weighted_avg_entry: float | None = None
    total_filled_usdt: float = 0.0
    realized_pnl_usdt: float = 0.0
    last_seen_price: float | None = None
    closed_ts_ms: int | None = None
    outcome: str | None = None  # WIN | LOSS | BREAKEVEN | CANCELLED
    notes: list[str] = field(default_factory=list)
    last_event_ts_ms: int = 0


class CascadeOrchestrator:
    """Singleton orchestrator: tracks active cascades, runs watchdog."""

    def __init__(self):
        self.active: dict[str, Cascade] = {}
        self.lock = threading.RLock()
        self.market_price_provider: Callable[[str], float | None] | None = None
        self.account_provider: Callable[[str], Optional[Any]] | None = None
        self.executor_factory: Callable[[Any], "CascadeExecutor"] | None = None
        self._watchdog_thread: threading.Thread | None = None
        self._running = False
        self._tick_interval = 6.0  # 6s — was 3s, reduced to ease rate limit pressure
        self._last_persist_ts = 0.0
        self._load()

    # ───────── Configuration ─────────
    def configure(
        self,
        market_price_provider: Callable[[str], float | None],
        account_provider: Callable[[str], Any],
        executor_factory: Callable[[Any], "CascadeExecutor"],
    ) -> None:
        self.market_price_provider = market_price_provider
        self.account_provider = account_provider
        self.executor_factory = executor_factory

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()

    def stop(self) -> None:
        self._running = False

    # ───────── Public API ─────────
    def create_from_signal(
        self,
        signal: dict,
        account_id: str,
        mode: CascadeMode = CascadeMode.PAPER,
        size_multiplier: float = 1.0,
    ) -> Cascade:
        """Create a cascade from a signal payload + entry_plan."""
        plan = signal.get("entry_plan") or {}
        tiers_data = plan.get("tiers") or []
        tp_ladder = plan.get("tp_ladder") or []
        sl_obj = plan.get("sl_invalidation") or {}
        sl_price = sl_obj.get("price")
        sl_reason = sl_obj.get("reason", "")
        if not tiers_data or sl_price is None or not tp_ladder:
            raise ValueError("signal missing tiers / sl_invalidation / tp_ladder")

        symbol = signal["symbol"]
        direction = signal.get("signal_direction") or signal.get("direction") or "NONE"
        if direction not in ("LONG", "SHORT"):
            raise ValueError(f"invalid direction: {direction}")

        # Safety: total size cap
        total_size_pct = sum(t.get("size_pct_equity", 0) for t in tiers_data) * size_multiplier
        if total_size_pct > MAX_TOTAL_SIZE_PCT_EQUITY_PER_CASCADE:
            raise ValueError(
                f"cascade total size {total_size_pct:.1f}% exceeds cap {MAX_TOTAL_SIZE_PCT_EQUITY_PER_CASCADE}%"
            )

        # Safety: per-account daily cap
        today_count = self._count_cascades_today(account_id)
        if today_count >= MAX_NEW_CASCADES_PER_ACCOUNT_PER_DAY:
            raise ValueError(
                f"account already started {today_count} cascades today (cap {MAX_NEW_CASCADES_PER_ACCOUNT_PER_DAY})"
            )

        # Safety: live mode requires feature flag + active cap
        if mode == CascadeMode.LIVE:
            if not CASCADE_LIVE_ENABLED:
                raise ValueError("LIVE mode disabled (set CASCADE_LIVE_ENABLED=1 to enable)")
            live_active = self._count_live_active(account_id)
            if live_active >= MAX_LIVE_CASCADES_ACTIVE_PER_ACCOUNT:
                raise ValueError(
                    f"account has {live_active} live cascades (cap {MAX_LIVE_CASCADES_ACTIVE_PER_ACCOUNT})"
                )

        # Resolve account + equity
        if self.account_provider is None:
            raise RuntimeError("orchestrator not configured (account_provider)")
        acc = self.account_provider(account_id)
        if acc is None:
            raise ValueError(f"account {account_id} not found")
        equity = float(getattr(acc, "_cached_equity", 0) or 0)
        if equity <= 0:
            raise ValueError(f"account {account_id} equity unavailable")
        account_name = getattr(acc, "name", account_id)

        # Build tiers
        tier_objs: list[dict] = []
        for t in tiers_data:
            size_usdt = (t["size_pct_equity"] * size_multiplier / 100.0) * equity
            tier_objs.append(asdict(TierFill(
                role=t["role"],
                name=t["name"],
                target_price=float(t["price"]),
                size_usdt=round(size_usdt, 4),
                lev=int(t["lev"]),
            )))

        # Build TPs
        tp_objs: list[dict] = []
        for tp in tp_ladder:
            if tp.get("price") is None:
                continue
            tp_objs.append(asdict(TpFill(
                tp_num=int(tp["tp"]),
                target_price=float(tp["price"]),
                close_pct=int(tp.get("close_pct", 33)),
            )))

        cid = uuid.uuid4().hex[:10]
        cascade = Cascade(
            id=cid,
            symbol=symbol,
            direction=direction,
            score=int(signal.get("confluence_score", 0)),
            started_ts_ms=int(time.time() * 1000),
            state=CascadeState.PENDING.value,
            mode=mode.value,
            account_id=account_id,
            account_name=account_name,
            tiers=tier_objs,
            tps=tp_objs,
            sl_price=float(sl_price),
            sl_original=float(sl_price),
            sl_reason=sl_reason,
            last_event_ts_ms=int(time.time() * 1000),
        )

        with self.lock:
            self.active[cid] = cascade
            self._append_journal(cascade, "created")
            self._save_state()
        return cascade

    def cancel(self, cascade_id: str, reason: str = "user_cancel") -> Cascade | None:
        with self.lock:
            c = self.active.get(cascade_id)
            if not c:
                return None
            if CascadeState(c.state) in TERMINAL_STATES:
                return c
            c.state = CascadeState.CANCELLED.value
            c.closed_ts_ms = int(time.time() * 1000)
            c.outcome = "CANCELLED"
            c.notes.append(f"cancelled: {reason}")
            c.last_event_ts_ms = c.closed_ts_ms
            self._append_journal(c, "cancelled")
            self._save_state()
            return c

    def kill_all_live(self) -> int:
        """Emergency: cancel all LIVE cascades, attempt to close open positions."""
        cancelled = 0
        with self.lock:
            for c in list(self.active.values()):
                if c.mode != CascadeMode.LIVE.value:
                    continue
                if CascadeState(c.state) in TERMINAL_STATES:
                    continue
                # Try to close live position
                try:
                    if self.executor_factory and any(t["filled"] for t in c.tiers):
                        acc = self.account_provider(c.account_id) if self.account_provider else None
                        if acc:
                            executor = self.executor_factory(acc)
                            executor.market_close_all(c.symbol, c.direction)
                except Exception as e:
                    c.notes.append(f"kill_switch close failed: {e}")
                self.cancel(c.id, reason="kill_switch")
                cancelled += 1
        return cancelled

    def set_mode(self, cascade_id: str, mode: CascadeMode) -> Cascade | None:
        """Upgrade PAPER → LIVE (or downgrade)."""
        if mode == CascadeMode.LIVE and not CASCADE_LIVE_ENABLED:
            raise ValueError("LIVE mode disabled (set CASCADE_LIVE_ENABLED=1)")
        with self.lock:
            c = self.active.get(cascade_id)
            if not c:
                return None
            if CascadeState(c.state) in TERMINAL_STATES:
                return c
            old = c.mode
            c.mode = mode.value
            c.notes.append(f"mode {old} → {mode.value}")
            c.last_event_ts_ms = int(time.time() * 1000)
            self._append_journal(c, "mode_change")
            self._save_state()
            return c

    def list_active(self) -> list[Cascade]:
        with self.lock:
            return [c for c in self.active.values()
                    if CascadeState(c.state) not in TERMINAL_STATES]

    def list_all(self) -> list[Cascade]:
        with self.lock:
            return list(self.active.values())

    def get(self, cascade_id: str) -> Cascade | None:
        with self.lock:
            return self.active.get(cascade_id)

    # ───────── Watchdog ─────────
    def _watchdog_loop(self) -> None:
        while self._running:
            try:
                self._tick()
            except Exception as e:
                # Don't crash watchdog
                print(f"[cascade] watchdog error: {e}")
            time.sleep(self._tick_interval)

    def _tick(self) -> None:
        if not self.market_price_provider:
            return
        with self.lock:
            cascades = list(self.active.values())
        for c in cascades:
            if CascadeState(c.state) in TERMINAL_STATES:
                continue
            try:
                price = self.market_price_provider(c.symbol)
                if price is None or price <= 0:
                    continue
                c.last_seen_price = price
                self._advance(c, price)
            except Exception as e:
                with self.lock:
                    c.notes.append(f"tick error: {e}")
                    c.last_event_ts_ms = int(time.time() * 1000)

        # Periodic persistence
        now = time.time()
        if now - self._last_persist_ts > 10:
            with self.lock:
                self._save_state()
            self._last_persist_ts = now

    def _advance(self, c: Cascade, price: float) -> None:
        is_long = c.direction == "LONG"

        # 1. Check SL hit (only if some tier filled)
        if any(t["filled"] for t in c.tiers):
            sl_hit = (is_long and price <= c.sl_price) or (not is_long and price >= c.sl_price)
            if sl_hit:
                self._close_cascade(c, price, reason="SL_HIT")
                return

        # 2. Check tier fills (in order)
        for tier_data in c.tiers:
            if tier_data["filled"]:
                continue
            target = tier_data["target_price"]
            should_fill = (
                (is_long and price <= target) or
                (not is_long and price >= target)
            )
            # Radar tier fills at market when state is PENDING (no price check needed)
            if tier_data["role"] == "radar" and CascadeState(c.state) == CascadeState.PENDING:
                should_fill = True
            if should_fill:
                self._fill_tier(c, tier_data, price)

        # 3. Check TP fills
        if any(t["filled"] for t in c.tiers):
            for tp_data in c.tps:
                if tp_data["filled"]:
                    continue
                tp_target = tp_data["target_price"]
                should_take = (
                    (is_long and price >= tp_target) or
                    (not is_long and price <= tp_target)
                )
                if should_take:
                    self._take_profit(c, tp_data, price)

        # 4. Trailing SL+
        self._update_trailing_sl(c, price)

        # 5. If all TPs filled, exit
        if c.tps and all(t["filled"] for t in c.tps):
            self._close_cascade(c, price, reason="ALL_TP")

    def _fill_tier(self, c: Cascade, tier_data: dict, price: float) -> None:
        # Live execution wiring
        order_id = None
        if c.mode == CascadeMode.LIVE.value and CASCADE_LIVE_ENABLED:
            try:
                acc = self.account_provider(c.account_id) if self.account_provider else None
                if acc and self.executor_factory:
                    executor = self.executor_factory(acc)
                    order_id = executor.place_market_entry(
                        c.symbol, c.direction, tier_data["size_usdt"], tier_data["lev"]
                    )
            except Exception as e:
                c.notes.append(f"[LIVE] tier {tier_data['name']} entry FAILED: {e}")
                c.state = CascadeState.ERROR.value
                c.last_event_ts_ms = int(time.time() * 1000)
                self._append_journal(c, "tier_fill_error")
                return

        tier_data["filled"] = True
        tier_data["fill_price"] = price
        tier_data["fill_ts_ms"] = int(time.time() * 1000)
        if order_id:
            tier_data["order_id"] = order_id

        # Update state — only if we're still in pre-TP phase. After TP1+
        # already hit, don't regress to a tier-fill state (preserves info).
        PRE_TP_STATES = {
            CascadeState.PENDING.value,
            CascadeState.RADAR_FILLED.value,
            CascadeState.U1_FILLED.value,
            CascadeState.U2_FILLED.value,
            CascadeState.BOOSTER_FILLED.value,
        }
        if c.state in PRE_TP_STATES:
            role = tier_data["role"]
            state_map = {
                "radar": CascadeState.RADAR_FILLED,
                "main_1": CascadeState.U1_FILLED,
                "main_2": CascadeState.U2_FILLED,
                "booster": CascadeState.BOOSTER_FILLED,
            }
            new_state = state_map.get(role)
            if new_state:
                c.state = new_state.value

        # Recompute weighted avg
        filled = [t for t in c.tiers if t["filled"]]
        total_usdt = sum(t["size_usdt"] for t in filled)
        if total_usdt > 0:
            c.weighted_avg_entry = round(
                sum(t["fill_price"] * t["size_usdt"] for t in filled) / total_usdt, 8
            )
        c.total_filled_usdt = round(total_usdt, 4)

        c.notes.append(f"[{c.mode}] {tier_data['name']} filled @ {price}")
        c.last_event_ts_ms = int(time.time() * 1000)
        self._append_journal(c, "tier_fill")

    def _take_profit(self, c: Cascade, tp_data: dict, price: float) -> None:
        # Live: place close order
        order_id = None
        if c.mode == CascadeMode.LIVE.value and CASCADE_LIVE_ENABLED:
            try:
                acc = self.account_provider(c.account_id) if self.account_provider else None
                if acc and self.executor_factory:
                    executor = self.executor_factory(acc)
                    order_id = executor.partial_close(
                        c.symbol, c.direction, tp_data["close_pct"], c.total_filled_usdt
                    )
            except Exception as e:
                c.notes.append(f"[LIVE] TP{tp_data['tp_num']} close FAILED: {e}")
                # Don't error out — paper-track the TP anyway

        tp_data["filled"] = True
        tp_data["fill_ts_ms"] = int(time.time() * 1000)
        if order_id:
            tp_data["order_id"] = order_id

        # PnL calculation — size-weighted leverage (radar 100x weighs different from utama 50x)
        if c.weighted_avg_entry and c.total_filled_usdt > 0:
            partial_size = c.total_filled_usdt * (tp_data["close_pct"] / 100.0)
            if c.direction == "LONG":
                pct = (price - c.weighted_avg_entry) / c.weighted_avg_entry
            else:
                pct = (c.weighted_avg_entry - price) / c.weighted_avg_entry
            filled_tiers = [t for t in c.tiers if t["filled"]]
            total_size_w = sum(t["size_usdt"] for t in filled_tiers)
            if total_size_w > 0:
                weighted_lev = sum(t["size_usdt"] * t["lev"] for t in filled_tiers) / total_size_w
            else:
                weighted_lev = 0
            pnl_usdt = partial_size * weighted_lev * pct
            tp_data["pnl_usdt"] = round(pnl_usdt, 4)
            c.realized_pnl_usdt = round(c.realized_pnl_usdt + pnl_usdt, 4)

        # State updates
        if tp_data["tp_num"] == 1:
            c.state = CascadeState.PARTIAL_TP1.value
            self._arm_breakeven_sl(c)
        elif tp_data["tp_num"] == 2:
            c.state = CascadeState.PARTIAL_TP2.value

        c.notes.append(f"[{c.mode}] TP{tp_data['tp_num']} hit @ {price}")
        c.last_event_ts_ms = int(time.time() * 1000)
        self._append_journal(c, "tp_hit")

    def _arm_breakeven_sl(self, c: Cascade) -> None:
        if c.sl_breakeven_armed:
            return
        if c.weighted_avg_entry is None:
            return
        # Break-even = weighted avg entry + small buffer (0.1% for fees)
        buffer_pct = 0.001
        if c.direction == "LONG":
            new_sl = c.weighted_avg_entry * (1 + buffer_pct)
        else:
            new_sl = c.weighted_avg_entry * (1 - buffer_pct)
        c.sl_price = round(new_sl, 8)
        c.sl_breakeven_armed = True
        c.notes.append(f"SL armed to break-even @ {c.sl_price}")
        # Live: modify SL
        if c.mode == CascadeMode.LIVE.value and CASCADE_LIVE_ENABLED:
            try:
                acc = self.account_provider(c.account_id) if self.account_provider else None
                if acc and self.executor_factory:
                    self.executor_factory(acc).modify_sl(c.symbol, c.direction, c.sl_price)
            except Exception as e:
                c.notes.append(f"[LIVE] BE-SL modify failed: {e}")

    def _update_trailing_sl(self, c: Cascade, price: float) -> None:
        if not c.sl_breakeven_armed:
            return
        if c.weighted_avg_entry is None:
            return
        # Trail SL to lock in % of unrealized profit
        if c.direction == "LONG":
            profit_pct = ((price - c.weighted_avg_entry) / c.weighted_avg_entry) * 100
        else:
            profit_pct = ((c.weighted_avg_entry - price) / c.weighted_avg_entry) * 100
        if profit_pct < 3:  # need at least 3% to start trailing
            return
        # Trail leaves 40% of profit on the table (locks 60%)
        trail_back_pct = profit_pct * 0.4
        if c.direction == "LONG":
            new_sl = price * (1 - trail_back_pct / 100)
            if new_sl > c.sl_price:
                c.sl_price = round(new_sl, 8)
                c.sl_trail_armed = True
                c.state = CascadeState.TRAILING.value
                c.notes.append(f"SL trail → {c.sl_price} (profit lock {profit_pct - trail_back_pct:.1f}%)")
                if c.mode == CascadeMode.LIVE.value and CASCADE_LIVE_ENABLED:
                    try:
                        acc = self.account_provider(c.account_id) if self.account_provider else None
                        if acc and self.executor_factory:
                            self.executor_factory(acc).modify_sl(c.symbol, c.direction, c.sl_price)
                    except Exception as e:
                        c.notes.append(f"[LIVE] trail SL failed: {e}")
        else:
            new_sl = price * (1 + trail_back_pct / 100)
            if new_sl < c.sl_price:
                c.sl_price = round(new_sl, 8)
                c.sl_trail_armed = True
                c.state = CascadeState.TRAILING.value
                c.notes.append(f"SL trail → {c.sl_price} (profit lock {profit_pct - trail_back_pct:.1f}%)")
                if c.mode == CascadeMode.LIVE.value and CASCADE_LIVE_ENABLED:
                    try:
                        acc = self.account_provider(c.account_id) if self.account_provider else None
                        if acc and self.executor_factory:
                            self.executor_factory(acc).modify_sl(c.symbol, c.direction, c.sl_price)
                    except Exception as e:
                        c.notes.append(f"[LIVE] trail SL failed: {e}")

    def _close_cascade(self, c: Cascade, price: float, reason: str) -> None:
        # Compute final PnL on remaining unfilled-TP portion
        remaining_pct = 100 - sum(tp["close_pct"] for tp in c.tps if tp["filled"])
        if remaining_pct > 0 and c.weighted_avg_entry and c.total_filled_usdt > 0:
            partial_size = c.total_filled_usdt * (remaining_pct / 100.0)
            if c.direction == "LONG":
                pct = (price - c.weighted_avg_entry) / c.weighted_avg_entry
            else:
                pct = (c.weighted_avg_entry - price) / c.weighted_avg_entry
            filled_tiers = [t for t in c.tiers if t["filled"]]
            if filled_tiers:
                total_size_w = sum(t["size_usdt"] for t in filled_tiers)
                if total_size_w > 0:
                    weighted_lev = sum(t["size_usdt"] * t["lev"] for t in filled_tiers) / total_size_w
                    final_pnl = partial_size * weighted_lev * pct
                    c.realized_pnl_usdt = round(c.realized_pnl_usdt + final_pnl, 4)

        # Live: market close any open position
        if c.mode == CascadeMode.LIVE.value and CASCADE_LIVE_ENABLED and any(t["filled"] for t in c.tiers):
            try:
                acc = self.account_provider(c.account_id) if self.account_provider else None
                if acc and self.executor_factory:
                    self.executor_factory(acc).market_close_all(c.symbol, c.direction)
            except Exception as e:
                c.notes.append(f"[LIVE] final close failed: {e}")

        c.closed_ts_ms = int(time.time() * 1000)
        if c.realized_pnl_usdt > 0.01:
            c.state = CascadeState.CLOSED_WIN.value
            c.outcome = "WIN"
        elif c.realized_pnl_usdt < -0.01:
            c.state = CascadeState.CLOSED_LOSS.value
            c.outcome = "LOSS"
        else:
            c.state = CascadeState.CLOSED_BREAKEVEN.value
            c.outcome = "BREAKEVEN"
        c.notes.append(f"[{c.mode}] CLOSED {c.outcome} @ {price} (reason: {reason})")
        c.last_event_ts_ms = c.closed_ts_ms
        self._append_journal(c, "close")
        self._save_state()

    # ───────── Persistence ─────────
    def _append_journal(self, c: Cascade, event: str) -> None:
        try:
            entry = {"event": event, "ts_ms": int(time.time() * 1000), **asdict(c)}
            with CASCADE_JOURNAL.open("a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            pass

    def _save_state(self) -> None:
        try:
            data = {cid: asdict(c) for cid, c in self.active.items()}
            with CASCADE_STATE_FILE.open("w") as f:
                json.dump(data, f, default=str)
        except Exception:
            pass

    def _load(self) -> None:
        if not CASCADE_STATE_FILE.exists():
            return
        try:
            with CASCADE_STATE_FILE.open() as f:
                data = json.load(f)
            for cid, raw in data.items():
                # Re-instantiate dataclass
                try:
                    c = Cascade(**raw)
                    self.active[cid] = c
                except Exception:
                    continue
        except Exception:
            pass

    def _count_cascades_today(self, account_id: str) -> int:
        today_start_ms = int(time.time() // 86400) * 86400 * 1000
        with self.lock:
            return sum(
                1 for c in self.active.values()
                if c.account_id == account_id and c.started_ts_ms >= today_start_ms
            )

    def _count_live_active(self, account_id: str) -> int:
        with self.lock:
            return sum(
                1 for c in self.active.values()
                if c.account_id == account_id
                and c.mode == CascadeMode.LIVE.value
                and CascadeState(c.state) not in TERMINAL_STATES
            )


class CascadeExecutor:
    """Bridge between Cascade orchestrator and MEXC client for LIVE execution.

    All methods no-op when CASCADE_LIVE_ENABLED=0 (default safety).
    When enabled, real MEXC orders are placed. USE WITH CAUTION.

    Order side mapping (MEXC futures):
      OPEN_LONG = 1, CLOSE_SHORT = 2, OPEN_SHORT = 3, CLOSE_LONG = 4
    """

    def __init__(self, account: Any):
        self.account = account
        self.client = getattr(account, "client", None)

    def _contract_size(self, symbol: str) -> float:
        """Fetch contract size from MEXC (cached)."""
        if not self.client:
            return 1.0
        try:
            resp = self.client.contract_detail(symbol)
            data = resp.get("data") if isinstance(resp, dict) else None
            if isinstance(data, list) and data:
                return float(data[0].get("contractSize") or 1)
            elif isinstance(data, dict):
                return float(data.get("contractSize") or 1)
        except Exception:
            pass
        return 1.0

    def _volume_from_usdt(self, symbol: str, size_usdt: float, mark_price: float) -> float:
        """Convert USDT margin × leverage into MEXC contract volume.

        contracts = (size_usdt × leverage) / (mark × contract_size)
        Note: caller passes size_usdt as MARGIN; lev applied separately.
        Here we just compute notional value → contracts.
        """
        if mark_price <= 0:
            return 0
        contract_size = self._contract_size(symbol)
        if contract_size <= 0:
            contract_size = 1.0
        # size_usdt is MARGIN. Notional = margin × lev (lev set in change_leverage).
        # Volume = notional / (mark × contract_size). We pass margin only — MEXC
        # uses change_leverage to scale. So volume = margin / (mark × contract_size).
        # But MEXC place_order takes vol in contracts; we want margin × lev / price / contractSize.
        # Simpler: caller multiplies lev × margin → notional → contracts here.
        return max(0.0001, size_usdt / (mark_price * contract_size))

    def place_market_entry(
        self, symbol: str, direction: str, size_usdt: float, lev: int
    ) -> str | None:
        """Open position via market order. Returns order_id or None.

        size_usdt = margin to commit
        lev = leverage to set
        """
        if not CASCADE_LIVE_ENABLED:
            return None
        if not self.client:
            raise RuntimeError("no MEXC client on account")

        # 1. Set leverage (cross by default, openType=2=cross, 1=isolated)
        try:
            self.client.change_leverage({
                "symbol": symbol,
                "leverage": lev,
                "openType": 2,  # cross
                "positionType": 1 if direction == "LONG" else 2,
            })
        except Exception as e:
            raise RuntimeError(f"change_leverage failed: {e}") from e

        # 2. Get latest mark price for contract conversion
        try:
            tk_resp = self.client.ticker(symbol)
            tk_data = tk_resp.get("data") if isinstance(tk_resp, dict) else None
            mark = float((tk_data or {}).get("fairPrice") or (tk_data or {}).get("lastPrice") or 0)
        except Exception:
            mark = 0
        if mark <= 0:
            raise RuntimeError("could not fetch live mark for size conversion")

        # 3. Compute contract volume (margin × lev / mark / contract_size)
        notional = size_usdt * lev
        volume = self._volume_from_usdt(symbol, notional, mark)
        if volume <= 0:
            raise RuntimeError(f"invalid computed volume {volume}")

        # 4. Place market order
        # side: OPEN_LONG=1, OPEN_SHORT=3
        side = 1 if direction == "LONG" else 3
        try:
            # Use raw _request since OrderRequest model expects different shape.
            # Match MEXC futures /order/create body.
            payload = {
                "symbol": symbol,
                "side": side,
                "type": 5,  # market order
                "vol": volume,
                "openType": 2,  # cross
                "leverage": lev,
                "positionMode": 1,  # hedge mode off (one-way)
            }
            resp = self.client._request("POST", "/api/v1/private/order/create", body=payload, private=True)
            order_id = None
            if isinstance(resp, dict):
                d = resp.get("data") or {}
                order_id = d.get("orderId") or d.get("order_id") or str(d)
            return str(order_id) if order_id else None
        except Exception as e:
            raise RuntimeError(f"place_order failed: {e}") from e

    def partial_close(
        self, symbol: str, direction: str, close_pct: int, total_size_usdt: float
    ) -> str | None:
        """Close % of current open position via market order."""
        if not CASCADE_LIVE_ENABLED:
            return None
        if not self.client:
            return None

        # Get current open position size for this symbol
        try:
            resp = self.client.open_positions(symbol)
            data = resp.get("data") if isinstance(resp, dict) else None
            if not isinstance(data, list):
                return None
            matching = [
                p for p in data
                if p.get("symbol") == symbol and
                ((direction == "LONG" and p.get("positionType") == 1) or
                 (direction == "SHORT" and p.get("positionType") == 2))
            ]
            if not matching:
                return None
            pos = matching[0]
            current_vol = float(pos.get("holdVol") or 0)
        except Exception:
            return None

        close_vol = current_vol * (close_pct / 100.0)
        if close_vol <= 0:
            return None

        # side: CLOSE_LONG=4, CLOSE_SHORT=2
        side = 4 if direction == "LONG" else 2
        try:
            payload = {
                "symbol": symbol,
                "side": side,
                "type": 5,
                "vol": close_vol,
                "openType": 2,
                "positionMode": 1,
            }
            resp = self.client._request("POST", "/api/v1/private/order/create", body=payload, private=True)
            order_id = None
            if isinstance(resp, dict):
                d = resp.get("data") or {}
                order_id = d.get("orderId") or d.get("order_id")
            return str(order_id) if order_id else None
        except Exception:
            return None

    def modify_sl(self, symbol: str, direction: str, new_sl_price: float) -> str | None:
        """Place/replace stop-market order at new SL price.

        Strategy: cancel any existing stop orders for this symbol+direction,
        then place a new stop-market.
        """
        if not CASCADE_LIVE_ENABLED:
            return None
        if not self.client:
            return None
        # Cancel existing stop orders (simplification — could be more targeted)
        try:
            # Fetch current stop orders, cancel matching
            sresp = self.client._request(
                "GET",
                "/api/v1/private/stoporder/list/orders",
                params={"symbol": symbol, "page_num": 1, "page_size": 50},
                private=True,
            )
            sdata = sresp.get("data") if isinstance(sresp, dict) else None
            if isinstance(sdata, dict):
                sdata = sdata.get("resultList") or []
            if isinstance(sdata, list):
                for o in sdata:
                    sid = o.get("id")
                    if sid:
                        try:
                            self.client._request(
                                "POST", "/api/v1/private/stoporder/cancel",
                                body={"id": sid}, private=True,
                            )
                        except Exception:
                            continue
        except Exception:
            pass

        # Place new SL trigger order
        # triggerType: 1=LessEq, 2=GreaterEq (for LONG SL = LessEq, SHORT SL = GreaterEq)
        trigger_type = 1 if direction == "LONG" else 2
        side = 4 if direction == "LONG" else 2  # CLOSE_LONG or CLOSE_SHORT

        try:
            # First fetch current position to know how much to close
            resp = self.client.open_positions(symbol)
            data = resp.get("data") if isinstance(resp, dict) else None
            matching = [
                p for p in (data or [])
                if p.get("symbol") == symbol and
                ((direction == "LONG" and p.get("positionType") == 1) or
                 (direction == "SHORT" and p.get("positionType") == 2))
            ]
            if not matching:
                return None
            vol = float(matching[0].get("holdVol") or 0)
            if vol <= 0:
                return None

            payload = {
                "symbol": symbol,
                "side": side,
                "type": 5,  # market
                "vol": vol,
                "openType": 2,
                "triggerPrice": new_sl_price,
                "triggerType": trigger_type,
                "executeCycle": 1,  # always
                "orderType": 1,  # plan order
            }
            resp = self.client._request(
                "POST", "/api/v1/private/stoporder/place", body=payload, private=True,
            )
            d = resp.get("data") if isinstance(resp, dict) else None
            return str((d or {}).get("orderId") or "")
        except Exception:
            return None

    def market_close_all(self, symbol: str, direction: str) -> str | None:
        """Emergency close all position for symbol+direction at market."""
        return self.partial_close(symbol, direction, 100, 0)


# Module-level singleton
ORCHESTRATOR = CascadeOrchestrator()


def list_journal_entries(limit: int = 200) -> list[dict]:
    """Read recent journal events."""
    if not CASCADE_JOURNAL.exists():
        return []
    try:
        with CASCADE_JOURNAL.open() as f:
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


def compute_performance_metrics(limit: int = 500) -> dict:
    """Aggregate metrics from journal close events."""
    journal = list_journal_entries(limit * 5)
    closed = [e for e in journal if e.get("event") == "close"]
    if not closed:
        return {
            "total_trades": 0,
            "win_rate": None,
            "expectancy_usdt": None,
            "total_pnl": 0,
            "max_drawdown_pct": None,
            "sharpe": None,
            "sortino": None,
            "calmar": None,
            "avg_win_usdt": 0,
            "avg_loss_usdt": 0,
            "best_trade": None,
            "worst_trade": None,
            "by_direction": {},
            "by_pattern": {},
        }

    pnls = [float(c.get("realized_pnl_usdt", 0)) for c in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    n = len(pnls)
    win_rate = len(wins) / n * 100 if n else 0
    total_pnl = sum(pnls)
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    expectancy = total_pnl / n if n else 0

    # Equity curve + max drawdown
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    curve = []
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)
        curve.append(round(equity, 4))

    # Sharpe / Sortino approximations (per-trade, not annualized)
    import statistics
    mean = statistics.mean(pnls) if pnls else 0
    sharpe = None
    sortino = None
    if len(pnls) > 2:
        stdev = statistics.stdev(pnls)
        if stdev > 0:
            sharpe = round(mean / stdev * (len(pnls) ** 0.5), 3)
        downside = [p for p in pnls if p < 0]
        if len(downside) > 1:
            dstd = statistics.stdev(downside)
            if dstd > 0:
                sortino = round(mean / dstd * (len(pnls) ** 0.5), 3)
    calmar = None
    if max_dd > 0:
        calmar = round(total_pnl / max_dd, 3)

    # Breakdowns
    by_direction = {"LONG": {"wins": 0, "losses": 0, "pnl": 0.0},
                    "SHORT": {"wins": 0, "losses": 0, "pnl": 0.0}}
    for c in closed:
        d = c.get("direction")
        if d not in by_direction:
            continue
        p = float(c.get("realized_pnl_usdt", 0))
        by_direction[d]["pnl"] += p
        if p > 0:
            by_direction[d]["wins"] += 1
        elif p < 0:
            by_direction[d]["losses"] += 1
    for d in by_direction:
        by_direction[d]["pnl"] = round(by_direction[d]["pnl"], 4)
        total = by_direction[d]["wins"] + by_direction[d]["losses"]
        by_direction[d]["win_rate"] = round(by_direction[d]["wins"] / total * 100, 1) if total > 0 else 0

    return {
        "total_trades": n,
        "win_rate": round(win_rate, 2),
        "expectancy_usdt": round(expectancy, 4),
        "total_pnl": round(total_pnl, 4),
        "max_drawdown_pct": round(max_dd, 3),
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "avg_win_usdt": round(avg_win, 4),
        "avg_loss_usdt": round(avg_loss, 4),
        "best_trade": round(max(pnls), 4) if pnls else None,
        "worst_trade": round(min(pnls), 4) if pnls else None,
        "equity_curve": curve[-100:],
        "by_direction": by_direction,
    }
