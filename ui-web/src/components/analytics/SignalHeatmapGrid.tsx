import { useMemo, useState } from "react";
import { motion } from "motion/react";
import { Grid3x3, TrendingUp, TrendingDown } from "lucide-react";
import type { Signal } from "@/types/position";

interface Props {
  signals: Signal[] | undefined;
  onSelect?: (symbol: string) => void;
}

/**
 * Grid heatmap of all signals colored by direction × score.
 * Bigger tiles for higher score.
 */
export function SignalHeatmapGrid({ signals, onSelect }: Props) {
  const [filter, setFilter] = useState<"ALL" | "LONG" | "SHORT">("ALL");

  const filtered = useMemo(() => {
    if (!signals) return [];
    let list = signals.filter((s) => s.direction !== "NONE");
    if (filter !== "ALL") list = list.filter((s) => s.direction === filter);
    return list.sort((a, b) => b.confluence_score - a.confluence_score);
  }, [signals, filter]);

  if (filtered.length === 0) return null;

  return (
    <div className="lift rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] overflow-hidden">
      <div className="px-3 py-2 flex items-center gap-2 border-b border-[var(--color-border)]/50">
        <Grid3x3 size={11} className="text-[var(--color-accent)]" />
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
          Heatmap Sinyal
        </span>
        <div className="ml-auto flex items-center gap-1">
          {(["ALL", "LONG", "SHORT"] as const).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setFilter(k)}
              className={
                "text-[9px] px-1.5 py-0.5 rounded uppercase tracking-wider transition " +
                (filter === k
                  ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)] ring-1 ring-[var(--color-accent)]/30"
                  : "text-[var(--color-fg-subtle)] hover:text-[var(--color-fg)]")
              }
            >
              {k === "ALL" ? "Semua" : k}
            </button>
          ))}
        </div>
      </div>

      <div className="p-3 grid grid-cols-4 sm:grid-cols-6 lg:grid-cols-8 xl:grid-cols-10 gap-1.5">
        {filtered.map((s, i) => {
          const isLong = s.direction === "LONG";
          const tone = isLong ? "var(--color-success)" : "var(--color-danger)";
          const intensity = Math.min(100, Math.max(20, s.confluence_score)) / 100;
          const isPremium = s.confluence_score >= 80;
          return (
            <motion.button
              key={s.symbol}
              type="button"
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{
                duration: 0.3,
                delay: Math.min(i, 30) * 0.015,
                ease: [0.34, 1.4, 0.4, 1],
              }}
              whileHover={{ scale: 1.06, zIndex: 5 }}
              onClick={() => onSelect?.(s.symbol)}
              className="relative aspect-square rounded-[var(--radius-sm)] ring-1 p-1.5 flex flex-col items-center justify-center text-center transition cursor-pointer"
              style={{
                background: `color-mix(in oklch, ${tone} ${intensity * 30}%, transparent)`,
                borderColor: `color-mix(in oklch, ${tone} ${intensity * 60}%, transparent)`,
                boxShadow: isPremium ? `0 0 12px color-mix(in oklch, ${tone} 40%, transparent)` : "none",
              }}
              title={`${s.symbol} · ${s.direction} · ${s.confluence_score}`}
            >
              {isLong ? (
                <TrendingUp size={9} style={{ color: tone }} />
              ) : (
                <TrendingDown size={9} style={{ color: tone }} />
              )}
              <span className="text-[9px] font-bold truncate w-full" style={{ color: tone }}>
                {s.symbol.replace("_USDT", "")}
              </span>
              <span className="text-[11px] font-bold num leading-none" style={{ color: tone }}>
                {s.confluence_score}
              </span>
              {isPremium && (
                <span
                  className="absolute -top-1 -right-1 text-[8px] w-3.5 h-3.5 flex items-center justify-center rounded-full font-bold"
                  style={{ background: "var(--color-warning)", color: "black" }}
                >
                  ★
                </span>
              )}
            </motion.button>
          );
        })}
      </div>
      <div className="px-3 pb-2 text-[8px] text-[var(--color-fg-faint)] text-center">
        {filtered.length} sinyal · klik tile untuk detail
      </div>
    </div>
  );
}
