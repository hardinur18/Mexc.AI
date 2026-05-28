import { useMemo } from "react";
import { motion } from "motion/react";
import { Shield, ShieldAlert, AlertTriangle, Activity, TrendingUp, TrendingDown } from "lucide-react";
import type { Snapshot, Position, AccountSummary } from "@/types/position";
import { fmt, fmtPct } from "@/lib/format";

const MAX_TRADE_PCT = 5; // user rule: max 5% equity per trade
const MAX_AGG_EXPOSURE_MULT = 10; // max total notional / equity
const SAFE_BUFFER_PCT = 25;

interface RiskDashboardProps {
  snapshot: Snapshot;
}

/** Inner content — used inside InsightsPanel. */
export function RiskDashboardInner({ snapshot }: RiskDashboardProps) {
  const metrics = useMemo(() => computeRisk(snapshot.accounts, snapshot.positions), [snapshot]);

  if (snapshot.positions.length === 0) return null;

  return (
    <div className="px-4 py-3">
      {/* Summary header */}
      <div className="flex items-center justify-between mb-3 text-[10px] uppercase tracking-wider text-[var(--color-fg-faint)]">
        <span>aturan ≤5% per-posisi · {snapshot.totals.pos_count} posisi aktif</span>
        <div className="flex items-center gap-2">
          {metrics.violations.length > 0 && (
            <span className="text-[10px] px-2 py-0.5 rounded-[var(--radius-sm)] bg-[var(--color-danger-soft)] text-[var(--color-danger)] ring-1 ring-[var(--color-danger)]/40 font-bold">
              {metrics.violations.length} pelanggaran
            </span>
          )}
          <OverallRiskPill level={metrics.overallLevel} />
        </div>
      </div>

      {/* 4-card grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
        {/* 1. Total exposure leverage */}
        <RiskCard
          icon={<Activity size={11} />}
          label="Leverage Efektif"
          value={`${metrics.aggLeverage.toFixed(2)}x`}
          sub={`${fmt(metrics.totalNotional, 1)} / ${fmt(metrics.totalEquity, 1)} equity`}
          tone={
            metrics.aggLeverage > MAX_AGG_EXPOSURE_MULT
              ? "danger"
              : metrics.aggLeverage > 5
                ? "warn"
                : "ok"
          }
          fillPct={Math.min(100, (metrics.aggLeverage / MAX_AGG_EXPOSURE_MULT) * 100)}
        />

        {/* 2. Largest position % of equity */}
        <RiskCard
          icon={metrics.largestTradePct > MAX_TRADE_PCT ? <ShieldAlert size={11} /> : <Shield size={11} />}
          label="Posisi Terbesar vs Aturan"
          value={fmtPct(metrics.largestTradePct)}
          sub={
            metrics.largestPosition
              ? `${metrics.largestPosition.symbol} · ${metrics.largestPosition.account_name}`
              : "—"
          }
          tone={
            metrics.largestTradePct > MAX_TRADE_PCT
              ? "danger"
              : metrics.largestTradePct > MAX_TRADE_PCT * 0.7
                ? "warn"
                : "ok"
          }
          fillPct={Math.min(100, (metrics.largestTradePct / (MAX_TRADE_PCT * 1.5)) * 100)}
          ruleLine={MAX_TRADE_PCT}
        />

        {/* 3. Long/Short bias */}
        <RiskCard
          icon={metrics.longBias >= 60 ? <TrendingUp size={11} /> : metrics.longBias <= 40 ? <TrendingDown size={11} /> : <Activity size={11} />}
          label="Bias Arah"
          value={
            metrics.longBias >= 60
              ? "Dominan Long"
              : metrics.longBias <= 40
                ? "Dominan Short"
                : "Seimbang"
          }
          sub={`${metrics.longBias.toFixed(0)}% L · ${(100 - metrics.longBias).toFixed(0)}% S (dari notional)`}
          tone={metrics.longBias > 85 || metrics.longBias < 15 ? "warn" : "ok"}
          fillPct={metrics.longBias}
          biasMode
        />

        {/* 4. Closest to liq */}
        <RiskCard
          icon={
            metrics.closestBuffer != null && metrics.closestBuffer < 10 ? (
              <AlertTriangle size={11} />
            ) : (
              <Shield size={11} />
            )
          }
          label="Terdekat ke Liq"
          value={
            metrics.closestBuffer != null
              ? `${metrics.closestBuffer.toFixed(1)}%`
              : "shared"
          }
          sub={
            metrics.closestPosition
              ? `${metrics.closestPosition.symbol} · ${metrics.closestPosition.account_name}`
              : "tidak ada posisi isolated"
          }
          tone={
            metrics.closestBuffer == null
              ? "ok"
              : metrics.closestBuffer < 10
                ? "danger"
                : metrics.closestBuffer < SAFE_BUFFER_PCT
                  ? "warn"
                  : "ok"
          }
          fillPct={
            metrics.closestBuffer != null
              ? Math.min(100, metrics.closestBuffer * 2)
              : 100
          }
        />
      </div>

      {/* Rule violations strip */}
      {metrics.violations.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5 pt-2 border-t border-[var(--color-border)]/40">
          <span className="text-[9px] uppercase tracking-wider text-[var(--color-danger)] font-bold flex items-center gap-1">
            <AlertTriangle size={10} />
            Pelanggaran aturan:
          </span>
          {metrics.violations.map((v, i) => (
            <span
              key={i}
              className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-danger-soft)] text-[var(--color-danger)] ring-1 ring-[var(--color-danger)]/30"
            >
              {v}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** Default export — wrapper for backward compat. */
export function RiskDashboard({ snapshot }: RiskDashboardProps) {
  return (
    <div className="glass rounded-[var(--radius-lg)] mb-5">
      <RiskDashboardInner snapshot={snapshot} />
    </div>
  );
}

function OverallRiskPill({ level }: { level: "low" | "moderate" | "high" | "critical" }) {
  const map = {
    low: { color: "var(--color-success)", label: "Risiko: Rendah" },
    moderate: { color: "var(--color-warning)", label: "Risiko: Sedang" },
    high: { color: "oklch(75% 0.18 45)", label: "Risiko: Tinggi" },
    critical: { color: "var(--color-danger)", label: "Risiko: Kritis" },
  } as const;
  const m = map[level];
  return (
    <span
      className="text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-[var(--radius-sm)] ring-1"
      style={{
        color: m.color,
        background: `color-mix(in oklch, ${m.color} 12%, transparent)`,
        borderColor: `color-mix(in oklch, ${m.color} 40%, transparent)`,
      }}
    >
      {m.label}
    </span>
  );
}

function RiskCard({
  icon,
  label,
  value,
  sub,
  tone,
  fillPct,
  ruleLine,
  biasMode,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  tone: "ok" | "warn" | "danger";
  fillPct: number;
  ruleLine?: number;
  biasMode?: boolean;
}) {
  const c =
    tone === "danger"
      ? "var(--color-danger)"
      : tone === "warn"
        ? "var(--color-warning)"
        : "var(--color-success)";
  return (
    <div className="rounded-[var(--radius-md)] inner-card px-3 py-2.5">
      <div className="flex items-center gap-1.5 text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] mb-1">
        <span style={{ color: c }}>{icon}</span>
        {label}
      </div>
      <div className="text-base font-bold num leading-none" style={{ color: c }}>
        {value}
      </div>
      {sub && (
        <div className="text-[10px] text-[var(--color-fg-faint)] mt-0.5 truncate">{sub}</div>
      )}
      {/* Bar */}
      <div className="relative h-1 rounded-full bg-[var(--color-surface)] overflow-hidden mt-1.5">
        {ruleLine !== undefined && (
          <div
            className="absolute top-0 bottom-0 w-px bg-white/40"
            style={{ left: `${(ruleLine / 7.5) * 100}%` }}
          />
        )}
        {biasMode ? (
          <>
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${fillPct}%` }}
              transition={{ duration: 0.5, ease: [0.34, 1.4, 0.4, 1] }}
              className="absolute top-0 bottom-0 left-0"
              style={{ background: "var(--color-success)" }}
            />
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${100 - fillPct}%` }}
              transition={{ duration: 0.5, ease: [0.34, 1.4, 0.4, 1] }}
              className="absolute top-0 bottom-0 right-0"
              style={{ background: "var(--color-danger)" }}
            />
          </>
        ) : (
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${fillPct}%` }}
            transition={{ duration: 0.5, ease: [0.34, 1.4, 0.4, 1] }}
            className="absolute top-0 bottom-0 left-0"
            style={{
              background: c,
              boxShadow: tone !== "ok" ? `0 0 4px ${c}` : "none",
            }}
          />
        )}
      </div>
    </div>
  );
}

function computeRisk(accounts: AccountSummary[], positions: Position[]) {
  const totalEquity = accounts.reduce((s, a) => s + a.equity, 0) || 1;
  const totalNotional = positions.reduce((s, p) => s + p.notional, 0);
  const aggLeverage = totalEquity > 0 ? totalNotional / totalEquity : 0;

  // Largest trade %
  let largestPosition: Position | null = null;
  let largestTradePct = 0;
  for (const p of positions) {
    const accountEquity = accounts.find((a) => a.id === p.account_id)?.equity || 1;
    const pct = (p.margin / accountEquity) * 100;
    if (pct > largestTradePct) {
      largestTradePct = pct;
      largestPosition = p;
    }
  }

  // Long/Short bias by notional
  const longNotional = positions.filter((p) => p.side === "LONG").reduce((s, p) => s + p.notional, 0);
  const longBias = totalNotional > 0 ? (longNotional / totalNotional) * 100 : 50;

  // Closest to liq (isolated positions only — cross is shared)
  let closestPosition: Position | null = null;
  let closestBuffer: number | null = null;
  for (const p of positions) {
    if (p.buffer_pct == null) continue;
    if (closestBuffer == null || p.buffer_pct < closestBuffer) {
      closestBuffer = p.buffer_pct;
      closestPosition = p;
    }
  }

  // Rule violations
  const violations: string[] = [];
  if (largestTradePct > MAX_TRADE_PCT)
    violations.push(
      `Posisi > ${MAX_TRADE_PCT}% equity (${largestPosition?.symbol})`,
    );
  if (aggLeverage > MAX_AGG_EXPOSURE_MULT)
    violations.push(`Leverage efektif > ${MAX_AGG_EXPOSURE_MULT}x`);
  if (closestBuffer != null && closestBuffer < 10)
    violations.push(`${closestPosition?.symbol} buffer < 10%`);
  if (longBias > 90 || longBias < 10)
    violations.push("Bias arah ekstrem (semua LONG atau semua SHORT)");

  // Overall risk level
  let overallLevel: "low" | "moderate" | "high" | "critical" = "low";
  if (violations.length > 0) {
    if (violations.length >= 3 || (closestBuffer != null && closestBuffer < 10)) {
      overallLevel = "critical";
    } else if (violations.length >= 2) {
      overallLevel = "high";
    } else {
      overallLevel = "moderate";
    }
  } else if (largestTradePct > MAX_TRADE_PCT * 0.7 || aggLeverage > 5) {
    overallLevel = "moderate";
  }

  return {
    totalEquity,
    totalNotional,
    aggLeverage,
    largestPosition,
    largestTradePct,
    longBias,
    closestPosition,
    closestBuffer,
    violations,
    overallLevel,
  };
}
