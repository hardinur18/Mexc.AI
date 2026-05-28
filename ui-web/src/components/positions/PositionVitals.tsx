import { motion } from "motion/react";
import { Zap, Activity, TrendingUp, TrendingDown } from "lucide-react";
import { fmt, fmtPct, fmtSign } from "@/lib/format";
import type { Position } from "@/types/position";
import { cn } from "@/lib/cn";
import { HealthScore } from "./HealthScore";
import { FundingCard } from "./FundingCard";
import { HoldingCard } from "./HoldingCard";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";

/* ═══════════════ Live Unrealized P&L (matches MEXC display) ═══════════════ */
export function PnlBreakdown({ p }: { p: Position }) {
  // Primary: UNREALIZED — matches what MEXC web shows in Open Positions tab
  const tone =
    p.pnl_unrealized > 0
      ? "var(--color-success)"
      : p.pnl_unrealized < 0
        ? "var(--color-danger)"
        : "var(--color-fg-muted)";
  const TrendIcon = p.pnl_unrealized > 0 ? TrendingUp : TrendingDown;
  const roiUnreal = p.margin > 0 ? (p.pnl_unrealized / p.margin) * 100 : 0;

  return (
    <div className="rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] px-3 py-3">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] flex items-center gap-1.5">
          <TrendIcon size={11} style={{ color: tone }} />
          Unrealized P&L
          <span className="text-[var(--color-fg-faint)] normal-case font-normal">(live)</span>
        </span>
        <span className="text-[9px] uppercase tracking-wider font-bold" style={{ color: tone }}>
          {p.pnl_unrealized >= 0 ? "untung" : "rugi"}
        </span>
      </div>

      <div className="flex items-baseline gap-2 mb-2" style={{ color: tone }}>
        <AnimatedNumber
          value={p.pnl_unrealized}
          decimals={4}
          signed
          className="text-[28px] leading-none font-bold num"
        />
        <span className="text-[11px] opacity-70">USDT</span>
        <span className="ml-auto text-base font-semibold num" style={{ color: tone }}>
          {fmtPct(roiUnreal)} ROI
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2 text-[10px] num pt-2 border-t border-[var(--color-border)]/50">
        <div>
          <div className="text-[var(--color-fg-faint)] uppercase tracking-wider mb-0.5">
            Realised (locked)
          </div>
          <div
            className="font-medium"
            style={{
              color:
                p.pnl_realised > 0
                  ? "var(--color-success)"
                  : p.pnl_realised < 0
                    ? "var(--color-fg-muted)"
                    : "var(--color-fg-muted)",
            }}
          >
            {fmtSign(p.pnl_realised, 4)}
          </div>
          <div className="text-[9px] text-[var(--color-fg-faint)]">
            partial TPs + fees
          </div>
        </div>
        <div>
          <div className="text-[var(--color-fg-faint)] uppercase tracking-wider mb-0.5">
            Net Lifetime
          </div>
          <div
            className="font-medium"
            style={{
              color:
                p.pnl_usdt > 0
                  ? "var(--color-success)"
                  : p.pnl_usdt < 0
                    ? "var(--color-danger)"
                    : "var(--color-fg-muted)",
            }}
          >
            {fmtSign(p.pnl_usdt, 4)}
          </div>
          <div className="text-[9px] text-[var(--color-fg-faint)]">
            unreal + realised
          </div>
        </div>
        <div>
          <div className="text-[var(--color-fg-faint)] uppercase tracking-wider mb-0.5">
            Net ROI
          </div>
          <div
            className="font-medium"
            style={{
              color:
                p.pnl_pct_lev > 0
                  ? "var(--color-success)"
                  : p.pnl_pct_lev < 0
                    ? "var(--color-danger)"
                    : "var(--color-fg-muted)",
            }}
          >
            {fmtPct(p.pnl_pct_lev)}
          </div>
          <div className="text-[9px] text-[var(--color-fg-faint)]">on margin</div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════ Signal Alignment — cross-check posisi vs market signal ═══════════════ */
function SignalAlignmentCard({ p }: { p: Position }) {
  const score = p.signal_score;
  const verdict = p.signal_verdict ?? "—";
  const oversoldN = p.signal_oversold_n ?? 0;
  const overboughtN = p.signal_overbought_n ?? 0;

  // Verdict tone
  // New scoring (no baseline): 80+ scream, 65+ accumulate, 45+ watch, 25+ wait, else avoid
  const tone =
    score == null
      ? "var(--color-fg-muted)"
      : score >= 80
        ? "var(--color-success)"
        : score >= 65
          ? "var(--color-success)"
          : score >= 45
            ? "var(--color-warning)"
            : score >= 25
              ? "var(--color-fg-muted)"
              : "var(--color-danger)";

  // Cross-signal interpretation:
  // Position is LONG + signal says ACCUMULATE/SCREAMING = ALIGNED ✓
  // Position is LONG + signal says AVOID = MISALIGNED (you bought at top)
  const isLong = p.side === "LONG";
  const isAligned =
    score == null
      ? null
      : isLong
        ? score >= 45
        : score < 25; // SHORT positions should align with bearish signals
  const alignmentLabel =
    isAligned == null
      ? "—"
      : isAligned
        ? "✓ SEJALAN"
        : "✗ MELAWAN SINYAL";
  const alignmentTone = isAligned
    ? "var(--color-success)"
    : isAligned === false
      ? "var(--color-danger)"
      : "var(--color-fg-muted)";

  return (
    <div className="rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] px-3 py-3 space-y-2.5">
      <div className="flex items-center justify-between">
        <span className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] flex items-center gap-1.5">
          <Activity size={11} />
          Posisi vs Sinyal Pasar
        </span>
        <span
          className="text-[9px] uppercase tracking-wider font-bold"
          style={{ color: alignmentTone }}
        >
          {alignmentLabel}
        </span>
      </div>

      {/* Verdict + score */}
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] font-bold uppercase tracking-wider" style={{ color: tone }}>
          {verdict}
        </span>
        {score != null && (
          <span className="num text-base font-bold" style={{ color: tone }}>
            {score}
            <span className="text-[10px] opacity-60 ml-0.5">/100</span>
          </span>
        )}
      </div>

      {/* Score bar with thresholds */}
      {score != null && (
        <div>
          <div className="relative h-1.5 rounded-full bg-white/5 overflow-hidden">
            <div
              className="absolute top-0 bottom-0 w-px bg-[var(--color-warning)]/40"
              style={{ left: "60%" }}
            />
            <div
              className="absolute top-0 bottom-0 w-px bg-[var(--color-success)]/50"
              style={{ left: "75%" }}
            />
            <div
              className="absolute top-0 bottom-0 w-px bg-[var(--color-success)]"
              style={{ left: "85%" }}
            />
            <motion.div
              initial={false}
              animate={{ width: `${score}%` }}
              transition={{ duration: 0.6, ease: [0.34, 1.4, 0.4, 1] }}
              className="h-full rounded-full"
              style={{
                background: tone,
                boxShadow: `0 0 6px ${tone}`,
              }}
            />
          </div>
          <div className="flex justify-between text-[8px] text-[var(--color-fg-faint)] mt-0.5 uppercase tracking-wider">
            <span>hindari</span>
            <span>sabar</span>
            <span>akumulasi</span>
            <span>borong</span>
          </div>
        </div>
      )}

      {/* MTF context */}
      <div className="flex items-center justify-between text-[10px] pt-0.5">
        <div className="flex items-center gap-2">
          <span className="text-[var(--color-fg-faint)] uppercase tracking-wider">MTF</span>
          <span className="text-[var(--color-success)] num">
            {oversoldN}/4 oversold
          </span>
          {overboughtN > 0 && (
            <span className="text-[var(--color-danger)] num">
              {overboughtN}/4 overbeli
            </span>
          )}
        </div>
        {p.signal_bb_lower && (
          <span className="text-[var(--color-success)] text-[9px] uppercase tracking-wider font-bold">
            ⚡ SENTUH BB BAWAH
          </span>
        )}
      </div>

      {/* Distance from 7d high (key dip-buy metric) */}
      {p.signal_dist_7d_high != null && (
        <div className="text-[10px] flex items-center justify-between border-t border-[var(--color-border)]/40 pt-2">
          <span className="text-[var(--color-fg-faint)] uppercase tracking-wider">
            Diskon dari high 7d
          </span>
          <span
            className="num font-semibold"
            style={{
              color:
                p.signal_dist_7d_high < -15
                  ? "var(--color-success)"
                  : p.signal_dist_7d_high < -8
                    ? "var(--color-fg-muted)"
                    : "var(--color-danger)",
            }}
          >
            {p.signal_dist_7d_high > 0 ? "+" : ""}
            {p.signal_dist_7d_high.toFixed(2)}%
          </span>
        </div>
      )}
    </div>
  );
}

/* ═══════════════ Leverage + Notional + Targets (bottom-right) ═══════════════ */
function LeverageCard({ p }: { p: Position }) {
  const lev = p.lev;
  const lTone =
    lev > 75
      ? "var(--color-danger)"
      : lev > 25
        ? "var(--color-warning)"
        : "var(--color-success)";
  const lText = lev > 75 ? "Extreme" : lev > 25 ? "High" : "Moderate";

  // Quick distance to TP1 bar
  const tpDist = p.tp_dist_pct;
  const bufferDist = p.buffer_pct;

  return (
    <div className="rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] px-3 py-3 space-y-3">
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] flex items-center gap-1.5">
            <Zap size={11} />
            Exposure
          </span>
          <span className="text-[9px] uppercase tracking-wider font-bold" style={{ color: lTone }}>
            {lText}
          </span>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <Stat label="Lev" value={`${lev}x`} tone={lTone} />
          <Stat label="Margin" value={fmt(p.margin, 3)} subValue="USDT" />
          <Stat label="Notional" value={fmt(p.notional, 1)} subValue="USDT" />
        </div>
        <div className="text-[9px] text-[var(--color-fg-faint)] mt-1.5 uppercase tracking-wider">
          {p.open_type} · {p.side.toLowerCase()}
        </div>
      </div>

      <div className="h-px bg-[var(--color-border)]/40" />

      <div className="space-y-1.5">
        <DistanceBar
          label="→ TP nearest"
          value={tpDist ?? 0}
          available={tpDist !== null}
          max={50}
          tone="var(--color-success)"
        />
        <DistanceBar
          label="→ Liq buffer"
          value={bufferDist ?? 0}
          available={bufferDist !== null}
          max={60}
          tone={
            bufferDist != null && bufferDist < 10
              ? "var(--color-danger)"
              : bufferDist != null && bufferDist < 25
                ? "var(--color-warning)"
                : "var(--color-success)"
          }
          unavailableText="cross-shared"
        />
      </div>
    </div>
  );
}

/* ═══════════════ Tiny primitives ═══════════════ */
function Stat({
  label,
  value,
  subValue,
  tone,
}: {
  label: string;
  value: string;
  subValue?: string;
  tone?: string;
}) {
  return (
    <div className="leading-tight">
      <div className="text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)]">
        {label}
      </div>
      <div className={cn("text-[13px] font-semibold num")} style={{ color: tone }}>
        {value}
      </div>
      {subValue && (
        <div className="text-[8px] text-[var(--color-fg-faint)] uppercase tracking-wider">
          {subValue}
        </div>
      )}
    </div>
  );
}

function DistanceBar({
  label,
  value,
  available,
  max,
  tone,
  unavailableText,
}: {
  label: string;
  value: number;
  available: boolean;
  max: number;
  tone: string;
  unavailableText?: string;
}) {
  if (!available) {
    return (
      <div className="flex items-center justify-between text-[10px]">
        <span className="text-[var(--color-fg-muted)]">{label}</span>
        <span className="text-[var(--color-fg-faint)] uppercase tracking-wider">
          {unavailableText ?? "n/a"}
        </span>
      </div>
    );
  }
  return (
    <div>
      <div className="flex justify-between text-[10px] mb-0.5">
        <span className="text-[var(--color-fg-muted)]">{label}</span>
        <span className="num font-medium" style={{ color: tone }}>
          {fmtPct(value)}
        </span>
      </div>
      <div className="relative h-0.5 rounded-full bg-white/5 overflow-hidden">
        <motion.div
          initial={false}
          animate={{ width: `${Math.min(Math.abs(value) / max, 1) * 100}%` }}
          transition={{ duration: 0.4, ease: [0.34, 1.4, 0.4, 1] }}
          className="h-full rounded-full"
          style={{ background: tone, boxShadow: `0 0 4px ${tone}80` }}
        />
      </div>
    </div>
  );
}

/* ═══════════════ Container — 2x3 grid wrapping all vitals ═══════════════ */
export function PositionVitals({ p }: { p: Position }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <PnlBreakdown p={p} />
      <HealthScore p={p} />
      <SignalAlignmentCard p={p} />
      <LeverageCard p={p} />
      <FundingCard p={p} />
      <HoldingCard p={p} />
    </div>
  );
}
