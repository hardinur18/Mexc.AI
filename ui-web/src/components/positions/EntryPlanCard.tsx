import { motion } from "motion/react";
import {
  Target,
  TrendingUp,
  TrendingDown,
  Sparkles,
  Lock,
  Layers,
  Radar,
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
      <div className="rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] px-3 py-4 text-center">
        <div className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] mb-1.5 flex items-center justify-center gap-1.5">
          <Target size={11} /> Rencana Entry Multi-Tier
        </div>
        <div className="text-[11px] text-[var(--color-fg-faint)]">
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
    <div className="rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] overflow-hidden">
      <div
        className="px-3 py-2 flex items-center justify-between border-b border-[var(--color-border)]/50"
        style={{ background: `color-mix(in oklch, ${tone} 8%, transparent)` }}
      >
        <div className="flex items-center gap-1.5">
          <Target size={11} style={{ color: tone }} />
          <span className="text-[10px] uppercase tracking-wider font-semibold">
            Rencana Entry Multi-Tier
          </span>
        </div>
        <span
          className="text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-[var(--radius-sm)] flex items-center gap-1 ring-1"
          style={{
            color: tone,
            background: `color-mix(in oklch, ${tone} 14%, transparent)`,
            borderColor: `color-mix(in oklch, ${tone} 40%, transparent)`,
          }}
        >
          <DirIcon size={11} /> {verdict}
        </span>
      </div>

      <div className="px-3 py-3 space-y-3">
        {/* Reasoning — short summary */}
        {plan.reasoning && plan.reasoning.length > 0 && (
          <div>
            <div className="text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1 flex items-center gap-1.5">
              <Sparkles size={10} /> Kenapa Setup Ini Valid
            </div>
            <ul className="space-y-0.5">
              {plan.reasoning.slice(0, 4).map((r, i) => (
                <li
                  key={i}
                  className="text-[10px] text-[var(--color-fg-muted)] flex items-start gap-1.5"
                >
                  <span
                    className="inline-block w-0.5 h-0.5 rounded-full mt-1.5 shrink-0"
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
            <div className="text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1.5 flex items-center gap-1.5">
              <Radar size={10} /> Cascade Entry (DCA Pyramid)
            </div>
            <div className="space-y-2">
              {tiers.map((t) => {
                const tierColor = TIER_COLORS[t.role] ?? "var(--color-fg-muted)";
                const usd = equityUsd > 0 ? (equityUsd * t.size_pct_equity) / 100 : null;
                // Distance from current price (= radar price)
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
                    className="rounded-[var(--radius-sm)] ring-1 px-2.5 py-2 space-y-1"
                    style={{
                      background: `color-mix(in oklch, ${tierColor} 6%, transparent)`,
                      borderColor: `color-mix(in oklch, ${tierColor} 30%, transparent)`,
                    }}
                  >
                    {/* Tier header row */}
                    <div className="grid grid-cols-[64px_1fr_auto] gap-2 items-center">
                      <span
                        className="text-[9px] font-bold uppercase tracking-wider"
                        style={{ color: tierColor }}
                      >
                        {t.name}
                      </span>
                      <div className="leading-tight min-w-0">
                        <div className="text-[12px] num font-bold">
                          @ {t.price != null ? fmtPrice(t.price) : "—"}
                          <span className="text-[9px] text-[var(--color-warning)] ml-1.5 font-bold">
                            {t.lev}x
                          </span>
                          {distPct != null && Math.abs(distPct) > 0.01 && (
                            <span
                              className="text-[10px] num ml-1.5"
                              style={{ color: tierColor }}
                            >
                              {distPct > 0 ? "+" : ""}
                              {distPct.toFixed(2)}%
                            </span>
                          )}
                        </div>
                        <div className="text-[10px] text-[var(--color-fg-muted)] truncate">
                          ▶ {t.trigger_label}
                        </div>
                      </div>
                      <div className="text-right leading-tight">
                        <div
                          className="text-[11px] font-bold num"
                          style={{ color: tierColor }}
                        >
                          {t.size_pct_equity}% eq
                        </div>
                        {usd != null && (
                          <div className="text-[9px] num text-[var(--color-fg-muted)]">
                            ≈ ${usd.toFixed(usd < 1 ? 3 : 2)}
                          </div>
                        )}
                      </div>
                    </div>
                    {/* Tier rationale */}
                    {t.rationale && (
                      <div className="text-[9px] text-[var(--color-fg-subtle)] leading-snug pl-[68px] -mt-0.5">
                        {t.rationale}
                      </div>
                    )}
                  </motion.div>
                );
              })}
            </div>

            {/* Cascade projection — weighted avg + worst case */}
            {plan.cascade_projection && (
              <div className="mt-2 rounded-[var(--radius-sm)] bg-[var(--color-bg-elev-2)] ring-1 ring-[var(--color-border-strong)] px-3 py-2 space-y-1">
                <div className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
                  Proyeksi Cascade (Kalau Semua Tier Kena)
                </div>
                <div className="grid grid-cols-3 gap-2 text-[10px]">
                  <div>
                    <div className="text-[9px] text-[var(--color-fg-faint)] uppercase">
                      Avg entry
                    </div>
                    <div className="num font-semibold text-[var(--color-fg)]">
                      {plan.cascade_projection.weighted_avg_price
                        ? fmtPrice(plan.cascade_projection.weighted_avg_price)
                        : "—"}
                    </div>
                  </div>
                  <div>
                    <div className="text-[9px] text-[var(--color-fg-faint)] uppercase">
                      Total expo
                    </div>
                    <div className="num font-semibold text-[var(--color-fg)]">
                      {plan.cascade_projection.total_size_pct_equity}%
                      {equityUsd > 0 && (
                        <span className="text-[9px] text-[var(--color-fg-faint)] ml-1">
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
                    <div className="text-[9px] text-[var(--color-fg-faint)] uppercase">
                      Worst-case rugi
                    </div>
                    <div className="num font-semibold text-[var(--color-danger)]">
                      -{plan.cascade_projection.worst_case_loss_pct_equity}% eq
                    </div>
                  </div>
                </div>
                <div className="text-[9px] text-[var(--color-fg-faint)] leading-snug">
                  {plan.cascade_projection.explanation}
                </div>
              </div>
            )}
          </div>
        )}

        {/* TP ladder dengan PRICE actual */}
        {tpLadder.length > 0 && (
          <div>
            <div className="text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1.5 flex items-center gap-1.5">
              <Layers size={10} /> Take Profit Bertahap (Harga Actual)
            </div>
            <div className="space-y-0.5">
              {tpLadder.map((tp) => (
                <div
                  key={tp.tp}
                  className="grid grid-cols-[44px_80px_60px_1fr] gap-2 items-center text-[10px]"
                >
                  <span className="font-bold text-[var(--color-success)]">
                    TP{tp.tp}
                  </span>
                  <span className="num font-semibold">
                    {tp.price != null ? fmtPrice(tp.price) : "—"}
                  </span>
                  <span className="text-[var(--color-fg-muted)] num text-[9px]">
                    {tp.pct_price > 0 ? "+" : ""}
                    {tp.pct_price}% / {tp.pct_margin_100x}%@100x
                  </span>
                  <span className="text-[var(--color-fg-faint)] text-[9px] truncate">
                    close {tp.close_pct}% · {tp.reason}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {plan.stop_plus_hint && (
          <div className="text-[10px] flex items-start gap-1.5 px-2 py-1.5 rounded bg-[var(--color-accent-soft)] ring-1 ring-[var(--color-accent)]/30">
            <Lock size={10} className="text-[var(--color-accent)] shrink-0 mt-0.5" />
            <span className="text-[var(--color-fg-muted)]">
              <span className="text-[var(--color-accent)] font-semibold">SL+ : </span>
              {plan.stop_plus_hint}
            </span>
          </div>
        )}

        {/* Sizing summary footer */}
        <div className="flex items-center justify-between text-[9px] uppercase tracking-wider pt-1 border-t border-[var(--color-border)]/40">
          <span className="text-[var(--color-fg-faint)]">Skor & Tier Default:</span>
          <span
            className={cn(
              "font-bold",
              score >= 65
                ? "text-[var(--color-success)]"
                : score >= 45
                  ? "text-[var(--color-warning)]"
                  : "text-[var(--color-fg-faint)]",
            )}
          >
            {score} / 100 · default {sizingPct}%
          </span>
        </div>
      </div>
    </div>
  );
}
