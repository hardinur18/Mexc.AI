import { motion } from "motion/react";
import { Layers3 } from "lucide-react";
import type { OrderbookHeatmap } from "@/types/position";
import { fmtPrice, fmt } from "@/lib/format";

interface Props {
  data: OrderbookHeatmap | null | undefined;
}

/** Bid/ask wall visualization with mid spread + cumulative depth bars. */
export function OrderBookHeatmapCard({ data }: Props) {
  if (!data) return null;
  const asks = [...(data.asks_top ?? [])].slice(0, 14).reverse();
  const bids = (data.bids_top ?? []).slice(0, 14);
  const allLevels = [...asks, ...bids];
  if (allLevels.length === 0) return null;
  const maxVol = Math.max(...allLevels.map((l) => l.volume), 1);
  const totalRatio =
    data.bid_total_vol + data.ask_total_vol > 0
      ? (data.bid_total_vol / (data.bid_total_vol + data.ask_total_vol)) * 100
      : 50;

  return (
    <div className="inner-card overflow-hidden">
      <div className="ui-panel-header px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <span className="ui-icon-chip" style={{ color: "var(--color-accent)" }}>
            <Layers3 size={13} />
          </span>
          <span className="ui-section-title">Order Book Heatmap</span>
        </div>
        <span className="text-[11px] text-[var(--color-fg-faint)]">walls · spread {data.spread_pct.toFixed(3)}%</span>
      </div>

      <div className="px-4 py-4">
        {/* Asks */}
        <div className="space-y-px mb-1">
          {asks.map((lv, i) => (
            <Row
              key={`a-${i}`}
              price={lv.price}
              volume={lv.volume}
              maxVol={maxVol}
              tone="var(--color-danger)"
              side="ask"
            />
          ))}
        </div>

        {/* Mid */}
        <div className="flex items-center justify-between px-1 py-1 my-1 rounded bg-white/[0.04] border-y border-[var(--color-border)]/50">
          <span className="text-[9px] text-[var(--color-fg-faint)] uppercase tracking-wider">
            spread
          </span>
          <span className="text-[10px] num font-bold">
            <span className="text-[var(--color-success)]">{fmtPrice(data.best_bid)}</span>{" "}
            <span className="text-[var(--color-fg-faint)]">|</span>{" "}
            <span className="text-[var(--color-danger)]">{fmtPrice(data.best_ask)}</span>
          </span>
        </div>

        {/* Bids */}
        <div className="space-y-px mt-1">
          {bids.map((lv, i) => (
            <Row
              key={`b-${i}`}
              price={lv.price}
              volume={lv.volume}
              maxVol={maxVol}
              tone="var(--color-success)"
              side="bid"
            />
          ))}
        </div>

        {/* Cumulative bias bar */}
        <div className="mt-2 pt-2 border-t border-[var(--color-border)]/40">
          <div className="flex items-center justify-between text-[9px] mb-1">
            <span className="text-[var(--color-success)] num font-semibold">
              ↑ {fmt(data.bid_total_vol, 0)} bids
            </span>
            <span className="text-[var(--color-fg-faint)] uppercase tracking-wider">
              cumulative
            </span>
            <span className="text-[var(--color-danger)] num font-semibold">
              {fmt(data.ask_total_vol, 0)} asks ↓
            </span>
          </div>
          <div className="relative h-1.5 rounded-full overflow-hidden bg-[var(--color-surface)]">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${totalRatio}%` }}
              transition={{ duration: 0.5, ease: [0.34, 1.4, 0.4, 1] }}
              className="absolute inset-y-0 left-0 bg-[var(--color-success)]"
            />
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${100 - totalRatio}%` }}
              transition={{ duration: 0.5, ease: [0.34, 1.4, 0.4, 1] }}
              className="absolute inset-y-0 right-0 bg-[var(--color-danger)]"
            />
          </div>
          <div className="text-[8px] text-[var(--color-fg-faint)] mt-1 text-center">
            {totalRatio > 60
              ? "buy pressure dominan"
              : totalRatio < 40
                ? "sell pressure dominan"
                : "balanced"}
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({
  price,
  volume,
  maxVol,
  tone,
  side,
}: {
  price: number;
  volume: number;
  maxVol: number;
  tone: string;
  side: "ask" | "bid";
}) {
  const w = (volume / maxVol) * 100;
  return (
    <div className="relative flex items-center text-[9px] num">
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${w}%` }}
        transition={{ duration: 0.3, ease: [0.34, 1.4, 0.4, 1] }}
        className={`absolute top-0 bottom-0 ${side === "ask" ? "left-0" : "left-0"} rounded`}
        style={{
          background: `color-mix(in oklch, ${tone} 18%, transparent)`,
        }}
      />
      <span className="relative z-10 flex-1 px-2 py-px" style={{ color: tone }}>
        {fmtPrice(price)}
      </span>
      <span className="relative z-10 text-[var(--color-fg-muted)] px-2 py-px">
        {fmt(volume, 0)}
      </span>
    </div>
  );
}
