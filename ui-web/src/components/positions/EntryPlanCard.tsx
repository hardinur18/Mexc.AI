import { motion } from "motion/react";
import {
  Target,
  TrendingUp,
  TrendingDown,
  Sparkles,
  Lock,
  Layers,
  Radar,
  BarChart3,
} from "lucide-react";
import { fmtPrice } from "@/lib/format";
import type { EntryPlan } from "@/types/position";
import { cn } from "@/lib/cn";

interface EntryPlanCardProps {
  plan: EntryPlan | null | undefined;
  verdict: string;
  score: number;
  sizingPct?: number;
  /** Total equity untuk hitung USD amount per tier */
  equityUsd?: number;
}

const TIER_COLORS: Record<string, string> = {
  radar: "var(--color-accent)",
  main_1: "var(--color-success)",
  main_2: "oklch(78% 0.17 165)",
  booster: "var(--color-warning)",
};

export function EntryPlanCard({
  plan,
  verdict,
  score,
  sizingPct = 0,
  equityUsd = 0,
}: EntryPlanCardProps) {
  if (!plan) {
    return (
      <div className="inner-card px-4 py-5 text-center">
        <div className="ui-section-title mb-2 flex items-center justify-center gap-1.5">
          <Target size={12} /> Rencana Entry Multi-Tier
        </div>
        <div className="text-[12px] text-[var(--color-fg-faint)]">
          Belum ada setup valid — tunggu confluence kuat sebelum entry
        </div>
      </div>
    );
  }

  const isLong = plan.direction === "LONG";
  const tone = isLong ? "var(--color-success)" : "var(--color-danger)";
  const DirIcon = isLong ? TrendingUp : TrendingDown;
  const tiers = plan.tiers ?? [];
  const tpLadder = plan.tp_ladder ?? [];

  return (
    <div className="inner-card overflow-hidden">
      {/* Header */}
      <div className="ui-panel-header px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="ui-icon-chip" style={{ color: tone }}>
            <Target size={13} />
          </span>
          <span className="ui-section-title">
            Rencana Entry Multi-Tier
          </span>
        </div>
        <span
          className="flex items-center gap-1.5 rounded-[var(--radius-sm)] border px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider"
          style={{
            color: tone,
            background: `color-mix(in oklch, ${tone} 14%, transparent)`,
            borderColor: `color-mix(in oklch, ${tone} 40%, transparent)`,
          }}
        >
          <DirIcon size={12} /> {verdict}
        </span>
      </div>

      <div className="px-3 py-3 space-y-3">
        {/* Reasoning — short summary */}
        {plan.reasoning && plan.reasoning.length > 0 && (
          <div>
            <div className="ui-section-title mb-1 flex items-center gap-1.5">
              <Sparkles size={11} /> Kenapa Setup Ini Valid
            </div>
            <ul className="space-y-0.5">
              {plan.reasoning.slice(0, 4).map((r, i) => (
                <li
                  key={i}
                  className="text-[11px] text-[var(--color-fg-muted)] flex items-start gap-1.5"
                >
                  <span
                    className="inline-block w-1 h-1 rounded-full mt-[6px] shrink-0"
                    style={{ background: tone }}
                  />
                  <span className="leading-snug">{r}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Tier ladder — entry plan per account */}
        {tiers.length > 0 && (
          <div>
            <div className="ui-section-title mb-1.5 flex items-center gap-1.5">
              <Radar size={11} /> Cascade Entry (DCA Pyramid)
            </div>
            <div className="space-y-1.5">
              {tiers.map((t) => {
                const tierColor = TIER_COLORS[t.role] ?? "var(--color-fg-muted)";
                const usd = equityUsd > 0 ? (equityUsd * t.size_pct_equity) / 100 : null;
                const radarPrice = tiers[0]?.price;
                const distPct =
                  radarPrice && t.price && radarPrice > 0
                    ? ((t.price - radarPrice) / radarPrice) * 100
                    : null;
                return (
                  <motion.div
                    key={t.role}
                    initial={{ opacity: 0, x: -4 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.3 }}
                    className="ui-subcard relative px-2.5 py-1.5"
                    style={{
                      borderLeftWidth: "3px",
                      borderLeftColor: tierColor,
                    }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <span
                          className="text-[11px] font-bold uppercase tracking-wider shrink-0 w-16"
                          style={{ color: tierColor }}
                        >
                          {t.name}
                        </span>
                        <div className="leading-tight min-w-0">
                          <div className="text-[12px] num font-bold text-[var(--color-fg)]">
                            @ {t.price != null ? fmtPrice(t.price) : "—"}
                            <span className="text-[11px] text-[var(--color-warning)] ml-1.5 font-bold">
                              {t.lev}x
                            </span>
                            {distPct != null && Math.abs(distPct) > 0.01 && (
                              <span
                                className="text-[11px] num ml-1.5"
                                style={{ color: tierColor }}
                              >
                                {distPct > 0 ? "+" : ""}
                                {distPct.toFixed(2)}%
                              </span>
                            )}
                          </div>
                          <div className="text-[11px] text-[var(--color-fg-muted)] truncate">
                            {t.trigger_label}
                          </div>
                        </div>
                      </div>
                      <div className="text-right shrink-0">
                        <div
                          className="text-[11px] font-bold num"
                          style={{ color: tierColor }}
                        >
                          {t.size_pct_equity}% eq
                        </div>
                        {usd != null && (
                          <div className="text-[10px] num text-[var(--color-fg-muted)]">
                            ≈ ${usd.toFixed(usd < 1 ? 3 : 2)}
                          </div>
                        )}
                      </div>
                    </div>
                    {t.rationale && (
                      <div className="text-[11px] text-[var(--color-fg-subtle)] leading-snug mt-1 pl-[74px]">
                        {t.rationale}
                      </div>
                    )}
                  </motion.div>
                );
              })}
            </div>

            {/* Cascade projection */}
            {plan.cascade_projection && (
              <div className="ui-subcard mt-2 px-3 py-2">
                <div className="ui-section-title mb-1.5 flex items-center gap-1.5">
                  <BarChart3 size={11} /> Proyeksi Cascade
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <div className="text-[10px] text-[var(--color-fg-faint)] uppercase tracking-wider">
                      Avg entry
                    </div>
                    <div className="text-[13px] num font-semibold text-[var(--color-fg)]">
                      {plan.cascade_projection.weighted_avg_price
                        ? fmtPrice(plan.cascade_projection.weighted_avg_price)
                        : "—"}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[var(--color-fg-faint)] uppercase tracking-wider">
                      Total expo
                    </div>
                    <div className="text-[13px] num font-semibold text-[var(--color-fg)]">
                      {plan.cascade_projection.total_size_pct_equity}%
                      {equityUsd > 0 && (
                        <span className="text-[11px] text-[var(--color-fg-faint)] ml-1">
                          ($
                          {(
                            (equityUsd *
                              plan.cascade_projection.total_size_pct_equity) /
                            100
                          ).toFixed(2)}
                          )
                        </span>
                      )}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-[var(--color-fg-faint)] uppercase tracking-wider">
                      Worst-case
                    </div>
                    <div className="text-[13px] num font-semibold text-[var(--color-danger)]">
                      -{plan.cascade_projection.worst_case_loss_pct_equity}% eq
                    </div>
                  </div>
                </div>
                {plan.cascade_projection.explanation && (
                  <div className="text-[11px] text-[var(--color-fg-faint)] leading-snug mt-1.5 pt-1.5 border-t border-[var(--color-border)]/30">
                    {plan.cascade_projection.explanation}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* TP ladder */}
        {tpLadder.length > 0 && (
          <div>
            <div className="ui-section-title mb-1.5 flex items-center gap-1.5">
              <Layers size={12} /> Take Profit Bertahap
            </div>
            <div className="ui-subcard overflow-hidden divide-y divide-[var(--color-border)]/40">
              {tpLadder.map((tp) => (
                <div
                  key={tp.tp}
                  className="flex items-center gap-2.5 px-3 py-1.5"
                >
                  <span className="shrink-0 w-8 text-[11px] font-bold text-[var(--color-success)]">
                    TP{tp.tp}
                  </span>
                  <span className="shrink-0 w-20 text-[12px] num font-semibold text-[var(--color-fg)]">
                    {tp.price != null ? fmtPrice(tp.price) : "—"}
                  </span>
                  <span className="shrink-0 text-[11px] text-[var(--color-fg-muted)] num font-medium">
                    +{tp.pct_price}%
                  </span>
                  <span className="flex-1 text-[11px] text-[var(--color-fg-faint)] truncate">
                    close {tp.close_pct}% · {tp.reason}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* SL+ hint */}
        {plan.stop_plus_hint && (
          <div className="ui-subcard flex items-start gap-2 px-3 py-2"
            style={{
              background: "color-mix(in oklch, var(--color-accent) 8%, var(--color-bg-elev))",
              borderColor: "color-mix(in oklch, var(--color-accent) 30%, var(--color-border))",
            }}
          >
            <Lock size={12} className="text-[var(--color-accent)] shrink-0 mt-0.5" />
            <div className="text-[11px] text-[var(--color-fg-muted)] leading-snug">
              <span className="text-[var(--color-accent)] font-semibold">SL+ : </span>
              {plan.stop_plus_hint}
            </div>
          </div>
        )}

        {/* Sizing summary footer */}
        <div className="flex items-center justify-between text-[11px] uppercase tracking-wider pt-2 border-t border-[var(--color-border)]/40">
          <span className="text-[var(--color-fg-faint)] font-medium">Skor & Sizing Default</span>
          <span
            className={cn(
              "font-bold num text-[12px]",
              score >= 65
                ? "text-[var(--color-success)]"
                : score >= 45
                  ? "text-[var(--color-warning)]"
                  : "text-[var(--color-fg-faint)]",
            )}
          >
            {score}/100 · {sizingPct}%
          </span>
        </div>
      </div>
    </div>
  );
}
