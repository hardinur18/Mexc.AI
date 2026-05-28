import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Zap,
  AlertOctagon,
  CheckCircle,
  XCircle,
  Activity,
  ChevronDown,
  ChevronRight,
  Power,
} from "lucide-react";
import { useCascadeActive, useCascadeAll } from "@/hooks/useSnapshot";
import { cancelCascade, killSwitch, setCascadeMode } from "@/lib/api";
import type { Cascade } from "@/types/position";
import { fmt, fmtPrice } from "@/lib/format";
import { toast } from "sonner";
import { cn } from "@/lib/cn";

const STATE_TONE: Record<string, string> = {
  pending: "var(--color-fg-muted)",
  radar_filled: "var(--color-warning)",
  u1_filled: "var(--color-accent)",
  u2_filled: "var(--color-accent)",
  booster_filled: "var(--color-accent)",
  partial_tp1: "var(--color-success)",
  partial_tp2: "var(--color-success)",
  trailing: "var(--color-success)",
  closed_win: "var(--color-success)",
  closed_loss: "var(--color-danger)",
  closed_be: "var(--color-fg-muted)",
  cancelled: "var(--color-fg-faint)",
  error: "var(--color-danger)",
};

const STATE_LABEL: Record<string, string> = {
  pending: "Pending",
  radar_filled: "Radar filled",
  u1_filled: "Utama 1 filled",
  u2_filled: "Utama 2 filled",
  booster_filled: "Booster filled",
  partial_tp1: "TP1 hit",
  partial_tp2: "TP2 hit",
  trailing: "Trailing SL+",
  closed_win: "✓ WIN",
  closed_loss: "✗ LOSS",
  closed_be: "= BE",
  cancelled: "cancelled",
  error: "ERROR",
};

export function CascadePanel() {
  const { data } = useCascadeActive();
  const { data: allData } = useCascadeAll();
  const [showHistory, setShowHistory] = useState(false);
  const active = data?.items ?? [];
  // History = terminal-state cascades from /all endpoint
  const history = (allData?.items ?? []).filter((c) =>
    ["closed_win", "closed_loss", "closed_be", "cancelled", "error"].includes(c.state),
  );

  const handleKillSwitch = async () => {
    if (!confirm("Kill switch: cancel SEMUA cascade LIVE? Ini akan menutup posisi terbuka.")) return;
    try {
      const r = await killSwitch();
      toast.success(`Kill switch fired — ${r.cancelled_count} cascade dibatalkan`);
    } catch (e) {
      toast.error(`Kill switch failed: ${e instanceof Error ? e.message : "error"}`);
    }
  };

  return (
    <div className="lift rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] overflow-hidden">
      <div className="px-3 py-2 flex items-center gap-2 border-b border-[var(--color-border)]/50">
        <Zap size={11} className="text-[var(--color-accent)]" />
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
          Cascade Engine
        </span>
        <span className="text-[9px] text-[var(--color-fg-faint)]">
          {data?.live_enabled ? (
            <span className="text-[var(--color-warning)]">LIVE enabled</span>
          ) : (
            <span>paper-only</span>
          )}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-[9px] num text-[var(--color-fg-muted)]">
            {active.length} aktif
          </span>
          {active.length > 0 && (
            <button
              type="button"
              onClick={handleKillSwitch}
              className="text-[9px] uppercase tracking-wider px-2 py-0.5 rounded ring-1 ring-[var(--color-danger)]/40 text-[var(--color-danger)] hover:bg-[var(--color-danger-soft)] transition flex items-center gap-1 font-bold"
              title="Cancel all LIVE cascades"
            >
              <Power size={9} /> KILL
            </button>
          )}
        </div>
      </div>

      {/* Active list */}
      {active.length === 0 ? (
        <div className="p-3 text-[10px] text-center text-[var(--color-fg-faint)]">
          Belum ada cascade aktif — klik tombol "Start cascade" di sinyal untuk mulai.
        </div>
      ) : (
        <div className="p-2 space-y-1.5">
          {active.map((c) => (
            <CascadeRow key={c.id} cascade={c} />
          ))}
        </div>
      )}

      {/* History toggle */}
      {history.length > 0 && (
        <div className="border-t border-[var(--color-border)]/40">
          <button
            type="button"
            onClick={() => setShowHistory((s) => !s)}
            className="w-full px-3 py-1.5 flex items-center gap-2 text-[10px] text-[var(--color-fg-subtle)] hover:text-[var(--color-fg)] transition"
          >
            {showHistory ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
            History ({history.length})
          </button>
          <AnimatePresence>
            {showHistory && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25 }}
                className="overflow-hidden"
              >
                <div className="p-2 space-y-1">
                  {history
                    .sort((a, b) => (b.closed_ts_ms ?? 0) - (a.closed_ts_ms ?? 0))
                    .slice(0, 30)
                    .map((c) => (
                      <CascadeRow key={c.id} cascade={c} compact />
                    ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}

function CascadeRow({ cascade, compact }: { cascade: Cascade; compact?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const tone = STATE_TONE[cascade.state] || "var(--color-fg-muted)";
  const stateLabel = STATE_LABEL[cascade.state] || cascade.state;
  const filledTiers = cascade.tiers.filter((t) => t.filled).length;
  const filledTps = cascade.tps.filter((t) => t.filled).length;
  const isLong = cascade.direction === "LONG";
  const pnl = cascade.realized_pnl_usdt;

  const handleCancel = async () => {
    if (!confirm(`Batalkan cascade ${cascade.symbol}?`)) return;
    try {
      await cancelCascade(cascade.id);
      toast.success("Cascade dibatalkan");
    } catch (e) {
      toast.error(`Cancel failed: ${e instanceof Error ? e.message : "error"}`);
    }
  };

  const handleToggleMode = async () => {
    const target = cascade.mode === "paper" ? "live" : "paper";
    if (
      target === "live" &&
      !confirm(
        `Upgrade ke LIVE? Real money risk. Cascade akan place real MEXC orders. Lanjut?`,
      )
    )
      return;
    try {
      await setCascadeMode(cascade.id, target);
      toast.success(`Mode → ${target}`);
    } catch (e) {
      toast.error(`Mode change failed: ${e instanceof Error ? e.message : "error"}`);
    }
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="rounded-[var(--radius-sm)] bg-white/[0.03] ring-1 ring-[var(--color-border)]/40"
    >
      <button
        type="button"
        onClick={() => setExpanded((s) => !s)}
        className="w-full px-2.5 py-2 flex items-center gap-2 hover:bg-white/[0.03] transition text-left"
      >
        {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        <span
          className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider"
          style={{
            color: isLong ? "var(--color-success)" : "var(--color-danger)",
            background: `color-mix(in oklch, ${isLong ? "var(--color-success)" : "var(--color-danger)"} 12%, transparent)`,
          }}
        >
          {cascade.direction}
        </span>
        <span className="text-xs font-bold">{cascade.symbol.replace("_USDT", "")}</span>
        <span
          className="text-[8px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded"
          style={{
            color: tone,
            background: `color-mix(in oklch, ${tone} 12%, transparent)`,
          }}
        >
          {stateLabel}
        </span>
        <span
          className="text-[8px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded"
          style={{
            color: cascade.mode === "live" ? "var(--color-warning)" : "var(--color-fg-faint)",
            background:
              cascade.mode === "live"
                ? "color-mix(in oklch, var(--color-warning) 16%, transparent)"
                : "rgba(255,255,255,0.04)",
          }}
        >
          {cascade.mode}
        </span>
        <span className="text-[9px] text-[var(--color-fg-faint)] ml-auto num">
          tier {filledTiers}/{cascade.tiers.length} · TP {filledTps}/{cascade.tps.length}
        </span>
        <span
          className="text-[10px] num font-bold"
          style={{
            color:
              pnl > 0
                ? "var(--color-success)"
                : pnl < 0
                  ? "var(--color-danger)"
                  : "var(--color-fg-muted)",
          }}
        >
          {pnl > 0 ? "+" : ""}
          {fmt(pnl, 2)}
        </span>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden border-t border-[var(--color-border)]/30"
          >
            <div className="p-2.5 space-y-2 text-[10px]">
              {/* Tiers */}
              <div>
                <div className="text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1">
                  Tiers
                </div>
                <div className="space-y-0.5">
                  {cascade.tiers.map((t) => (
                    <div
                      key={t.role}
                      className="flex items-center gap-2 px-2 py-1 rounded bg-white/[0.02]"
                    >
                      <span className="text-[8px] uppercase tracking-wider w-12 font-bold">
                        {t.name}
                      </span>
                      <span className="num text-[var(--color-fg-muted)]">
                        @{fmtPrice(t.target_price)}
                      </span>
                      <span className="text-[8px] text-[var(--color-fg-faint)]">
                        ${fmt(t.size_usdt, 2)} · {t.lev}x
                      </span>
                      <span className="ml-auto">
                        {t.filled ? (
                          <span className="text-[var(--color-success)] flex items-center gap-1">
                            <CheckCircle size={9} />
                            <span className="num text-[9px]">
                              filled @{t.fill_price ? fmtPrice(t.fill_price) : "—"}
                            </span>
                          </span>
                        ) : (
                          <span className="text-[var(--color-fg-faint)] text-[9px]">waiting</span>
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* TPs */}
              <div>
                <div className="text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1">
                  Take profits
                </div>
                <div className="space-y-0.5">
                  {cascade.tps.map((tp) => (
                    <div
                      key={tp.tp_num}
                      className="flex items-center gap-2 px-2 py-1 rounded bg-white/[0.02]"
                    >
                      <span className="text-[8px] uppercase tracking-wider w-12 font-bold">
                        TP{tp.tp_num}
                      </span>
                      <span className="num text-[var(--color-fg-muted)]">
                        @{fmtPrice(tp.target_price)}
                      </span>
                      <span className="text-[8px] text-[var(--color-fg-faint)]">
                        close {tp.close_pct}%
                      </span>
                      <span className="ml-auto">
                        {tp.filled ? (
                          <span className="text-[var(--color-success)] num text-[9px]">
                            +{fmt(tp.pnl_usdt ?? 0, 2)} USDT
                          </span>
                        ) : (
                          <span className="text-[var(--color-fg-faint)] text-[9px]">waiting</span>
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {/* SL */}
              <div className="px-2 py-1.5 rounded bg-[var(--color-danger-soft)] ring-1 ring-[var(--color-danger)]/30">
                <div className="flex items-center gap-2">
                  <AlertOctagon size={10} className="text-[var(--color-danger)]" />
                  <span className="text-[9px] text-[var(--color-fg-subtle)] uppercase tracking-wider">
                    SL
                  </span>
                  <span className="text-[10px] num font-bold text-[var(--color-danger)]">
                    {fmtPrice(cascade.sl_price)}
                  </span>
                  {cascade.sl_breakeven_armed && (
                    <span className="text-[8px] uppercase tracking-wider px-1 py-0.5 rounded bg-[var(--color-success-soft)] text-[var(--color-success)] font-bold">
                      BE armed
                    </span>
                  )}
                  {cascade.sl_trail_armed && (
                    <span className="text-[8px] uppercase tracking-wider px-1 py-0.5 rounded bg-[var(--color-warning-soft)] text-[var(--color-warning)] font-bold">
                      trailing
                    </span>
                  )}
                </div>
                <div className="text-[8px] text-[var(--color-fg-faint)] mt-0.5">
                  {cascade.sl_reason}
                </div>
              </div>

              {/* Metadata */}
              <div className="flex items-center justify-between text-[9px] text-[var(--color-fg-faint)]">
                <span>
                  Akun: <span className="text-[var(--color-fg-muted)]">{cascade.account_name}</span>
                </span>
                <span>
                  Avg entry:{" "}
                  <span className="num text-[var(--color-fg-muted)]">
                    {cascade.weighted_avg_entry ? fmtPrice(cascade.weighted_avg_entry) : "—"}
                  </span>
                </span>
                <span>
                  Mark:{" "}
                  <span className="num text-[var(--color-accent)]">
                    {cascade.last_seen_price ? fmtPrice(cascade.last_seen_price) : "—"}
                  </span>
                </span>
              </div>

              {/* Notes (last 3) */}
              {cascade.notes.length > 0 && (
                <div className="text-[8px] text-[var(--color-fg-faint)] space-y-0.5 max-h-20 overflow-y-auto">
                  {cascade.notes.slice(-3).map((n, i) => (
                    <div key={i}>· {n}</div>
                  ))}
                </div>
              )}

              {/* Actions */}
              {!compact && (
                <div className="flex items-center gap-2 pt-1 border-t border-[var(--color-border)]/30">
                  <button
                    type="button"
                    onClick={handleToggleMode}
                    className={cn(
                      "text-[9px] uppercase tracking-wider px-2 py-0.5 rounded ring-1 transition",
                      cascade.mode === "live"
                        ? "text-[var(--color-warning)] ring-[var(--color-warning)]/40 hover:bg-[var(--color-warning-soft)]"
                        : "text-[var(--color-fg-subtle)] ring-[var(--color-border)] hover:text-[var(--color-fg)]",
                    )}
                  >
                    {cascade.mode === "paper" ? "→ LIVE" : "→ paper"}
                  </button>
                  <button
                    type="button"
                    onClick={handleCancel}
                    className="text-[9px] uppercase tracking-wider px-2 py-0.5 rounded ring-1 ring-[var(--color-danger)]/40 text-[var(--color-danger)] hover:bg-[var(--color-danger-soft)] transition flex items-center gap-1"
                  >
                    <XCircle size={9} /> Cancel
                  </button>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

void Activity; // Keep import for future use
