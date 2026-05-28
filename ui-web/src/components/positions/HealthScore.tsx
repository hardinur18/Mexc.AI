import { motion } from "motion/react";
import type { Position } from "@/types/position";
import { cn } from "@/lib/cn";

interface HealthScoreProps {
  p: Position;
}

interface Factor {
  label: string;
  weight: number;
  earned: number;
  detail: string;
  status: "good" | "fair" | "weak" | "critical";
}

function computeFactors(p: Position): Factor[] {
  const out: Factor[] = [];

  // 1. Buffer to liq (40 pts)
  if (p.buffer_pct == null) {
    out.push({
      label: "Buffer → Liq",
      weight: 40,
      earned: 30,
      detail: "cross-margin (shared)",
      status: "fair",
    });
  } else if (p.buffer_pct >= 50) {
    out.push({
      label: "Buffer → Liq",
      weight: 40,
      earned: 40,
      detail: `${p.buffer_pct.toFixed(1)}% headroom`,
      status: "good",
    });
  } else if (p.buffer_pct >= 25) {
    out.push({
      label: "Buffer → Liq",
      weight: 40,
      earned: 30,
      detail: `${p.buffer_pct.toFixed(1)}% — watch`,
      status: "fair",
    });
  } else if (p.buffer_pct >= 10) {
    out.push({
      label: "Buffer → Liq",
      weight: 40,
      earned: 15,
      detail: `${p.buffer_pct.toFixed(1)}% — risky`,
      status: "weak",
    });
  } else {
    out.push({
      label: "Buffer → Liq",
      weight: 40,
      earned: 0,
      detail: `${p.buffer_pct.toFixed(1)}% — danger`,
      status: "critical",
    });
  }

  // 2. SL set (25 pts)
  if (p.sl_price) {
    out.push({
      label: "Stop Loss",
      weight: 25,
      earned: 25,
      detail: `protected @ ${p.sl_price}`,
      status: "good",
    });
  } else {
    out.push({
      label: "Stop Loss",
      weight: 25,
      earned: 0,
      detail: "no SL set",
      status: "critical",
    });
  }

  // 3. Margin ratio (20 pts) — lower = better
  if (p.margin_ratio < 5) {
    out.push({
      label: "Margin Ratio",
      weight: 20,
      earned: 20,
      detail: `${p.margin_ratio.toFixed(2)}% — light`,
      status: "good",
    });
  } else if (p.margin_ratio < 20) {
    out.push({
      label: "Margin Ratio",
      weight: 20,
      earned: 14,
      detail: `${p.margin_ratio.toFixed(2)}% — moderate`,
      status: "fair",
    });
  } else if (p.margin_ratio < 50) {
    out.push({
      label: "Margin Ratio",
      weight: 20,
      earned: 8,
      detail: `${p.margin_ratio.toFixed(2)}% — high`,
      status: "weak",
    });
  } else {
    out.push({
      label: "Margin Ratio",
      weight: 20,
      earned: 0,
      detail: `${p.margin_ratio.toFixed(2)}% — critical`,
      status: "critical",
    });
  }

  // 4. Leverage sanity (15 pts)
  if (p.lev <= 5) {
    out.push({
      label: "Leverage",
      weight: 15,
      earned: 15,
      detail: `${p.lev}x — conservative`,
      status: "good",
    });
  } else if (p.lev <= 25) {
    out.push({
      label: "Leverage",
      weight: 15,
      earned: 11,
      detail: `${p.lev}x — moderate`,
      status: "fair",
    });
  } else if (p.lev <= 75) {
    out.push({
      label: "Leverage",
      weight: 15,
      earned: 6,
      detail: `${p.lev}x — high`,
      status: "weak",
    });
  } else {
    out.push({
      label: "Leverage",
      weight: 15,
      earned: 0,
      detail: `${p.lev}x — extreme`,
      status: "critical",
    });
  }

  return out;
}

const STATUS_COLOR = {
  good: "var(--color-success)",
  fair: "var(--color-warning)",
  weak: "oklch(75% 0.18 45)",
  critical: "var(--color-danger)",
};

export function HealthScore({ p }: HealthScoreProps) {
  const factors = computeFactors(p);
  const score = factors.reduce((s, f) => s + f.earned, 0);
  let tier: "strong" | "fair" | "weak" | "critical";
  if (score >= 75) tier = "strong";
  else if (score >= 55) tier = "fair";
  else if (score >= 35) tier = "weak";
  else tier = "critical";
  const tierColor = {
    strong: "var(--color-success)",
    fair: "var(--color-warning)",
    weak: "oklch(75% 0.18 45)",
    critical: "var(--color-danger)",
  }[tier];
  const tierLabel = { strong: "Strong", fair: "Fair", weak: "Weak", critical: "Critical" }[tier];

  const radius = 32;
  const stroke = 5;
  const circ = 2 * Math.PI * radius;
  const offset = circ * (1 - score / 100);

  return (
    <div className="rounded-[var(--radius-md)] inner-card px-3 py-3 flex flex-col gap-2">
      <div className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] flex items-center justify-between">
        <span>Health Score</span>
        <span className="font-bold" style={{ color: tierColor }}>
          {tierLabel}
        </span>
      </div>

      <div className="flex items-center gap-3">
        {/* Compact gauge */}
        <div className="relative w-[78px] h-[78px] shrink-0">
          <svg width="78" height="78" viewBox="0 0 78 78" className="-rotate-90">
            <circle
              cx="39"
              cy="39"
              r={radius}
              stroke="rgba(255,255,255,0.06)"
              strokeWidth={stroke}
              fill="none"
            />
            <motion.circle
              cx="39"
              cy="39"
              r={radius}
              stroke={tierColor}
              strokeWidth={stroke}
              strokeLinecap="round"
              fill="none"
              strokeDasharray={circ}
              initial={{ strokeDashoffset: circ }}
              animate={{ strokeDashoffset: offset }}
              transition={{ duration: 0.9, ease: [0.34, 1.4, 0.4, 1] }}
              style={{ filter: `drop-shadow(0 0 4px ${tierColor})` }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center leading-none">
            <motion.span
              key={score}
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.3 }}
              className="text-xl font-bold num"
              style={{ color: tierColor }}
            >
              {Math.round(score)}
            </motion.span>
            <span className="text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)] mt-0.5">
              / 100
            </span>
          </div>
        </div>

        {/* Factor breakdown */}
        <div className="flex-1 space-y-1.5">
          {factors.map((f) => {
            const pct = f.weight > 0 ? (f.earned / f.weight) * 100 : 0;
            const c = STATUS_COLOR[f.status];
            return (
              <div key={f.label}>
                <div className="flex items-baseline justify-between text-[10px]">
                  <span className="text-[var(--color-fg-muted)]">{f.label}</span>
                  <span
                    className="num font-semibold tabular-nums"
                    style={{ color: c }}
                  >
                    {f.earned}
                    <span className="opacity-50">/{f.weight}</span>
                  </span>
                </div>
                <div className="relative h-0.5 mt-0.5 bg-[var(--color-surface)] rounded-full overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{ duration: 0.6, ease: [0.34, 1.4, 0.4, 1] }}
                    className="absolute top-0 bottom-0 left-0"
                    style={{ background: c, boxShadow: `0 0 4px ${c}40` }}
                  />
                </div>
                <div className={cn("text-[9px] mt-0.5")} style={{ color: c, opacity: 0.7 }}>
                  {f.detail}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
