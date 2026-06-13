"""Self-contained PAPER trading bot.

Simulates entries / take-profit / stop-loss on a DUMMY balance using live market
prices. NO real orders are ever sent to MEXC — this is pure mark-to-market
simulation, safe to run while live trading stays locked.

Strategy (mean-reversion, transparent on purpose):
  - Candidates carry a `bias` derived from where price sits in its recent range.
  - bias "long"  (price near range bottom) -> open LONG, target the "normal" price.
  - bias "short" (price near range top)    -> open SHORT, target the "normal" price.
  - Each position has a fixed-% stop-loss and a liquidation guard.

server.py owns market data + the background thread; this module is pure logic +
state so it stays testable and free of network/import coupling.
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

FEE_RATE = 0.0004  # 0.04% taker per side (exits) — realistic drag so PnL isn't fantasy
MAKER_FEE_RATE = 0.0  # limit entry at S/R is a maker order (~0 fee on MEXC)
DEFAULT_START_BALANCE = 100.0


@dataclass
class PaperPosition:
    id: int
    symbol: str
    coin: str
    side: str  # "LONG" | "SHORT"
    entry: float
    qty: float          # coin units
    margin: float       # collateral committed (returned on close)
    leverage: float
    tp: float
    sl: float
    entry_fee: float
    opened_ms: int
    icon_url: str | None = None
    mark: float = 0.0
    trailed: bool = False  # True once SL ratcheted into profit (breakeven/trail)

    @property
    def notional(self) -> float:
        return self.qty * self.entry

    def upnl(self, price: float) -> float:
        if self.side == "LONG":
            return (price - self.entry) * self.qty
        return (self.entry - price) * self.qty


@dataclass
class ClosedTrade:
    id: int
    symbol: str
    coin: str
    side: str
    entry: float
    exit: float
    qty: float
    pnl: float          # net of entry + exit fees
    fee: float
    reason: str         # "TP" | "TRAIL" | "SL" | "LIQ" | "timeout" | "manual"
    opened_ms: int
    closed_ms: int
    icon_url: str | None = None


@dataclass
class PendingOrder:
    """A resting LIMIT order waiting for price to reach its level."""
    id: int
    symbol: str
    coin: str
    side: str  # "LONG" | "SHORT"
    limit_price: float
    tp: float
    sl: float
    created_ms: int
    icon_url: str | None = None


class PaperBot:
    def __init__(self, state_path: Path):
        self.lock = threading.RLock()
        self.state_path = Path(state_path)
        self.running = True  # auto-run on a fresh install so the demo is live
        self.start_balance = DEFAULT_START_BALANCE
        self.cash = DEFAULT_START_BALANCE
        self.positions: list[PaperPosition] = []
        self.closed: list[ClosedTrade] = []
        self.equity_curve: list[list[float]] = []  # [[ts_ms, equity], ...]
        self._next_id = 1
        # --- config (fast scalper: quick TP, tight SL, short holds) ---
        self.max_positions = 6
        self.margin_fraction = 0.08   # fallback if margin_per_trade <= 0
        self.margin_per_trade = 8.0   # max $ modal per entry (cap; user-configurable)
        self.risk_pct = 0.03          # cap loss-at-SL to 3% of equity per trade (0 = off)
        self.leverage = 50.0          # high leverage: small price moves -> big PnL swings
        self.roi_take_profit = 0.8    # bank profit when uPnL >= 80% of margin (0 = off)
        self.signal_min_score = 55    # min confluence score to enter (higher = stricter/rarer)
        self.tp_pct = 0.005           # fallback only — scalp signal supplies ATR-based TP
        self.sl_pct = 0.012           # fallback only — scalp signal supplies ATR-based SL
        self.max_hold_ms = 6 * 3600 * 1000  # confluence = swing-ish; give it room (6h backstop)
        self.be_trigger = 0.35        # lock profit earlier — once >=35% of the way to TP
        self.trail_lock = 0.6         # lock 60% of the favorable move (protect winners)
        self.pending: list[PendingOrder] = []
        self.pending_ttl_ms = 5 * 60 * 1000  # cancel resting limit if unfilled after 5 min
        self._load()

    # ───────── equity ─────────
    def equity(self, prices: dict) -> float:
        eq = self.cash
        for p in self.positions:
            px = prices.get(p.symbol) or p.mark or p.entry
            eq += p.margin + p.upnl(px)
        return eq

    # ───────── lifecycle ─────────
    def start(self) -> None:
        with self.lock:
            self.running = True
            self._save()

    def stop(self) -> None:
        with self.lock:
            self.running = False
            self._save()

    def reset(self, balance: float | None = None) -> None:
        with self.lock:
            self.start_balance = float(balance) if balance else DEFAULT_START_BALANCE
            self.cash = self.start_balance
            self.positions.clear()
            self.closed.clear()
            self.pending.clear()
            self.equity_curve.clear()
            self._next_id = 1
            self._save()

    def update_config(self, **kw) -> None:
        with self.lock:
            if kw.get("max_positions") is not None:
                self.max_positions = max(1, min(int(kw["max_positions"]), 20))
            if kw.get("margin_per_trade") is not None:
                self.margin_per_trade = max(0.0, float(kw["margin_per_trade"]))
            if kw.get("leverage") is not None:
                self.leverage = max(1.0, min(float(kw["leverage"]), 125.0))
            if kw.get("roi_take_profit") is not None:
                self.roi_take_profit = max(0.0, min(float(kw["roi_take_profit"]), 50.0))
            if kw.get("risk_pct") is not None:
                self.risk_pct = max(0.0, min(float(kw["risk_pct"]), 0.5))
            if kw.get("signal_min_score") is not None:
                self.signal_min_score = max(0.0, min(float(kw["signal_min_score"]), 100.0))
            self._save()

    def close_position(self, pos_id: int, price: float | None, now_ms: int) -> bool:
        """Manually close a position at the given (or last mark) price."""
        with self.lock:
            for p in self.positions:
                if p.id == pos_id:
                    px = price if (price and price > 0) else (p.mark or p.entry)
                    self._close(p, px, "manual", now_ms)
                    self._save()
                    return True
        return False

    # ───────── core tick ─────────
    def tick(self, prices: dict, candidates: list, now_ms: int) -> None:
        """Mark open positions, fire exits, then open new ones if capacity remains."""
        with self.lock:
            if not self.running:
                return

            # 1) mark-to-market + exits
            for p in list(self.positions):
                px = prices.get(p.symbol)
                if not px or px <= 0:
                    continue
                p.mark = px
                # Breakeven + trailing stop: once price covers be_trigger of the way to
                # TP, ratchet SL to lock part of the gain (SL only ever moves favorably).
                tp_dist = abs(p.tp - p.entry)
                move = (px - p.entry) if p.side == "LONG" else (p.entry - px)
                if tp_dist > 0 and move > 0 and (move / tp_dist) >= self.be_trigger:
                    lock = self.trail_lock * move
                    if p.side == "LONG" and p.entry + lock > p.sl:
                        p.sl = p.entry + lock
                        p.trailed = True
                    elif p.side == "SHORT" and p.entry - lock < p.sl:
                        p.sl = p.entry - lock
                        p.trailed = True
                reason = None
                if p.side == "LONG":
                    if px >= p.tp:
                        reason = "TP"
                    elif px <= p.sl:
                        reason = "TRAIL" if p.trailed else "SL"
                else:
                    if px <= p.tp:
                        reason = "TP"
                    elif px >= p.sl:
                        reason = "TRAIL" if p.trailed else "SL"
                # ROI take-profit: bank big greens without waiting for the price TP.
                if reason is None and self.roi_take_profit > 0 and p.upnl(px) >= p.margin * self.roi_take_profit:
                    reason = "ROI"
                if reason is None and p.upnl(px) <= -p.margin:
                    reason = "LIQ"  # loss wiped the margin
                if reason is None and now_ms - p.opened_ms >= self.max_hold_ms:
                    reason = "timeout"
                if reason:
                    self._close(p, px, reason, now_ms)

            # 2) fill / expire resting LIMIT orders
            for o in list(self.pending):
                px = prices.get(o.symbol)
                if px and px > 0:
                    hit = (px <= o.limit_price) if o.side == "LONG" else (px >= o.limit_price)
                    if hit:
                        self.pending.remove(o)
                        self._open_position(
                            o.symbol, o.coin, o.side, o.limit_price, o.tp, o.sl, True, o.icon_url, now_ms
                        )
                        continue
                if now_ms - o.created_ms >= self.pending_ttl_ms:
                    self.pending.remove(o)

            # 3) new entries — market fills now, limit rests at S/R
            committed = {p.symbol for p in self.positions} | {o.symbol for o in self.pending}
            for c in candidates:
                if len(self.positions) + len(self.pending) >= self.max_positions:
                    break
                sym = c.get("symbol")
                if not sym or sym in committed or c.get("bias") not in ("long", "short"):
                    continue
                side = "LONG" if c["bias"] == "long" else "SHORT"
                if c.get("order_type") == "market":
                    ok = self._open_position(
                        sym, str(sym).split("_")[0], side,
                        float(c.get("price") or 0), float(c.get("tp") or 0), float(c.get("sl") or 0),
                        False, c.get("icon_url"), now_ms,
                    )
                else:
                    ok = self._place_limit(c, now_ms)
                if ok:
                    committed.add(sym)

            # 4) equity snapshot
            self.equity_curve.append([now_ms, round(self.equity(prices), 4)])
            if len(self.equity_curve) > 2000:
                self.equity_curve = self.equity_curve[-2000:]
            self._save()

    def _open_position(
        self, symbol, coin, side, entry, tp, sl, is_limit, icon_url, now_ms
    ) -> bool:
        """Open a position. Leak-safe: validate + build BEFORE touching cash."""
        entry = float(entry)
        tp = float(tp)
        sl = float(sl)
        if entry <= 0 or tp <= 0 or sl <= 0:
            return False
        if side == "LONG" and not (sl < entry < tp):
            return False
        if side == "SHORT" and not (tp < entry < sl):
            return False
        # Risk-based sizing: size so that hitting SL loses <= risk_pct of equity.
        sl_frac = abs(entry - sl) / entry if entry else 0.0
        sizing_equity = self.cash + sum(p.margin for p in self.positions)
        if self.risk_pct > 0 and sl_frac > 0:
            margin = (self.risk_pct * sizing_equity / sl_frac) / self.leverage
        else:
            margin = self.margin_per_trade if self.margin_per_trade > 0 else self.cash * self.margin_fraction
        # hard cap by modal-per-trade (if set) and available cash → risk only ever lower
        if self.margin_per_trade > 0:
            margin = min(margin, self.margin_per_trade)
        margin = round(min(margin, self.cash), 4)
        if margin < 0.25:  # allow small sizes for high-ATR coins (risk stays <=3%)
            return False
        notional = margin * self.leverage
        qty = notional / entry
        entry_fee = notional * (MAKER_FEE_RATE if is_limit else FEE_RATE)
        pos = PaperPosition(
            id=self._next_id,
            symbol=symbol,
            coin=coin,
            side=side,
            entry=entry,
            qty=qty,
            margin=margin,
            leverage=self.leverage,
            tp=round(tp, 8),
            sl=round(sl, 8),
            entry_fee=entry_fee,
            opened_ms=now_ms,
            icon_url=icon_url,
            mark=entry,
        )
        self.cash -= margin  # commit collateral only after pos built successfully
        self._next_id += 1
        self.positions.append(pos)
        return True

    def _place_limit(self, c: dict, now_ms: int) -> bool:
        """Place a resting LIMIT order at the S/R level (fills when price reaches it)."""
        side = "LONG" if c["bias"] == "long" else "SHORT"
        limit_price = float(c.get("entry") or c.get("price") or 0)
        tp = float(c.get("tp") or 0)
        sl = float(c.get("sl") or 0)
        if limit_price <= 0 or tp <= 0 or sl <= 0:
            return False
        if side == "LONG" and not (sl < limit_price < tp):
            return False
        if side == "SHORT" and not (tp < limit_price < sl):
            return False
        self.pending.append(
            PendingOrder(
                id=self._next_id,
                symbol=c["symbol"],
                coin=str(c["symbol"]).split("_")[0],
                side=side,
                limit_price=limit_price,
                tp=tp,
                sl=sl,
                created_ms=now_ms,
                icon_url=c.get("icon_url"),
            )
        )
        self._next_id += 1
        return True

    def _close(self, p: PaperPosition, px: float, reason: str, now_ms: int) -> None:
        exit_fee = (p.qty * px) * FEE_RATE
        net = p.upnl(px) - p.entry_fee - exit_fee
        self.cash += p.margin + net
        if self.cash < 0:
            self.cash = 0.0
        self.closed.append(
            ClosedTrade(
                id=p.id,
                symbol=p.symbol,
                coin=p.coin,
                side=p.side,
                entry=p.entry,
                exit=px,
                qty=p.qty,
                pnl=round(net, 4),
                fee=round(p.entry_fee + exit_fee, 6),
                reason=reason,
                opened_ms=p.opened_ms,
                closed_ms=now_ms,
                icon_url=p.icon_url,
            )
        )
        if len(self.closed) > 500:
            self.closed = self.closed[-500:]
        self.positions.remove(p)

    def held_symbols(self) -> list[str]:
        with self.lock:
            return [p.symbol for p in self.positions]

    # ───────── snapshot for API ─────────
    def snapshot(self, market: dict) -> dict:
        """`market`: {symbol: {"price": float, "change24": float|None, "icon_url": str|None}}."""
        with self.lock:
            prices = {s: (m or {}).get("price") for s, m in market.items() if (m or {}).get("price")}
            eq = self.equity(prices)

            open_list = []
            long_count = short_count = 0
            for p in self.positions:
                info = market.get(p.symbol) or {}
                px = info.get("price") or p.mark or p.entry
                up = p.upnl(px)
                # Progress along entry -> TP path (0 = at entry, 100 = TP hit).
                tp_span = (p.tp - p.entry) if p.side == "LONG" else (p.entry - p.tp)
                moved = (px - p.entry) if p.side == "LONG" else (p.entry - px)
                tp_progress = (moved / tp_span * 100) if tp_span else 0.0
                if p.side == "LONG":
                    dist_tp = (p.tp - px) / px * 100 if px else 0.0
                    dist_sl = (px - p.sl) / px * 100 if px else 0.0
                    long_count += 1
                else:
                    dist_tp = (px - p.tp) / px * 100 if px else 0.0
                    dist_sl = (p.sl - px) / px * 100 if px else 0.0
                    short_count += 1
                d = asdict(p)
                d["icon_url"] = p.icon_url or info.get("icon_url")
                d["mark"] = px
                d["upnl"] = round(up, 4)
                d["upnl_pct"] = round(up / p.margin * 100, 2) if p.margin else 0.0
                d["notional"] = round(p.notional, 4)
                d["change_24h_pct"] = info.get("change24")
                d["tp_progress_pct"] = round(tp_progress, 1)
                d["dist_tp_pct"] = round(dist_tp, 2)
                d["dist_sl_pct"] = round(dist_sl, 2)
                # risk = loss-at-SL as % of equity (the "entry ratio")
                risk_amt = p.qty * abs(p.entry - p.sl)
                d["risk_pct"] = round(risk_amt / eq * 100, 2) if eq > 0 else 0.0
                open_list.append(d)

            # ── analytics over closed trades ──
            wins = [t for t in self.closed if t.pnl > 0]
            losses = [t for t in self.closed if t.pnl < 0]
            gross_profit = sum(t.pnl for t in wins)
            gross_loss = sum(t.pnl for t in losses)  # negative
            realized = sum(t.pnl for t in self.closed)
            total_fees = sum(t.fee for t in self.closed) + sum(p.entry_fee for p in self.positions)
            profit_factor = (gross_profit / abs(gross_loss)) if gross_loss < 0 else (
                gross_profit if gross_profit > 0 else 0.0
            )
            pnls = [t.pnl for t in self.closed]

            # ── max drawdown from the equity curve ──
            peak = self.start_balance
            max_dd = 0.0
            for _, val in self.equity_curve:
                if val > peak:
                    peak = val
                if peak > 0:
                    max_dd = max(max_dd, (peak - val) / peak * 100)
            peak_equity = max(peak, eq)
            exposure = (sum(p.margin for p in self.positions) / eq * 100) if eq > 0 else 0.0

            # ── resting limit orders ──
            pending_list = []
            for o in self.pending:
                cur = prices.get(o.symbol) or o.limit_price
                pending_list.append(
                    {
                        "id": o.id,
                        "symbol": o.symbol,
                        "coin": o.coin,
                        "icon_url": o.icon_url,
                        "side": o.side,
                        "limit_price": o.limit_price,
                        "tp": o.tp,
                        "sl": o.sl,
                        "mark": cur,
                        "created_ms": o.created_ms,
                        "dist_pct": round((cur - o.limit_price) / cur * 100, 3) if cur else 0.0,
                    }
                )

            return {
                "running": self.running,
                "start_balance": round(self.start_balance, 2),
                "cash": round(self.cash, 4),
                "equity": round(eq, 4),
                "peak_equity": round(peak_equity, 4),
                "total_pnl": round(eq - self.start_balance, 4),
                "total_pnl_pct": round((eq / self.start_balance - 1) * 100, 2)
                if self.start_balance
                else 0.0,
                "realized_pnl": round(realized, 4),
                "open_count": len(self.positions),
                "long_count": long_count,
                "short_count": short_count,
                "closed_count": len(self.closed),
                "win_count": len(wins),
                "loss_count": len(losses),
                "win_rate": round(len(wins) / len(self.closed) * 100, 1) if self.closed else 0.0,
                "profit_factor": round(profit_factor, 2),
                "gross_profit": round(gross_profit, 4),
                "gross_loss": round(gross_loss, 4),
                "avg_win": round(gross_profit / len(wins), 4) if wins else 0.0,
                "avg_loss": round(gross_loss / len(losses), 4) if losses else 0.0,
                "best_trade": round(max(pnls), 4) if pnls else 0.0,
                "worst_trade": round(min(pnls), 4) if pnls else 0.0,
                "total_fees": round(total_fees, 4),
                "max_drawdown_pct": round(max_dd, 2),
                "exposure_pct": round(exposure, 1),
                "config": {
                    "max_positions": self.max_positions,
                    "margin_fraction": self.margin_fraction,
                    "margin_per_trade": self.margin_per_trade,
                    "risk_pct": self.risk_pct,
                    "leverage": self.leverage,
                    "roi_take_profit": self.roi_take_profit,
                    "signal_min_score": self.signal_min_score,
                    "sl_pct": self.sl_pct,
                    "fee_rate": FEE_RATE,
                },
                "open_count_positions": len(self.positions),
                "pending_count": len(self.pending),
                "positions": open_list,
                "pending": pending_list,
                "closed": [asdict(t) for t in reversed(self.closed[-50:])],
                "equity_curve": self.equity_curve[-300:],
            }

    # ───────── persistence (atomic) ─────────
    def _save(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "running": self.running,
                "start_balance": self.start_balance,
                "cash": self.cash,
                "next_id": self._next_id,
                "positions": [asdict(p) for p in self.positions],
                "pending": [asdict(o) for o in self.pending],
                "closed": [asdict(t) for t in self.closed],
                "equity_curve": self.equity_curve[-2000:],
            }
            tmp = self.state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data))
            tmp.replace(self.state_path)
        except (OSError, TypeError, ValueError):
            pass

    def _load(self) -> None:
        try:
            if not self.state_path.exists():
                return
            data = json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return
        self.running = data.get("running", True)
        self.start_balance = data.get("start_balance", DEFAULT_START_BALANCE)
        self.cash = data.get("cash", self.start_balance)
        self._next_id = data.get("next_id", 1)
        pos_fields = PaperPosition.__dataclass_fields__
        trade_fields = ClosedTrade.__dataclass_fields__
        self.positions = [
            PaperPosition(**{k: v for k, v in p.items() if k in pos_fields})
            for p in data.get("positions", [])
        ]
        self.closed = [
            ClosedTrade(**{k: v for k, v in t.items() if k in trade_fields})
            for t in data.get("closed", [])
        ]
        pend_fields = PendingOrder.__dataclass_fields__
        self.pending = [
            PendingOrder(**{k: v for k, v in o.items() if k in pend_fields})
            for o in data.get("pending", [])
        ]
        self.equity_curve = data.get("equity_curve", [])
