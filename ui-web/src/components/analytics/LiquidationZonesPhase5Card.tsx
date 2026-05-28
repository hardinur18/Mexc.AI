import { motion } from "motion/react";
import { Bomb, ArrowUp, ArrowDown } from "lucide-react";
import type { LiquidationZones } from "@/types/position";
import { fmtPrice, fmt } from "@/lib/format";

interface Props {
  zones: LiquidationZones | null | undefined;
  currentPrice?: number | null;
}

/**
 * Visualizes leverage-tier liquidation clusters around current price.
 * Mock-style: vertical price axis, bars showing estimated cluster size.
 */
export function LiquidationZonesPhase5Card({ zones, currentPrice }: Props) {
  if (!zones) return null;
  const longs = zones.long_clusters;
  const shorts = zones.short_clusters;
  // Find max value for bar scaling
  const allValues = [...longs, ...shorts]
    .map((c) => c.est_value_usdt || 0)
    .filter((v) => v > 0);
  const maxVal = allValues.length > 0 ? Math.max(...allValues) : 1;

  const dominantSide = zones.dominant_side;
  const longShare = zones.long_share_estimate;

  return (
    <div className="lift rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] overflow-hidden">
      <div className="px-3 py-2 flex items-center gap-2 border-b border-[var(--color-border)]/50">
        <Bomb size={11} className="text-[var(--color-warning)]" />
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
          Liquidation Map (est)
        </span>
        <span className="text-[9px] text-[var(--color-fg-faint)] ml-auto">
          per leverage tier · {zones.dominant_side} dominant
        </span>
      </div>

      <div className="p-3">
        {/* Dominant side gauge */}
        <div className="mb-3">
          <div className="flex items-center justify-between text-[9px] mb-1">
            <span className="text-[var(--color-success)] num font-semibold">
              {longShare.toFixed(0)}% longs
            </span>
            <span className="text-[var(--color-fg-faint)] uppercase tracking-wider">
              positioning bias
            </span>
            <span className="text-[var(--color-danger)] num font-semibold">
              {(100 - longShare).toFixed(0)}% shorts
            </span>
          </div>
          <div className="relative h-1.5 rounded-full overflow-hidden bg-white/5">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${longShare}%` }}
              transition={{ duration: 0.5, ease: [0.34, 1.4, 0.4, 1] }}
              className="absolute inset-y-0 left-0 bg-[var(--color-success)]"
            />
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${100 - longShare}%` }}
              transition={{ duration: 0.5, ease: [0.34, 1.4, 0.4, 1] }}
              className="absolute inset-y-0 right-0 bg-[var(--color-danger)]"
            />
          </div>
          <div className="text-[8px] text-[var(--color-fg-faint)] mt-1 text-center">
            {dominantSide === "longs"
              ? "longs piled up — risiko long squeeze ke bawah"
              : dominantSide === "shorts"
                ? "shorts piled up — risiko short squeeze ke atas"
                : "balanced — no clear squeeze setup"}
          </div>
        </div>

        {/* Short clusters (above current) */}
        <div className="space-y-px mb-1">
          {shorts
            .slice()
            .reverse()
            .map((c, i) => (
              <ClusterRow
                key={`s-${i}`}
                cluster={c}
                maxVal={maxVal}
                tone="var(--color-danger)"
                side="short"
              />
            ))}
        </div>

        {/* Current price marker */}
        {currentPrice != null && (
          <div className="flex items-center justify-between px-1 py-1 my-1 rounded bg-[var(--color-accent-soft)] border-y border-[var(--color-accent)]/40">
            <span className="text-[9px] uppercase tracking-wider text-[var(--color-accent)] font-bold">
              MARK
            </span>
            <span className="text-[10px] num font-bold text-[var(--color-accent)]">
              {fmtPrice(currentPrice)}
            </span>
          </div>
        )}

        {/* Long clusters (below current) */}
        <div className="space-y-px mt-1">
          {longs.map((c, i) => (
            <ClusterRow
              key={`l-${i}`}
              cluster={c}
              maxVal={maxVal}
              tone="var(--color-success)"
              side="long"
            />
          ))}
        </div>

        <div className="mt-2.5 text-[8px] text-[var(--color-fg-faint)] text-center">
          Estimasi cluster berdasarkan OI dominansi + tier leverage 100x/50x/25x/10x.
          Tidak akurat 1:1 dengan exchange — gunakan sebagai proxy.
        </div>
      </div>
    </div>
  );
}

function ClusterRow({
  cluster,
  maxVal,
  tone,
  side,
}: {
  cluster: import("@/types/position").LiquidationZoneCluster;
  maxVal: number;
  tone: string;
  side: "long" | "short";
}) {
  const w = cluster.est_value_usdt ? (cluster.est_value_usdt / maxVal) * 100 : 5;
  const Icon = side === "long" ? ArrowDown : ArrowUp;
  return (
    <div className="relative flex items-center text-[9px] num gap-2 px-1 py-px">
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${w}%` }}
        transition={{ duration: 0.4, ease: [0.34, 1.4, 0.4, 1] }}
        className="absolute top-0 bottom-0 left-0 rounded"
        style={{
          background: `color-mix(in oklch, ${tone} 18%, transparent)`,
        }}
      />
      <Icon size={9} style={{ color: tone, position: "relative", zIndex: 1 }} />
      <span className="relative z-10 num font-semibold" style={{ color: tone }}>
        {fmtPrice(cluster.price)}
      </span>
      <span className="relative z-10 text-[8px] text-[var(--color-fg-muted)]">
        {cluster.lev}x
      </span>
      <span className="relative z-10 ml-auto text-[8px] text-[var(--color-fg-muted)] num">
        ~${cluster.est_value_usdt ? fmt(cluster.est_value_usdt / 1000, 1) + "K" : "—"}
      </span>
      <span className="relative z-10 text-[8px] text-[var(--color-fg-faint)] num">
        {cluster.pct_from_current > 0 ? "+" : ""}
        {cluster.pct_from_current.toFixed(2)}%
      </span>
    </div>
  );
}
