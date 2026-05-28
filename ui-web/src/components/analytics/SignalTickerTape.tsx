import { motion } from "motion/react";
import { TrendingUp, TrendingDown, Flame } from "lucide-react";
import type { Signal } from "@/types/position";
import { fmtPrice } from "@/lib/format";

interface Props {
  signals: Signal[] | undefined;
}

/**
 * Marquee-style scrolling ticker of top signals.
 * Premium 80+ get flame icon, alt season hot streak.
 */
export function SignalTickerTape({ signals }: Props) {
  const filtered = (signals ?? [])
    .filter((s) => s.confluence_score >= 50 && s.direction !== "NONE")
    .sort((a, b) => b.confluence_score - a.confluence_score)
    .slice(0, 20);

  if (filtered.length === 0) return null;

  // Duplicate for seamless loop
  const display = [...filtered, ...filtered];

  return (
    <div className="relative overflow-hidden rounded-[var(--radius-md)] bg-gradient-to-r from-black/30 via-black/40 to-black/30 ring-1 ring-[var(--color-border)] py-1.5 mb-3">
      <div className="absolute inset-y-0 left-0 w-12 bg-gradient-to-r from-[var(--color-bg)] to-transparent z-10 pointer-events-none" />
      <div className="absolute inset-y-0 right-0 w-12 bg-gradient-to-l from-[var(--color-bg)] to-transparent z-10 pointer-events-none" />
      <motion.div
        className="flex items-center gap-6 whitespace-nowrap"
        animate={{ x: ["0%", "-50%"] }}
        transition={{ duration: 60, ease: "linear", repeat: Infinity }}
      >
        {display.map((s, i) => {
          const isLong = s.direction === "LONG";
          const tone = isLong ? "var(--color-success)" : "var(--color-danger)";
          const isPremium = s.confluence_score >= 80;
          const Icon = isLong ? TrendingUp : TrendingDown;
          return (
            <div key={`${s.symbol}-${i}`} className="flex items-center gap-2 px-2 text-[11px]">
              {isPremium && <Flame size={11} className="text-[var(--color-warning)] animate-pulse" />}
              <Icon size={11} style={{ color: tone }} />
              <span className="font-bold" style={{ color: tone }}>
                {s.symbol.replace("_USDT", "")}
              </span>
              <span className="num font-bold text-[var(--color-fg)]">{s.confluence_score}</span>
              {s.entry_plan?.entry_price != null && (
                <span className="text-[var(--color-fg-faint)] num text-[10px]">
                  @{fmtPrice(s.entry_plan.entry_price)}
                </span>
              )}
              {s.rr_ratio?.tp2 != null && (
                <span
                  className="text-[9px] num px-1 rounded"
                  style={{
                    color: s.rr_ratio.tp2 >= 2 ? "var(--color-success)" : "var(--color-fg-faint)",
                    background: `color-mix(in oklch, ${s.rr_ratio.tp2 >= 2 ? "var(--color-success)" : "var(--color-fg-faint)"} 12%, transparent)`,
                  }}
                >
                  {s.rr_ratio.tp2.toFixed(1)}R
                </span>
              )}
              <span className="text-[var(--color-fg-faint)]">·</span>
            </div>
          );
        })}
      </motion.div>
    </div>
  );
}
