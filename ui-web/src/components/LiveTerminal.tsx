import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import { usePaperBot, useMovers7d } from "@/hooks/useSnapshot";
import { useLivePrices, type LivePrices } from "@/hooks/useLivePrices";
import { useUiStore } from "@/store/ui";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { Sparkline } from "@/components/positions/Sparkline";
import type { Mover7d, BotClosedTrade, BotPosition } from "@/types/position";

const C = {
  bg: "#0a0512",
  panel: "rgba(20,10,30,0.66)",
  border: "rgba(255,45,120,0.22)",
  magenta: "#ff2d78",
  cyan: "#22d3ee",
  green: "#34d399",
  red: "#ff4d6d",
  text: "#ecd9ee",
  muted: "#9a7ba8",
};

function clamp(v: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, v));
}
function money(n: number, signed = false) {
  if (n == null || Number.isNaN(n)) return "—";
  const s = signed ? (n > 0 ? "+" : n < 0 ? "-" : "") : n < 0 ? "-" : "";
  return `${s}$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
function px(n: number) {
  const v = Math.abs(n);
  const dp = v >= 1000 ? 1 : v >= 1 ? 3 : 6;
  return n.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
}
function pct(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
}
function clock(d: Date) {
  return d.toLocaleTimeString("en-GB", { hour12: false });
}
function hms(ms: number) {
  const d = new Date(ms);
  return d.toLocaleTimeString("en-GB", { hour12: false });
}

/* ── neon panel shell ── */
function Panel({
  title,
  accent = C.magenta,
  children,
  className,
}: {
  title?: string;
  accent?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`relative rounded-lg border p-3 ${className ?? ""}`}
      style={{ background: C.panel, borderColor: C.border, boxShadow: `inset 0 0 30px rgba(255,45,120,0.05)` }}
    >
      {title && (
        <div
          className="mb-2 text-[10px] font-bold uppercase tracking-[0.18em]"
          style={{ color: accent, textShadow: `0 0 8px ${accent}66` }}
        >
          ▸ {title}
        </div>
      )}
      {children}
    </div>
  );
}

function biasColor(b: string) {
  return b === "long" ? C.green : b === "short" ? C.magenta : C.cyan;
}

/* ── the animated constellation of coins (entered positions = glowing web) ── */
function NodeMap({ coins, entered }: { coins: Mover7d[]; entered: Set<string> }) {
  const nodes = useMemo(
    () =>
      coins.slice(0, 30).map((m, i) => {
        const x = 5 + ((clamp(m.change_24h_pct ?? 0, -12, 12) + 12) / 24) * 90;
        const y = 10 + (1 - (clamp(m.change_pct, -45, 45) + 45) / 90) * 80;
        const size = clamp(8 + Math.log10((m.volume_24h_usdt ?? 0) + 10) * 2.4, 8, 26);
        const color = biasColor(m.bias);
        const dur = 3.2 + ((i * 37) % 40) / 10;
        const dx = 6 + ((i * 13) % 9);
        const dy = 5 + ((i * 7) % 10);
        return { m, x, y, size, color, dur, dx, dy, i };
      }),
    [coins],
  );
  const hot = nodes.filter((n) => entered.has(n.m.symbol));

  return (
    <div className="relative h-[320px] w-full overflow-hidden rounded-md" style={{ background: "radial-gradient(circle at 50% 50%, rgba(255,45,120,0.05), transparent 70%)" }}>
      {/* grid lines */}
      <div className="pointer-events-none absolute inset-0 opacity-[0.12]" style={{ backgroundImage: `linear-gradient(${C.magenta} 1px, transparent 1px), linear-gradient(90deg, ${C.magenta} 1px, transparent 1px)`, backgroundSize: "48px 48px" }} />
      {/* axis hints */}
      <div className="absolute left-2 top-2 text-[9px]" style={{ color: C.muted }}>↑ naik 7H</div>
      <div className="absolute bottom-2 right-2 text-[9px]" style={{ color: C.muted }}>24J →</div>

      {/* faint relation mesh — each node linked to its nearest neighbour */}
      <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none">
        {nodes.map((a) => {
          let nearest: (typeof nodes)[number] | null = null;
          let best = 1e9;
          for (const b of nodes) {
            if (b === a) continue;
            const d = (a.x - b.x) ** 2 + (a.y - b.y) ** 2;
            if (d < best) {
              best = d;
              nearest = b;
            }
          }
          if (!nearest) return null;
          return (
            <line key={`rel-${a.m.symbol}`} x1={a.x} y1={a.y} x2={nearest.x} y2={nearest.y} stroke={C.magenta} strokeWidth={0.1} opacity={0.13} />
          );
        })}
      </svg>

      {/* correlation web between coins the bot is currently IN */}
      {hot.length >= 2 && (
        <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none">
          {hot.flatMap((a, i) =>
            hot.slice(i + 1).map((b, j) => (
              <motion.line
                key={`${a.m.symbol}-${b.m.symbol}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={C.cyan}
                strokeWidth={0.18}
                animate={{ opacity: [0.12, 0.5, 0.12] }}
                transition={{ duration: 2.6, repeat: Infinity, delay: (i + j) * 0.18 }}
              />
            )),
          )}
        </svg>
      )}

      {nodes.map((n) => {
        const isHot = entered.has(n.m.symbol);
        return (
          <motion.div
            key={n.m.symbol}
            className="absolute -translate-x-1/2 -translate-y-1/2"
            style={{ left: `${n.x}%`, top: `${n.y}%`, zIndex: isHot ? 5 : 1 }}
            animate={{ x: [0, n.dx, 0, -n.dx, 0], y: [0, -n.dy, 0, n.dy, 0] }}
            transition={{ duration: n.dur, repeat: Infinity, ease: "easeInOut" }}
          >
            {/* entered = pulsing ring halo */}
            {isHot && (
              <motion.div
                className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border"
                style={{ borderColor: C.cyan }}
                initial={{ width: n.size, height: n.size, opacity: 0.8 }}
                animate={{ width: n.size * 3, height: n.size * 3, opacity: 0 }}
                transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut" }}
              />
            )}
            <motion.div
              className="rounded-full"
              style={{
                width: n.size,
                height: n.size,
                background: isHot ? C.cyan : n.color,
                boxShadow: `0 0 ${n.size * (isHot ? 1.6 : 1)}px ${isHot ? C.cyan : n.color}, 0 0 ${n.size * 2}px ${isHot ? C.cyan : n.color}55`,
              }}
              animate={{ scale: [1, 1.25, 1], opacity: [0.7, 1, 0.7] }}
              transition={{ duration: 1.6 + (n.i % 5) * 0.3, repeat: Infinity, ease: "easeInOut" }}
            />
            {(n.size > 15 || isHot) && (
              <span className="absolute left-1/2 top-full mt-0.5 -translate-x-1/2 whitespace-nowrap text-[8px] font-bold" style={{ color: isHot ? C.cyan : n.color }}>
                {n.m.coin}
              </span>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}

/* ── scrolling live execution log ── */
function ExecutionLog({
  closed,
  positions,
}: {
  closed: BotClosedTrade[];
  positions: BotPosition[];
}) {
  const ref = useRef<HTMLDivElement>(null);
  const lines = useMemo(() => {
    const evs: { ts: number; text: string; color: string }[] = [];
    for (const p of positions) {
      evs.push({
        ts: p.opened_ms,
        color: p.side === "LONG" ? C.green : C.magenta,
        text: `ENTRY  ${p.coin.padEnd(6)} ${p.side.padEnd(5)} @ ${px(p.entry)}  lev ${p.leverage}x`,
      });
    }
    for (const t of closed) {
      const win = t.pnl >= 0;
      evs.push({
        ts: t.closed_ms,
        color: win ? C.green : C.red,
        text: `${t.reason.padEnd(7)} ${t.coin.padEnd(6)} ${t.side.padEnd(5)} ${px(t.entry)}→${px(t.exit)}  ${money(t.pnl, true)}`,
      });
    }
    evs.sort((a, b) => a.ts - b.ts);
    return evs.slice(-60);
  }, [closed, positions]);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [lines]);

  return (
    <div ref={ref} className="h-[180px] overflow-y-auto pr-1 font-mono text-[11px] leading-relaxed">
      {lines.length === 0 && <div style={{ color: C.muted }}>menunggu sinyal…</div>}
      {lines.map((l, i) => (
        <div key={i} className="flex gap-2 whitespace-nowrap">
          <span style={{ color: C.muted }}>{hms(l.ts)}</span>
          <span style={{ color: l.color }}>{l.text}</span>
        </div>
      ))}
      <div className="flex gap-2" style={{ color: C.cyan }}>
        <span style={{ color: C.muted }}>{clock(new Date())}</span>
        <span>
          {"> scanning market"}
          <motion.span animate={{ opacity: [1, 0, 1] }} transition={{ duration: 1, repeat: Infinity }}>
            ▌
          </motion.span>
        </span>
      </div>
    </div>
  );
}

/* ── scrolling ticker tape (top marquee) ── */
function TickerTape({ coins, live }: { coins: Mover7d[]; live: LivePrices }) {
  const items = coins.slice(0, 24);
  if (items.length === 0) return null;
  const row = (
    <div className="flex shrink-0 items-center gap-6 px-3 py-1.5">
      {items.map((c) => {
        const p = live.get(c.symbol) ?? c.price;
        const up = (c.change_24h_pct ?? 0) >= 0;
        return (
          <span key={c.symbol} className="flex items-center gap-1.5 whitespace-nowrap text-[11px]">
            <span className="font-bold" style={{ color: C.text }}>{c.coin}</span>
            <span style={{ color: C.muted }}>${px(p)}</span>
            <span style={{ color: up ? C.green : C.red }}>{pct(c.change_24h_pct)}</span>
          </span>
        );
      })}
    </div>
  );
  return (
    <div className="relative mb-3 overflow-hidden border-y" style={{ borderColor: C.border, background: "rgba(0,0,0,0.3)" }}>
      <motion.div className="flex w-max" animate={{ x: ["0%", "-50%"] }} transition={{ duration: 45, repeat: Infinity, ease: "linear" }}>
        {row}
        {row}
      </motion.div>
    </div>
  );
}

export function LiveTerminal() {
  const { data: bot } = usePaperBot();
  const { data: movers } = useMovers7d("gainers", "Day1", 14, -100000);
  const live = useLivePrices(600);
  const setActivePage = useUiStore((s) => s.setActivePage);
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const coins = movers?.items ?? [];
  const enteredSyms = new Set((bot?.positions ?? []).map((p) => p.symbol));
  const btc = live.get("BTC_USDT") ?? coins.find((c) => c.symbol === "BTC_USDT")?.price ?? 0;
  const top = coins[0];

  // ticker list with live prices overlaid
  const ticker = coins.slice(0, 14).map((c) => ({
    ...c,
    livePx: live.get(c.symbol) ?? c.price,
  }));

  return (
    <div
      className="fixed inset-0 z-[60] overflow-y-auto font-mono"
      style={{ background: `radial-gradient(circle at 20% 0%, rgba(255,45,120,0.10), transparent 42%), radial-gradient(circle at 90% 100%, rgba(34,211,238,0.07), transparent 42%), ${C.bg}`, color: C.text }}
    >
      {/* CRT scanlines + vignette overlays */}
      <div className="pointer-events-none fixed inset-0 z-[61]" style={{ background: "repeating-linear-gradient(0deg, rgba(0,0,0,0.16) 0px, rgba(0,0,0,0.16) 1px, transparent 1px, transparent 3px)" }} />
      <div className="pointer-events-none fixed inset-0 z-[61]" style={{ background: "radial-gradient(circle at 50% 45%, transparent 52%, rgba(0,0,0,0.6) 100%)" }} />

      <div className="relative z-[62] p-3 md:p-4">
      {/* ── header bar ── */}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border px-3 py-2" style={{ borderColor: C.border, background: C.panel }}>
        <div className="flex items-center gap-3">
          <span className="text-sm font-black tracking-[0.2em]" style={{ color: C.magenta, textShadow: `0 0 14px ${C.magenta}` }}>
            MEXC ⛧ LIVE TERMINAL
          </span>
          <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-bold" style={{ background: live.connected ? "rgba(52,211,153,0.15)" : "rgba(154,123,168,0.15)", color: live.connected ? C.green : C.muted }}>
            <motion.span className="h-1.5 w-1.5 rounded-full" style={{ background: live.connected ? C.green : C.muted }} animate={{ opacity: [1, 0.3, 1] }} transition={{ duration: 1.2, repeat: Infinity }} />
            {live.connected ? `WS LIVE · ${live.count}` : "POLLING"}
          </span>
        </div>
        <div className="flex items-center gap-4 text-[11px]">
          <span style={{ color: C.muted }}>
            BTC <span style={{ color: C.text }}>${px(btc)}</span>
          </span>
          <span style={{ color: C.green }}>▲ {movers?.gainer_count ?? 0}</span>
          <span style={{ color: C.red }}>▼ {movers?.loser_count ?? 0}</span>
          <span className="tabular-nums" style={{ color: C.cyan, textShadow: `0 0 8px ${C.cyan}66` }}>
            {clock(now)}
          </span>
          <button
            type="button"
            onClick={() => setActivePage("dashboard")}
            className="rounded border px-2 py-0.5 text-[10px] font-bold transition hover:opacity-80"
            style={{ borderColor: C.border, color: C.muted }}
          >
            ✕ KELUAR
          </button>
        </div>
      </div>

      {/* ── ticker tape ── */}
      <TickerTape coins={coins} live={live} />

      {/* ── top row ── */}
      <div className="mb-3 grid grid-cols-1 gap-3 lg:grid-cols-3">
        {/* bot card */}
        <Panel title="PAPER_BOT_001" accent={C.magenta}>
          <div className="flex items-center justify-between">
            <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-black" style={{ background: bot?.running ? C.magenta : "#333", color: "#fff" }}>
              <motion.span className="h-1.5 w-1.5 rounded-full bg-white" animate={{ opacity: [1, 0.2, 1] }} transition={{ duration: 1, repeat: Infinity }} />
              {bot?.running ? "LIVE" : "PAUSE"}
            </span>
            <span className="text-[10px]" style={{ color: C.muted }}>
              {bot?.open_count ?? 0} open · {bot?.closed_count ?? 0} trade
            </span>
          </div>
          <div className="mt-2 text-3xl font-black tabular-nums" style={{ color: (bot?.total_pnl ?? 0) >= 0 ? C.green : C.red, textShadow: `0 0 16px ${(bot?.total_pnl ?? 0) >= 0 ? C.green : C.red}66` }}>
            <AnimatedNumber value={bot?.equity ?? 0} format={(n) => money(n)} />
          </div>
          <div className="mt-2 grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-[9px]" style={{ color: C.muted }}>PNL</div>
              <div className="text-xs font-bold" style={{ color: (bot?.total_pnl ?? 0) >= 0 ? C.green : C.red }}>{pct(bot?.total_pnl_pct)}</div>
            </div>
            <div>
              <div className="text-[9px]" style={{ color: C.muted }}>WIN</div>
              <div className="text-xs font-bold" style={{ color: C.cyan }}>{bot?.win_rate ?? 0}%</div>
            </div>
            <div>
              <div className="text-[9px]" style={{ color: C.muted }}>PF</div>
              <div className="text-xs font-bold" style={{ color: C.text }}>{bot?.profit_factor ?? 0}</div>
            </div>
          </div>
        </Panel>

        {/* equity chart */}
        <Panel title="EQUITY · LIVE" accent={C.green}>
          {bot && bot.equity_curve.length >= 2 ? (
            <div className="overflow-hidden">
              <Sparkline data={bot.equity_curve} width={420} height={92} color={C.green} refPrice={bot.start_balance} fill />
            </div>
          ) : (
            <div className="py-8 text-center text-[11px]" style={{ color: C.muted }}>mengumpulkan data…</div>
          )}
          <div className="mt-1 flex justify-between text-[10px]" style={{ color: C.muted }}>
            <span>start {money(bot?.start_balance ?? 100)}</span>
            <span style={{ color: C.green }}>peak {money(bot?.peak_equity ?? 100)}</span>
          </div>
        </Panel>

        {/* top mover + bars */}
        <Panel title="#1 MOVER · STREAK" accent={C.cyan}>
          {top ? (
            <>
              <div className="flex items-center justify-between">
                <span className="text-lg font-black" style={{ color: C.text }}>{top.coin}</span>
                <span className="text-lg font-black tabular-nums" style={{ color: top.change_pct >= 0 ? C.green : C.red, textShadow: `0 0 12px ${top.change_pct >= 0 ? C.green : C.red}66` }}>
                  {pct(top.change_pct)}
                </span>
              </div>
              <div className="mt-2 flex h-12 items-end gap-1">
                {top.periods.map((d, i) => {
                  const v = d.change_pct ?? 0;
                  const h = clamp(Math.abs(v) * 1.6, 3, 48);
                  return (
                    <motion.div
                      key={i}
                      className="flex-1 rounded-sm"
                      style={{ background: v >= 0 ? C.green : C.red, boxShadow: `0 0 6px ${v >= 0 ? C.green : C.red}88` }}
                      initial={{ height: 0 }}
                      animate={{ height: h }}
                      transition={{ duration: 0.5, delay: i * 0.03 }}
                    />
                  );
                })}
              </div>
              <div className="mt-1 text-[10px]" style={{ color: C.muted }}>14 candle harian · vol {money((top.volume_24h_usdt ?? 0) / 1e6)}M</div>
            </>
          ) : (
            <div className="py-8 text-center text-[11px]" style={{ color: C.muted }}>—</div>
          )}
        </Panel>
      </div>

      {/* ── node map ── */}
      <div className="mb-3">
        <Panel title="MARKET MAP · REALTIME" accent={C.magenta}>
          <div className="mb-2 flex gap-3 text-[9px]" style={{ color: C.muted }}>
            <span style={{ color: C.green }}>● LONG bias</span>
            <span style={{ color: C.magenta }}>● SHORT bias</span>
            <span style={{ color: C.cyan }}>● NETRAL</span>
            <span>· ukuran = volume</span>
          </div>
          <NodeMap coins={coins} entered={enteredSyms} />
        </Panel>
      </div>

      {/* ── positions + pending limits ── */}
      <div className="mb-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Panel title={`POSISI AKTIF · ${bot?.open_count ?? 0}`} accent={C.green}>
          {(bot?.positions?.length ?? 0) === 0 ? (
            <div className="py-4 text-center text-[11px]" style={{ color: C.muted }}>belum ada posisi terbuka</div>
          ) : (
            <div className="max-h-[170px] space-y-1 overflow-y-auto">
              {bot!.positions.map((p) => (
                <div key={p.id} className="flex items-center justify-between gap-2 rounded px-2 py-1 text-[11px]" style={{ background: "rgba(255,255,255,0.02)" }}>
                  <span className="flex items-center gap-1.5">
                    <span className="font-bold" style={{ color: C.text }}>{p.coin}</span>
                    <span className="font-bold" style={{ color: p.side === "LONG" ? C.green : C.magenta }}>{p.side}</span>
                    {p.trailed && <span className="font-bold" style={{ color: C.green }}>🔒SL+</span>}
                  </span>
                  <span className="tabular-nums" style={{ color: C.muted }}>
                    {money(p.margin)} ×{p.leverage} · @{px(p.entry)}
                  </span>
                  <span className="w-24 text-right font-bold tabular-nums" style={{ color: p.upnl >= 0 ? C.green : C.red }}>
                    {money(p.upnl, true)} ({pct(p.upnl_pct)})
                  </span>
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel title={`LIMIT PENDING · ${bot?.pending_count ?? 0}`} accent={C.cyan}>
          {(bot?.pending?.length ?? 0) === 0 ? (
            <div className="py-4 text-center text-[11px]" style={{ color: C.muted }}>tidak ada limit menunggu</div>
          ) : (
            <div className="max-h-[170px] space-y-1 overflow-y-auto">
              {bot!.pending.map((o) => (
                <div key={o.id} className="flex items-center justify-between gap-2 rounded px-2 py-1 text-[11px]" style={{ background: "rgba(34,211,238,0.05)" }}>
                  <span className="flex items-center gap-1.5">
                    <span className="font-bold" style={{ color: C.text }}>{o.coin}</span>
                    <span className="font-bold" style={{ color: o.side === "LONG" ? C.green : C.magenta }}>{o.side}</span>
                  </span>
                  <span className="tabular-nums" style={{ color: C.muted }}>limit @ {px(o.limit_price)}</span>
                  <span className="tabular-nums" style={{ color: C.cyan }}>
                    {o.dist_pct > 0 ? "+" : ""}{o.dist_pct}% → fill
                  </span>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      {/* ── bottom row ── */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Panel title="LIVE TICKERS" accent={C.cyan}>
          <div className="max-h-[180px] space-y-0.5 overflow-y-auto text-[11px]">
            {ticker.map((c) => (
              <div key={c.symbol} className="flex items-center justify-between rounded px-1.5 py-1" style={{ background: "rgba(255,255,255,0.02)" }}>
                <span className="font-bold" style={{ color: C.text }}>{c.coin}</span>
                <span className="tabular-nums" style={{ color: C.muted }}>${px(c.livePx)}</span>
                <span className="w-16 text-right font-bold tabular-nums" style={{ color: (c.change_24h_pct ?? 0) >= 0 ? C.green : C.red }}>
                  {pct(c.change_24h_pct)}
                </span>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="EXECUTION LOG · LIVE" accent={C.magenta}>
          <ExecutionLog closed={bot?.closed ?? []} positions={bot?.positions ?? []} />
        </Panel>
      </div>

      <p className="mt-3 text-center text-[10px]" style={{ color: C.muted }}>
        Simulasi paper · saldo dummy · data harga {live.connected ? "real-time WebSocket" : "polling REST"} · bukan saran finansial
      </p>
      </div>
    </div>
  );
}
