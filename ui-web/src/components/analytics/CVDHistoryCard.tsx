import { motion } from "motion/react";
import { Activity, AlertTriangle } from "lucide-react";
import type { CVDHistorical } from "@/types/position";
import { fmt, fmtPrice } from "@/lib/format";

interface Props {
  data: CVDHistorical | null | undefined;
}

/**
 * Cumulative Volume Delta history — dual line (price white + CVD cyan)
 * with proper dual-axis normalization + divergence/absorption alerts.
 */
export function CVDHistoryCard({ data }: Props) {
  if (!data || !data.history || data.history.length < 2) return null;
  const history = data.history;
  const cvds = history.map((h) => h.cvd);
  const prices = history.map((h) => h.price_close);
  const maxCvd = Math.max(...cvds);
  const minCvd = Math.min(...cvds);
  const rangeCvd = maxCvd - minCvd || 1;
  const maxPrice = Math.max(...prices);
  const minPrice = Math.min(...prices);
  const rangePrice = maxPrice - minPrice || 1;

  const W = 100;
  const H = 60;
  const PAD_TOP = 6;
  const PAD_BOT = 6;
  const usableH = H - PAD_TOP - PAD_BOT;
  const xStep = W / (history.length - 1);

  const buildPath = (vals: number[], min: number, range: number) =>
    vals
      .map((v, i) => {
        const x = i * xStep;
        const y = PAD_TOP + usableH * (1 - (v - min) / range);
        return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ");

  const pricePath = buildPath(prices, minPrice, rangePrice);
  const cvdPath = buildPath(cvds, minCvd, rangeCvd);

  // Zero baseline for CVD (where CVD = 0 maps to on y-axis)
  const zeroY = minCvd < 0 && maxCvd > 0
    ? PAD_TOP + usableH * (1 - (0 - minCvd) / rangeCvd)
    : null;

  return (
    <div className="inner-card overflow-hidden">
      <div className="ui-panel-header px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <span className="ui-icon-chip" style={{ color: "var(--color-accent)" }}>
            <Activity size={13} />
          </span>
          <span className="ui-section-title">CVD History</span>
        </div>
        <span className="text-[11px] text-[var(--color-fg-faint)]">delta cumulative · {history.length} bars 1h</span>
      </div>

      <div className="px-4 py-4">
        {/* Legend + axis labels */}
        <div className="flex items-center justify-between text-[9px] mb-1.5">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1 text-[var(--color-fg-muted)]">
              <span className="inline-block w-2.5 h-0.5 bg-white/70" /> Price
            </span>
            <span className="flex items-center gap-1 text-[var(--color-accent)]">
              <span className="inline-block w-2.5 h-0.5" style={{ background: "var(--color-accent)" }} /> CVD
            </span>
          </div>
          <div className="text-[var(--color-fg-faint)] num">
            {fmtPrice(minPrice)} → {fmtPrice(maxPrice)}
          </div>
        </div>

        {/* Chart */}
        <div className="relative bg-[var(--color-bg-elev-2)] rounded-[var(--radius-sm)] ring-1 ring-[var(--color-border)]/40 overflow-hidden">
          <svg
            width="100%"
            height="130"
            viewBox={`0 0 ${W} ${H}`}
            preserveAspectRatio="none"
            className="block"
          >
            {/* Zero baseline for CVD */}
            {zeroY != null && (
              <line
                x1="0"
                y1={zeroY}
                x2={W}
                y2={zeroY}
                stroke="var(--color-accent)"
                strokeWidth="0.2"
                strokeDasharray="0.6 0.6"
                opacity="0.3"
                vectorEffect="non-scaling-stroke"
              />
            )}

            {/* Grid horizontals (3 lines) */}
            {[0.25, 0.5, 0.75].map((p, i) => (
              <line
                key={i}
                x1="0"
                y1={PAD_TOP + usableH * p}
                x2={W}
                y2={PAD_TOP + usableH * p}
                stroke="var(--color-border)"
                strokeWidth="0.15"
                opacity="0.5"
                vectorEffect="non-scaling-stroke"
              />
            ))}

            {/* CVD path (cyan, behind) */}
            <motion.path
              d={cvdPath}
              fill="none"
              stroke="var(--color-accent)"
              strokeWidth="1.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5 }}
            />

            {/* Price path (white, in front) */}
            <motion.path
              d={pricePath}
              fill="none"
              stroke="rgba(255,255,255,0.85)"
              strokeWidth="1.0"
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5, delay: 0.15 }}
            />
          </svg>
        </div>

        {/* Divergence alert */}
        {data.divergence && (
          <motion.div
            initial={{ opacity: 0, y: -2 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-2 flex items-start gap-2 px-2 py-1.5 rounded ring-1"
            style={{
              background: `color-mix(in oklch, ${data.divergence.type === "bullish" ? "var(--color-success)" : "var(--color-danger)"} 10%, transparent)`,
              borderColor: `color-mix(in oklch, ${data.divergence.type === "bullish" ? "var(--color-success)" : "var(--color-danger)"} 30%, transparent)`,
            }}
          >
            <AlertTriangle
              size={11}
              style={{
                color:
                  data.divergence.type === "bullish"
                    ? "var(--color-success)"
                    : "var(--color-danger)",
              }}
              className="mt-0.5 shrink-0"
            />
            <div className="leading-tight">
              <div
                className="text-[10px] font-bold uppercase tracking-wider"
                style={{
                  color:
                    data.divergence.type === "bullish"
                      ? "var(--color-success)"
                      : "var(--color-danger)",
                }}
              >
                {data.divergence.type} divergence
              </div>
              <div className="text-[9px] text-[var(--color-fg-muted)] mt-0.5">
                {data.divergence.detail}
              </div>
            </div>
          </motion.div>
        )}

        {/* Absorption alert */}
        {data.absorption?.detected && (
          <motion.div
            initial={{ opacity: 0, y: -2 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-2 flex items-start gap-2 px-2 py-1.5 rounded ring-1"
            style={{
              background: "color-mix(in oklch, var(--color-warning) 10%, transparent)",
              borderColor: "color-mix(in oklch, var(--color-warning) 30%, transparent)",
            }}
          >
            <AlertTriangle
              size={11}
              style={{ color: "var(--color-warning)" }}
              className="mt-0.5 shrink-0"
            />
            <div className="leading-tight">
              <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-warning)]">
                Absorption: {data.absorption.side}
              </div>
              <div className="text-[9px] text-[var(--color-fg-muted)] mt-0.5">
                {data.absorption.detail} · delta {fmt(data.absorption.delta, 0)}
              </div>
            </div>
          </motion.div>
        )}

        {/* Footer metrics */}
        <div className="mt-2 flex items-center justify-between text-[9px]">
          <span className="text-[var(--color-fg-faint)]">
            CVD range:{" "}
            <span className="num text-[var(--color-fg-muted)]">
              {fmt(minCvd, 0)} → {fmt(maxCvd, 0)}
            </span>
          </span>
          <span className="text-[var(--color-fg-faint)]">
            Current:{" "}
            <span
              className="num font-bold"
              style={{
                color:
                  data.current_cvd > 0
                    ? "var(--color-success)"
                    : data.current_cvd < 0
                      ? "var(--color-danger)"
                      : "var(--color-fg-muted)",
              }}
            >
              {data.current_cvd > 0 ? "+" : ""}
              {fmt(data.current_cvd, 0)}
            </span>
          </span>
        </div>
      </div>
    </div>
  );
}
