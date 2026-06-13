import { useState, type ReactNode } from "react";
import { motion } from "motion/react";
import { useQueryClient } from "@tanstack/react-query";
import { Play, Square, RotateCcw, TrendingUp, TrendingDown, Loader2, Lock, X, Settings } from "lucide-react";
import { usePaperBot } from "@/hooks/useSnapshot";
import {
  paperBotAction,
  resetPaperBot,
  updatePaperBotConfig,
  closePaperBotPosition,
  type PaperBotConfigUpdate,
} from "@/lib/api";
import type { PaperBotState } from "@/types/position";
import type { BotClosedTrade } from "@/types/position";
import { CoinIcon } from "@/components/ui/CoinIcon";
import { Sparkline } from "@/components/positions/Sparkline";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { fmt, fmtPct, fmtPrice } from "@/lib/format";
import { cn } from "@/lib/cn";

function money(n: number | null | undefined, signed = false): string {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = signed ? (n > 0 ? "+" : n < 0 ? "-" : "") : n < 0 ? "-" : "";
  return `${sign}$${fmt(Math.abs(n), 2)}`;
}

function tone(n: number): string {
  if (n > 0) return "text-[var(--color-success)]";
  if (n < 0) return "text-[var(--color-danger)]";
  return "text-[var(--color-fg-muted)]";
}

function fmtAge(openedMs: number): string {
  const s = Math.max(0, Math.floor((Date.now() - openedMs) / 1000));
  if (s < 60) return `${s}d`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}j ${m % 60}m`;
  return `${Math.floor(h / 24)}h ${h % 24}j`;
}

function fmtClock(ms: number): string {
  const d = new Date(ms);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

const REASON_META: Record<BotClosedTrade["reason"], { label: string; cls: string }> = {
  TP: { label: "TP", cls: "bg-[var(--color-success-soft)] text-[var(--color-success)]" },
  ROI: { label: "ROI✓", cls: "bg-[var(--color-success-soft)] text-[var(--color-success)]" },
  TRAIL: { label: "TRAIL+", cls: "bg-[var(--color-success-soft)] text-[var(--color-success)]" },
  SL: { label: "SL", cls: "bg-[var(--color-danger-soft)] text-[var(--color-danger)]" },
  LIQ: { label: "LIKUIDASI", cls: "bg-[var(--color-danger-soft)] text-[var(--color-danger)]" },
  timeout: { label: "TIMEOUT", cls: "bg-[var(--color-bg-elev-2)] text-[var(--color-fg-muted)]" },
  manual: { label: "MANUAL", cls: "bg-[var(--color-bg-elev-2)] text-[var(--color-fg-muted)]" },
};

function SideBadge({ side }: { side: "LONG" | "SHORT" }) {
  const long = side === "LONG";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 rounded-[var(--radius-sm)] px-1.5 py-0.5 text-[10px] font-bold",
        long
          ? "bg-[var(--color-success-soft)] text-[var(--color-success)]"
          : "bg-[var(--color-danger-soft)] text-[var(--color-danger)]",
      )}
    >
      {long ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
      {side}
    </span>
  );
}

function StatCard({
  label,
  value,
  valueClass,
  sub,
}: {
  label: string;
  value: ReactNode;
  valueClass?: string;
  sub?: string;
}) {
  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-elev)] p-3">
      <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-fg-faint)]">
        {label}
      </div>
      <div className={cn("mt-1 text-lg font-bold tabular-nums", valueClass)}>{value}</div>
      {sub && <div className="text-[11px] tabular-nums text-[var(--color-fg-faint)]">{sub}</div>}
    </div>
  );
}

/** Compact metric chip for the analytics strip. */
function Metric({ label, value, valueClass }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="flex flex-col rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-bg-elev)] px-2.5 py-1.5">
      <span className="text-[9px] font-bold uppercase tracking-wider text-[var(--color-fg-faint)]">
        {label}
      </span>
      <span className={cn("text-[13px] font-semibold tabular-nums", valueClass)}>{value}</span>
    </div>
  );
}

/** Mini progress bar showing how close price is to TP (entry→TP path). */
function TpProgress({ pct }: { pct: number }) {
  const clamped = Math.max(0, Math.min(100, pct));
  const color = pct < 0 ? "var(--color-danger)" : "var(--color-success)";
  return (
    <div className="flex items-center justify-end gap-1.5">
      <div className="relative h-1.5 w-14 overflow-hidden rounded-full bg-[var(--color-bg-elev-2)] ring-1 ring-[var(--color-border)]">
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-500"
          style={{ width: `${clamped}%`, background: color }}
        />
      </div>
      <span className="w-8 text-right text-[10px] tabular-nums text-[var(--color-fg-faint)]">
        {Math.round(pct)}%
      </span>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-[9px] font-bold uppercase tracking-wider text-[var(--color-fg-faint)]">{label}</span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-8 w-24 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-bg-elev-2)] px-2 text-xs font-medium tabular-nums text-[var(--color-fg)]"
      />
    </label>
  );
}

function SettingsForm({
  cfg,
  onSave,
  busy,
}: {
  cfg: PaperBotState["config"];
  onSave: (u: PaperBotConfigUpdate) => void;
  busy: boolean;
}) {
  const [maxPos, setMaxPos] = useState(cfg.max_positions);
  const [modal, setModal] = useState(cfg.margin_per_trade);
  const [lev, setLev] = useState(cfg.leverage);
  const [roi, setRoi] = useState(Math.round(cfg.roi_take_profit * 100));
  const [risk, setRisk] = useState(Math.round(cfg.risk_pct * 100 * 10) / 10);
  const [minScore, setMinScore] = useState(Math.round(cfg.signal_min_score));

  function save() {
    onSave({
      max_positions: maxPos,
      margin_per_trade: modal,
      leverage: lev,
      roi_take_profit: roi / 100,
      risk_pct: risk / 100,
      signal_min_score: minScore,
    });
  }

  return (
    <div className="flex flex-wrap items-end gap-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-elev)] p-3">
      <div className="flex items-center gap-1.5 self-center text-[11px] font-bold uppercase tracking-wider text-[var(--color-fg-faint)]">
        <Settings size={13} /> Pengaturan Bot
      </div>
      <Field label="Maks Posisi" value={maxPos} onChange={setMaxPos} min={1} max={20} />
      <Field label="Skor Min Entry" value={minScore} onChange={setMinScore} min={0} max={100} step={1} />
      <Field label="Risk/Entry %" value={risk} onChange={setRisk} min={0} max={20} step={0.5} />
      <Field label="Maks Modal/Entry $" value={modal} onChange={setModal} min={1} step={1} />
      <Field label="Leverage" value={lev} onChange={setLev} min={1} max={125} />
      <Field label="Target Profit %" value={roi} onChange={setRoi} min={0} step={10} />
      <button
        type="button"
        disabled={busy}
        onClick={save}
        className="h-8 rounded-[var(--radius-sm)] bg-[var(--color-accent)] px-3 text-xs font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
      >
        Simpan
      </button>
      <span className="self-center text-[10px] text-[var(--color-fg-faint)]">
        Risk/Entry = rugi maks per posisi (% ekuitas) · Target Profit = auto-tutup saat cuan ≥ % modal
      </span>
    </div>
  );
}

export function PaperBotPanel() {
  const { data, isLoading, isError } = usePaperBot();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);

  async function act(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ["paperbot"] });
    } finally {
      setBusy(false);
    }
  }

  if (isLoading && !data) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-16 animate-pulse rounded-[var(--radius-md)] bg-[var(--color-bg-elev-2)]" />
        ))}
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div className="glass m-4 rounded-xl p-10 text-center text-[13px] text-[var(--color-danger)]">
        Gagal memuat bot dari /api/paperbot/state
      </div>
    );
  }

  const curve = data.equity_curve ?? [];

  return (
    <div className="space-y-4 p-3 md:p-4">
      {/* Header: status + controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider",
              data.running
                ? "bg-[var(--color-success-soft)] text-[var(--color-success)]"
                : "bg-[var(--color-bg-elev-2)] text-[var(--color-fg-muted)]",
            )}
          >
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                data.running ? "bg-[var(--color-success)] animate-pulse" : "bg-[var(--color-fg-muted)]",
              )}
            />
            {data.running ? "Bot Aktif" : "Bot Pause"}
          </span>
          <span className="text-[11px] text-[var(--color-fg-faint)]">
            Saldo dummy · simulasi · tanpa order asli
          </span>
          <span className="hidden items-center gap-1 text-[11px] text-[var(--color-success)] sm:inline-flex">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-success)] animate-pulse" />
            live
          </span>
        </div>
        <div className="flex items-center gap-2">
          {busy && <Loader2 size={14} className="animate-spin text-[var(--color-fg-faint)]" />}
          {data.running ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => act(() => paperBotAction("stop"))}
              className="inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-bg-elev-2)] px-3 text-xs font-semibold text-[var(--color-fg)] transition hover:border-[var(--color-border-strong)] disabled:opacity-50"
            >
              <Square size={12} /> Pause
            </button>
          ) : (
            <button
              type="button"
              disabled={busy}
              onClick={() => act(() => paperBotAction("start"))}
              className="inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-sm)] bg-[var(--color-success)] px-3 text-xs font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
            >
              <Play size={12} /> Mulai
            </button>
          )}
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              if (window.confirm("Reset bot ke saldo $100? Semua posisi & riwayat dummy dihapus.")) {
                act(() => resetPaperBot(100));
              }
            }}
            className="inline-flex h-8 items-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-bg-elev-2)] px-3 text-xs font-semibold text-[var(--color-fg-subtle)] transition hover:text-[var(--color-fg)] disabled:opacity-50"
          >
            <RotateCcw size={12} /> Reset $100
          </button>
        </div>
      </div>

      {/* Settings */}
      <SettingsForm
        key={`${data.config.max_positions}-${data.config.margin_per_trade}-${data.config.leverage}-${data.config.roi_take_profit}-${data.config.risk_pct}-${data.config.signal_min_score}`}
        cfg={data.config}
        onSave={(u) => act(() => updatePaperBotConfig(u))}
        busy={busy}
      />

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-6">
        <StatCard
          label="Equity"
          value={<AnimatedNumber value={data.equity} format={(n) => money(n)} />}
          valueClass={tone(data.total_pnl)}
          sub={`puncak ${money(data.peak_equity)}`}
        />
        <StatCard label="Saldo Bebas" value={money(data.cash)} sub={`${data.open_count} posisi terbuka`} />
        <StatCard
          label="Total PnL"
          value={money(data.total_pnl, true)}
          valueClass={tone(data.total_pnl)}
          sub={fmtPct(data.total_pnl_pct)}
        />
        <StatCard
          label="PnL Realisasi"
          value={money(data.realized_pnl, true)}
          valueClass={tone(data.realized_pnl)}
          sub={`${data.closed_count} trade selesai`}
        />
        <StatCard
          label="Win Rate"
          value={`${data.win_rate}%`}
          sub={`${data.win_count}/${data.closed_count} menang`}
        />
        <StatCard
          label="Leverage"
          value={`${data.config.leverage}x`}
          sub={`maks ${data.config.max_positions} posisi`}
        />
      </div>

      {/* Advanced analytics strip */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
        <Metric
          label="Profit Factor"
          value={data.closed_count ? data.profit_factor.toFixed(2) : "—"}
          valueClass={
            data.profit_factor >= 1
              ? "text-[var(--color-success)]"
              : data.profit_factor > 0
                ? "text-[var(--color-danger)]"
                : ""
          }
        />
        <Metric
          label="Max Drawdown"
          value={`-${data.max_drawdown_pct}%`}
          valueClass={data.max_drawdown_pct > 0 ? "text-[var(--color-danger)]" : ""}
        />
        <Metric label="Avg Win" value={money(data.avg_win, true)} valueClass="text-[var(--color-success)]" />
        <Metric label="Avg Loss" value={money(data.avg_loss, true)} valueClass="text-[var(--color-danger)]" />
        <Metric label="Trade Terbaik" value={money(data.best_trade, true)} valueClass="text-[var(--color-success)]" />
        <Metric label="Trade Terburuk" value={money(data.worst_trade, true)} valueClass="text-[var(--color-danger)]" />
        <Metric label="Total Fee" value={money(data.total_fees)} valueClass="text-[var(--color-fg-muted)]" />
        <Metric label="Exposure" value={`${data.exposure_pct}%`} />
      </div>

      {/* Equity curve */}
      <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-elev)] p-3">
        <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-[var(--color-fg-faint)]">
          Kurva Equity
        </div>
        {curve.length >= 2 ? (
          <div className="overflow-x-auto">
            <Sparkline data={curve} width={760} height={70} refPrice={data.start_balance} fill />
          </div>
        ) : (
          <div className="py-6 text-center text-[12px] text-[var(--color-fg-faint)]">
            Mengumpulkan data… kurva muncul setelah beberapa tick.
          </div>
        )}
      </div>

      {/* Open positions */}
      <div>
        <div className="mb-1.5 px-1 text-[11px] font-bold uppercase tracking-wider text-[var(--color-fg-faint)]">
          Posisi Terbuka ({data.open_count})
        </div>
        {data.positions.length === 0 ? (
          <div className="rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] py-6 text-center text-[12px] text-[var(--color-fg-faint)]">
            Belum ada posisi — bot menunggu sinyal entry.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1080px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-left text-[10px] font-bold uppercase tracking-wider text-[var(--color-fg-faint)]">
                  <th className="px-2 py-2">Koin</th>
                  <th className="px-2 py-2">Arah</th>
                  <th className="px-2 py-2 text-right" title="Modal (margin) · ukuran posisi (notional)">Modal $</th>
                  <th className="px-2 py-2 text-right">24 Jam</th>
                  <th className="px-2 py-2 text-right">Entry</th>
                  <th className="px-2 py-2 text-right">Mark</th>
                  <th className="px-2 py-2 text-right">TP</th>
                  <th className="px-2 py-2 text-right" title="Stop loss · ikon gembok = SL sudah dikunci ke profit (trailing)">SL</th>
                  <th className="px-2 py-2 text-right">Menuju TP</th>
                  <th className="px-2 py-2 text-right">uPnL</th>
                  <th className="px-2 py-2 text-right">Umur</th>
                  <th className="px-2 py-2 text-center">Aksi</th>
                </tr>
              </thead>
              <tbody>
                {data.positions.map((p) => (
                  <motion.tr
                    key={p.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="border-b border-[var(--color-border)]/50 hover:bg-[var(--color-bg-elev-2)]/60"
                  >
                    <td className="px-2 py-2">
                      <div className="flex items-center gap-2">
                        <CoinIcon coin={p.coin} iconUrl={p.icon_url} size={22} />
                        <span className="text-[13px] font-semibold text-[var(--color-fg)]">{p.coin}</span>
                      </div>
                    </td>
                    <td className="px-2 py-2">
                      <SideBadge side={p.side} />
                    </td>
                    <td className="px-2 py-2 text-right">
                      <div className="text-xs font-semibold tabular-nums text-[var(--color-fg)]">
                        {money(p.margin)}
                      </div>
                      <div className="text-[10px] tabular-nums text-[var(--color-fg-faint)]">
                        ×{p.leverage} = {money(p.notional)}
                      </div>
                      <div
                        className={cn(
                          "text-[10px] font-semibold tabular-nums",
                          p.risk_pct <= 3 ? "text-[var(--color-success)]" : "text-[var(--color-warning)]",
                        )}
                        title="Rugi maksimum jika kena SL, sebagai % dari ekuitas"
                      >
                        risk {p.risk_pct}%
                      </div>
                    </td>
                    <td className={cn("px-2 py-2 text-right text-xs tabular-nums", tone(p.change_24h_pct ?? 0))}>
                      {fmtPct(p.change_24h_pct)}
                    </td>
                    <td className="px-2 py-2 text-right text-xs tabular-nums text-[var(--color-fg-subtle)]">
                      {fmtPrice(p.entry)}
                    </td>
                    <td className="px-2 py-2 text-right text-xs font-semibold tabular-nums text-[var(--color-fg)]">
                      <AnimatedNumber value={p.mark} format={(n) => fmtPrice(n)} />
                    </td>
                    <td className="px-2 py-2 text-right text-xs tabular-nums text-[var(--color-success)]">
                      {fmtPrice(p.tp)}
                    </td>
                    <td className="px-2 py-2 text-right">
                      <div
                        className={cn(
                          "flex items-center justify-end gap-1 text-xs tabular-nums",
                          p.trailed ? "text-[var(--color-success)]" : "text-[var(--color-danger)]",
                        )}
                        title={p.trailed ? "SL sudah dikunci ke profit (trailing aktif)" : "Stop loss awal"}
                      >
                        {p.trailed && <Lock size={10} />}
                        {fmtPrice(p.sl)}
                      </div>
                      {p.trailed && (
                        <div className="text-[9px] font-bold text-[var(--color-success)]">SL+ terkunci</div>
                      )}
                    </td>
                    <td className="px-2 py-2">
                      <TpProgress pct={p.tp_progress_pct} />
                    </td>
                    <td className={cn("px-2 py-2 text-right text-xs font-semibold tabular-nums", tone(p.upnl))}>
                      {money(p.upnl, true)}
                      <span className="ml-1 text-[10px] opacity-70">({fmtPct(p.upnl_pct)})</span>
                    </td>
                    <td className="px-2 py-2 text-right text-[11px] tabular-nums text-[var(--color-fg-faint)]">
                      {fmtAge(p.opened_ms)}
                    </td>
                    <td className="px-2 py-2 text-center">
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => act(() => closePaperBotPosition(p.id))}
                        title="Tutup posisi sekarang (market)"
                        className="inline-flex h-6 items-center gap-1 rounded-[var(--radius-sm)] border border-[var(--color-danger)]/40 px-1.5 text-[10px] font-bold text-[var(--color-danger)] transition hover:bg-[var(--color-danger-soft)] disabled:opacity-50"
                      >
                        <X size={10} /> Tutup
                      </button>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Closed trades */}
      <div>
        <div className="mb-1.5 px-1 text-[11px] font-bold uppercase tracking-wider text-[var(--color-fg-faint)]">
          Riwayat Trade ({data.closed_count})
        </div>
        {data.closed.length === 0 ? (
          <div className="rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] py-6 text-center text-[12px] text-[var(--color-fg-faint)]">
            Belum ada trade selesai.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-left text-[10px] font-bold uppercase tracking-wider text-[var(--color-fg-faint)]">
                  <th className="px-2 py-2">Koin</th>
                  <th className="px-2 py-2">Arah</th>
                  <th className="px-2 py-2 text-right">Entry</th>
                  <th className="px-2 py-2 text-right">Exit</th>
                  <th className="px-2 py-2 text-right">PnL</th>
                  <th className="px-2 py-2 text-center">Sebab</th>
                  <th className="px-2 py-2 text-right">Waktu</th>
                </tr>
              </thead>
              <tbody>
                {data.closed.map((t) => (
                  <tr
                    key={t.id}
                    className="border-b border-[var(--color-border)]/50 hover:bg-[var(--color-bg-elev-2)]/60"
                  >
                    <td className="px-2 py-2">
                      <div className="flex items-center gap-2">
                        <CoinIcon coin={t.coin} iconUrl={t.icon_url} size={20} />
                        <span className="text-[12px] font-semibold text-[var(--color-fg)]">{t.coin}</span>
                      </div>
                    </td>
                    <td className="px-2 py-2">
                      <SideBadge side={t.side} />
                    </td>
                    <td className="px-2 py-2 text-right text-xs tabular-nums text-[var(--color-fg-subtle)]">
                      {fmtPrice(t.entry)}
                    </td>
                    <td className="px-2 py-2 text-right text-xs tabular-nums text-[var(--color-fg-subtle)]">
                      {fmtPrice(t.exit)}
                    </td>
                    <td className={cn("px-2 py-2 text-right text-xs font-semibold tabular-nums", tone(t.pnl))}>
                      {money(t.pnl, true)}
                    </td>
                    <td className="px-2 py-2 text-center">
                      <span
                        className={cn(
                          "rounded-[var(--radius-sm)] px-1.5 py-0.5 text-[10px] font-bold",
                          REASON_META[t.reason].cls,
                        )}
                      >
                        {REASON_META[t.reason].label}
                      </span>
                    </td>
                    <td className="px-2 py-2 text-right text-[11px] tabular-nums text-[var(--color-fg-faint)]">
                      {fmtClock(t.closed_ms)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="px-1 text-[11px] leading-relaxed text-[var(--color-fg-faint)]">
        ⚠️ Ini bot <b>simulasi (paper)</b> dengan saldo dummy — tidak ada order nyata ke MEXC. Entry pakai
        <b> confluence engine</b> (RSI multi-TF + DMI + divergence + SMC + S/R + orderflow) — cuma masuk saat
        skor konviksi tinggi (≥68) & arah terkonfirmasi multi-timeframe. TP/SL berbasis ATR 4h (R:R ~1.6),
        risk per entry ≤{Math.round(data.config.risk_pct * 100)}%, leverage {data.config.leverage}x,
        fee {(data.config.fee_rate * 100).toFixed(3)}%/sisi. Hasil simulasi bukan jaminan hasil nyata.
      </p>
    </div>
  );
}
