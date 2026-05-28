import { motion } from "motion/react";
import { Activity, ArrowUp, ArrowDown } from "lucide-react";
import type { CumulativeDelta } from "@/types/position";
import { fmt } from "@/lib/format";

interface Props {
  data: CumulativeDelta | null | undefined;
}

/** Buy vs Sell pressure from last 100 trades. */
export function CumulativeDeltaCard({ data }: Props) {
  if (!data) return null;
  const tone =
    data.bias === "buy"
      ? "var(--color-success)"
      : data.bias === "sell"
        ? "var(--color-danger)"
        : "var(--color-fg-muted)";
  const Icon = data.bias === "buy" ? ArrowUp : data.bias === "sell" ? ArrowDown : Activity;
  return (
    <div className="inner-card overflow-hidden">
      <div className="ui-panel-header px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <span className="ui-icon-chip" style={{ color: "var(--color-accent)" }}>
            <Activity size={13} />
          </span>
          <span className="ui-section-title">Cumulative Delta</span>
        </div>
        <span className="text-[11px] text-[var(--color-fg-faint)]">last 100 trades flow</span>
      </div>
      <div className="px-4 py-4">
        <div className="flex items-baseline gap-2 mb-2">
          <Icon size={14} style={{ color: tone }} />
          <span className="text-base font-bold num leading-none" style={{ color: tone }}>
            {data.buy_pct.toFixed(0)}%
          </span>
          <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-faint)]">
            buy aggression
          </span>
          <span className="text-[9px] num text-[var(--color-fg-muted)] ml-auto">
            Δ {fmt(data.delta, 2)}
          </span>
        </div>
        <div className="relative h-1.5 rounded-full overflow-hidden bg-[var(--color-surface)]">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${data.buy_pct}%` }}
            transition={{ duration: 0.5, ease: [0.34, 1.4, 0.4, 1] }}
            className="absolute inset-y-0 left-0 bg-[var(--color-success)]"
          />
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${100 - data.buy_pct}%` }}
            transition={{ duration: 0.5, ease: [0.34, 1.4, 0.4, 1] }}
            className="absolute inset-y-0 right-0 bg-[var(--color-danger)]"
          />
        </div>
        <div className="flex items-center justify-between mt-1.5 text-[9px] num">
          <span className="text-[var(--color-success)]">
            buy {fmt(data.buy_vol, 2)}
          </span>
          <span className="text-[var(--color-danger)]">
            sell {fmt(data.sell_vol, 2)}
          </span>
        </div>
      </div>
    </div>
  );
}
