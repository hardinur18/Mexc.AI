import { motion } from "motion/react";
import { Flame, Shield } from "lucide-react";
import { usePortfolioRisk, useCircuitBreaker } from "@/hooks/useSnapshot";
import { fmt, fmtPct } from "@/lib/format";

export function PortfolioHeatCard() {
  const { data: heat } = usePortfolioRisk();
  const { data: breaker } = useCircuitBreaker();
  if (!heat) return null;

  const tone =
    heat.heat.warning_level === "critical"
      ? "var(--color-danger)"
      : heat.heat.warning_level === "high"
        ? "var(--color-warning)"
        : heat.heat.warning_level === "moderate"
          ? "var(--color-warning)"
          : "var(--color-success)";
  const widthPct = Math.min(100, heat.heat.total_heat_pct * 4);

  return (
    <div className="lift rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] overflow-hidden">
      <div className="px-3 py-2 flex items-center gap-2 border-b border-[var(--color-border)]/50">
        <Flame size={11} style={{ color: tone }} />
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
          Portfolio Heat
        </span>
        <span
          className="text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded ml-auto"
          style={{
            color: tone,
            background: `color-mix(in oklch, ${tone} 14%, transparent)`,
          }}
        >
          {heat.heat.warning_level}
        </span>
      </div>

      <div className="p-3 space-y-3">
        <div>
          <div className="flex items-baseline justify-between mb-1">
            <span
              className="text-2xl font-bold num leading-none"
              style={{ color: tone }}
            >
              {heat.heat.total_heat_pct.toFixed(1)}%
            </span>
            <span className="text-[9px] text-[var(--color-fg-faint)] num">
              equity {fmt(heat.total_equity, 2)} USDT
            </span>
          </div>
          <div className="relative h-1.5 rounded-full overflow-hidden bg-white/5">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${widthPct}%` }}
              transition={{ duration: 0.5, ease: [0.34, 1.4, 0.4, 1] }}
              className="absolute inset-y-0 left-0"
              style={{ background: tone, boxShadow: `0 0 8px ${tone}` }}
            />
            {/* Threshold marker at 25% (critical) */}
            <div
              className="absolute top-0 bottom-0 w-px bg-white/40"
              style={{ left: "100%" }}
              title="25% critical threshold"
            />
          </div>
          <div className="text-[9px] text-[var(--color-fg-faint)] mt-1">
            {heat.heat.open_positions} posisi · max single {heat.heat.max_single_heat_pct.toFixed(1)}%
          </div>
        </div>

        {/* Phase 14: Loss cooldown BIG warning */}
        {breaker?.cooldown_active && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="rounded-[var(--radius-sm)] px-3 py-2 ring-1 flex items-start gap-2"
            style={{
              background: "color-mix(in oklch, var(--color-danger) 14%, transparent)",
              borderColor: "color-mix(in oklch, var(--color-danger) 40%, transparent)",
              boxShadow: "0 0 12px color-mix(in oklch, var(--color-danger) 25%, transparent)",
            }}
          >
            <Shield size={13} className="text-[var(--color-danger)] mt-0.5 shrink-0 [animation:pulse-glow_2s_ease-in-out_infinite]" />
            <div className="leading-tight">
              <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-danger)]">
                🛑 Loss Cooldown Aktif
              </div>
              <div className="text-[9px] text-[var(--color-fg-muted)] mt-0.5">
                {breaker.cooldown_reason ?? ""}
              </div>
              {breaker.minutes_until_cooldown_ends != null && (
                <div className="text-[9px] text-[var(--color-danger)] font-bold mt-0.5 num">
                  {Math.max(0, breaker.minutes_until_cooldown_ends).toFixed(0)} mnt lagi sebelum bisa entry baru
                </div>
              )}
            </div>
          </motion.div>
        )}

        {/* Circuit breaker */}
        {breaker && (
          <div
            className="rounded-[var(--radius-sm)] px-2.5 py-1.5 ring-1"
            style={{
              background: breaker.tripped
                ? "color-mix(in oklch, var(--color-danger) 10%, transparent)"
                : "color-mix(in oklch, var(--color-success) 6%, transparent)",
              borderColor: breaker.tripped
                ? "color-mix(in oklch, var(--color-danger) 30%, transparent)"
                : "color-mix(in oklch, var(--color-border) 60%, transparent)",
            }}
          >
            <div className="flex items-center justify-between text-[9px]">
              <span className="flex items-center gap-1 uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
                <Shield size={9} />
                Circuit breaker
              </span>
              <span
                className="num font-semibold"
                style={{
                  color: breaker.tripped
                    ? "var(--color-danger)"
                    : breaker.daily_pct_equity > 0
                      ? "var(--color-success)"
                      : "var(--color-fg-muted)",
                }}
              >
                {fmtPct(breaker.daily_pct_equity)} hari ini
              </span>
            </div>
            <div className="text-[8px] text-[var(--color-fg-muted)] mt-0.5">
              {breaker.recommendation} · threshold {breaker.threshold_pct}%
            </div>
          </div>
        )}

        {/* Phase 9.1: Size recommendation */}
        {heat.size_recommendation && (
          <div
            className="rounded-[var(--radius-sm)] px-2.5 py-1.5 ring-1 text-[10px]"
            style={{
              background:
                heat.size_recommendation.multiplier >= 0.85
                  ? "color-mix(in oklch, var(--color-success) 6%, transparent)"
                  : heat.size_recommendation.multiplier >= 0.5
                    ? "color-mix(in oklch, var(--color-warning) 10%, transparent)"
                    : "color-mix(in oklch, var(--color-danger) 10%, transparent)",
              borderColor:
                heat.size_recommendation.multiplier >= 0.85
                  ? "color-mix(in oklch, var(--color-success) 30%, transparent)"
                  : heat.size_recommendation.multiplier >= 0.5
                    ? "color-mix(in oklch, var(--color-warning) 30%, transparent)"
                    : "color-mix(in oklch, var(--color-danger) 30%, transparent)",
            }}
          >
            <div className="flex items-center justify-between mb-0.5">
              <span className="text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)] font-semibold">
                Saran ukuran entry
              </span>
              <span className="num font-bold text-[11px]">
                {(heat.size_recommendation.multiplier * 100).toFixed(0)}%
              </span>
            </div>
            <div className="text-[9px] text-[var(--color-fg-muted)]">
              {heat.size_recommendation.reason}
            </div>
          </div>
        )}

        {/* Phase 9.4: Correlation cluster warning */}
        {heat.correlation && heat.correlation.clusters.length > 0 && (
          <div className="rounded-[var(--radius-sm)] px-2.5 py-1.5 ring-1 bg-[color-mix(in_oklch,var(--color-warning)_8%,transparent)] border-[color-mix(in_oklch,var(--color-warning)_25%,transparent)]">
            <div className="flex items-center justify-between mb-0.5">
              <span className="text-[8px] uppercase tracking-wider text-[var(--color-warning)] font-semibold">
                ⚠ Korelasi tinggi terdeteksi
              </span>
              <span className="text-[9px] text-[var(--color-fg-muted)]">
                {heat.correlation.raw_position_count} posisi → {heat.correlation.effective_position_count} efektif
              </span>
            </div>
            {heat.correlation.clusters.map((c, i) => (
              <div key={i} className="text-[9px] text-[var(--color-fg-muted)] mt-0.5">
                Cluster {i + 1}: {c.symbols.map((s) => s.replace("_USDT", "")).join(", ")} ({c.size}×)
              </div>
            ))}
            <div className="text-[8px] text-[var(--color-fg-faint)] mt-1 italic">
              Posisi-posisi ini bergerak bersamaan — risiko 1 trade besar, bukan {heat.correlation.raw_position_count} trade independent.
            </div>
          </div>
        )}

        {/* Per-account breakdown */}
        {heat.per_account.length > 0 && (
          <div className="space-y-1">
            <div className="text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)]">
              Per akun
            </div>
            {heat.per_account.map((a) => {
              const aTone =
                a.warning_level === "critical"
                  ? "var(--color-danger)"
                  : a.warning_level === "high"
                    ? "var(--color-warning)"
                    : a.warning_level === "moderate"
                      ? "var(--color-warning)"
                      : "var(--color-success)";
              return (
                <div
                  key={a.account_id}
                  className="flex items-center justify-between text-[10px] px-1.5 py-1 rounded bg-white/[0.02]"
                >
                  <span className="font-semibold truncate max-w-[120px]">{a.account_name}</span>
                  <div className="flex items-center gap-2">
                    <span className="num text-[9px] text-[var(--color-fg-muted)]">
                      {a.open_positions} pos
                    </span>
                    <span className="num font-bold" style={{ color: aTone }}>
                      {a.total_heat_pct.toFixed(1)}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
