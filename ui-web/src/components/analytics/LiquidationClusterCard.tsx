import { motion } from "motion/react";
import { Bomb, AlertTriangle } from "lucide-react";
import type { LiquidationCluster } from "@/types/position";

interface Props {
  data: LiquidationCluster | null | undefined;
}

export function LiquidationClusterCard({ data }: Props) {
  if (!data) return null;
  if (!data.detected) {
    return (
      <div className="rounded-[var(--radius-md)] inner-card px-3 py-2.5">
        <div className="flex items-center gap-2">
          <Bomb size={11} className="text-[var(--color-fg-muted)]" />
          <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
            Liquidation Cluster
          </span>
          <span className="text-[9px] text-[var(--color-fg-faint)] ml-auto">
            tidak terdeteksi
          </span>
        </div>
        {data.oi_surge_pct != null && (
          <div className="text-[9px] text-[var(--color-fg-faint)] mt-1.5">
            OI 5h:{" "}
            <span className="num text-[var(--color-fg-muted)]">
              {data.oi_surge_pct > 0 ? "+" : ""}
              {data.oi_surge_pct.toFixed(1)}%
            </span>
            {data.range_pct != null && (
              <>
                {" "}
                · range 5h:{" "}
                <span className="num text-[var(--color-fg-muted)]">
                  {data.range_pct.toFixed(2)}%
                </span>
              </>
            )}
          </div>
        )}
      </div>
    );
  }
  const tone =
    data.side === "long_squeeze"
      ? "var(--color-danger)"
      : "var(--color-success)";
  const title =
    data.side === "long_squeeze"
      ? "Long Squeeze Setup"
      : "Short Squeeze Setup";
  const subtitle =
    data.side === "long_squeeze"
      ? "Longs piled up + tight compression — risk break DOWN dengan cascade"
      : "Shorts piled up + tight compression — risk break UP dengan cascade";

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
      className="rounded-[var(--radius-md)] ring-1 overflow-hidden"
      style={{
        background: `color-mix(in oklch, ${tone} 10%, transparent)`,
        borderColor: `color-mix(in oklch, ${tone} 40%, transparent)`,
        boxShadow: `0 0 12px color-mix(in oklch, ${tone} 20%, transparent)`,
      }}
    >
      <div className="px-3 py-2 flex items-center gap-2 border-b border-[var(--color-border)]/50">
        <AlertTriangle size={11} style={{ color: tone }} className="[animation:pulse-glow_2s_ease-in-out_infinite]" />
        <span className="text-[10px] uppercase tracking-wider font-bold" style={{ color: tone }}>
          {title}
        </span>
      </div>
      <div className="p-4 space-y-2">
        <div className="text-[10px] text-[var(--color-fg-muted)] leading-snug">{subtitle}</div>
        <div className="grid grid-cols-3 gap-2 text-[9px]">
          <Metric
            label="OI surge 5h"
            value={
              data.oi_surge_pct != null
                ? `${data.oi_surge_pct > 0 ? "+" : ""}${data.oi_surge_pct.toFixed(1)}%`
                : "—"
            }
            tone={tone}
          />
          <Metric
            label="Range 5h"
            value={data.range_pct != null ? `${data.range_pct.toFixed(2)}%` : "—"}
            tone="var(--color-fg-muted)"
          />
          <Metric
            label="Funding"
            value={
              data.funding_extreme === "long_crowded"
                ? "long crowded"
                : data.funding_extreme === "short_crowded"
                  ? "short crowded"
                  : "—"
            }
            tone={tone}
          />
        </div>
      </div>
    </motion.div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="rounded-[var(--radius-sm)] bg-white/[0.04] px-2 py-1.5">
      <div className="text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)]">
        {label}
      </div>
      <div className="text-[10px] num font-bold mt-0.5" style={{ color: tone }}>
        {value}
      </div>
    </div>
  );
}
