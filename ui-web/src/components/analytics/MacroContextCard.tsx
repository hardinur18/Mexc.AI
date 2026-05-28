import { motion } from "motion/react";
import { Globe, TrendingUp, TrendingDown } from "lucide-react";
import type { SymbolAnalytics } from "@/types/position";
import { fmtPct } from "@/lib/format";

interface Props {
  a: Partial<SymbolAnalytics> | null | undefined;
}

/**
 * Macro context: Long/Short ratio + funding 7d avg + OI history sparkline + Long/Short ratio history.
 * Reads what the leveraged crowd is doing.
 */
export function MacroContextCard({ a }: Props) {
  if (!a) return null;
  const lsr = a.long_short_ratio;
  const lsrHist = a.long_short_ratio_history ?? [];
  const oiHist = a.oi_history_api ?? [];
  const fundingNow = a.funding_rate_pct;
  const funding7d = a.funding_rate_7d_avg;

  // Pick the best L/S ratio metric available
  const lsrVal = lsr
    ? Number(lsr.longShortRatio ?? lsr.longRatio ?? 0)
    : null;
  const longPct =
    lsr && lsr.longRatio != null
      ? Number(lsr.longRatio) * 100
      : lsrVal != null
        ? (lsrVal / (1 + lsrVal)) * 100
        : null;

  const fundingTone =
    fundingNow == null
      ? "var(--color-fg-muted)"
      : fundingNow > 0.03
        ? "var(--color-danger)"
        : fundingNow < -0.03
          ? "var(--color-success)"
          : "var(--color-fg-muted)";

  return (
    <div className="inner-card overflow-hidden">
      <div className="ui-panel-header px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <span className="ui-icon-chip" style={{ color: "var(--color-accent)" }}>
            <Globe size={13} />
          </span>
          <span className="ui-section-title">Konteks Makro</span>
        </div>
        <span className="text-[11px] text-[var(--color-fg-faint)]">
          posisi crowd & funding flow
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3 px-4 py-4">
        {/* Long/Short Ratio */}
        <div className="ui-subcard px-3 py-2.5">
          <div className="text-[10px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1">
            Long/Short
          </div>
          {longPct != null ? (
            <>
              <div className="flex items-baseline gap-1">
                <span
                  className="text-base font-bold num leading-none"
                  style={{
                    color:
                      longPct > 65
                        ? "var(--color-warning)"
                        : longPct < 35
                          ? "var(--color-warning)"
                          : "var(--color-success)",
                  }}
                >
                  {longPct.toFixed(0)}%
                </span>
                <span className="text-[9px] text-[var(--color-fg-faint)]">
                  long
                </span>
              </div>
              <div className="relative h-1 mt-1.5 rounded-full overflow-hidden bg-[var(--color-surface)]">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${longPct}%` }}
                  transition={{ duration: 0.5, ease: [0.34, 1.4, 0.4, 1] }}
                  className="absolute inset-y-0 left-0 bg-[var(--color-success)]"
                />
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${100 - longPct}%` }}
                  transition={{ duration: 0.5, ease: [0.34, 1.4, 0.4, 1] }}
                  className="absolute inset-y-0 right-0 bg-[var(--color-danger)]"
                />
              </div>
              <div className="text-[8px] text-[var(--color-fg-faint)] mt-1">
                {longPct > 70 && "⚠ long crowded — risk squeeze"}
                {longPct < 30 && "⚠ short crowded — risk squeeze"}
                {longPct >= 30 && longPct <= 70 && "seimbang"}
              </div>
            </>
          ) : (
            <span className="text-[10px] text-[var(--color-fg-faint)]">—</span>
          )}
        </div>

        {/* Funding Now + 7d avg */}
        <div className="ui-subcard px-2.5 py-2">
          <div className="text-[10px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1">
            Funding
          </div>
          {fundingNow != null ? (
            <>
              <div
                className="text-base font-bold num leading-none"
                style={{ color: fundingTone }}
              >
                {fmtPct(fundingNow)}
              </div>
              <div className="text-[8px] text-[var(--color-fg-faint)] mt-1">
                7d avg{" "}
                <span className="num font-semibold text-[var(--color-fg-muted)]">
                  {funding7d != null ? fmtPct(funding7d) : "—"}
                </span>
              </div>
              <div className="text-[8px] text-[var(--color-fg-faint)] mt-0.5">
                {(fundingNow ?? 0) > 0.05 && "longs bayar short — bearish"}
                {(fundingNow ?? 0) < -0.05 && "shorts bayar long — bullish"}
                {Math.abs(fundingNow ?? 0) <= 0.05 && "neutral"}
              </div>
            </>
          ) : (
            <span className="text-[10px] text-[var(--color-fg-faint)]">—</span>
          )}
        </div>

        {/* OI history sparkline */}
        <div className="ui-subcard px-2.5 py-2">
          <div className="text-[10px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1">
            Open Interest
          </div>
          <OiSpark history={oiHist} />
          {oiHist.length > 0 && (
            <div className="text-[8px] text-[var(--color-fg-faint)] mt-1">
              {(() => {
                const first = Number(oiHist[0]?.holdVol ?? 0);
                const last = Number(oiHist[oiHist.length - 1]?.holdVol ?? 0);
                if (first <= 0) return "—";
                const chg = ((last - first) / first) * 100;
                return (
                  <span style={{ color: chg > 0 ? "var(--color-success)" : "var(--color-danger)" }}>
                    {chg > 0 ? "+" : ""}
                    {chg.toFixed(1)}% (8h)
                  </span>
                );
              })()}
            </div>
          )}
        </div>
      </div>

      {/* L/S history mini stack */}
      {lsrHist.length > 1 && (
        <div className="px-4 pb-3">
          <div className="text-[11px] uppercase tracking-wider text-[var(--color-fg-faint)] font-medium mb-1.5">
            Tren long/short 7h terakhir
          </div>
          <div className="flex h-1.5 gap-px rounded-full overflow-hidden">
            {lsrHist.slice(-24).map((sample, i) => {
              const r = Number(sample?.longRatio ?? 0);
              const pct = r > 0 ? r * 100 : 50;
              return (
                <motion.div
                  key={i}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.3, delay: i * 0.01 }}
                  className="flex-1 flex flex-col"
                  title={`Long ${pct.toFixed(0)}%`}
                >
                  <div
                    className="bg-[var(--color-success)]"
                    style={{ height: `${pct}%` }}
                  />
                  <div
                    className="bg-[var(--color-danger)]"
                    style={{ height: `${100 - pct}%` }}
                  />
                </motion.div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function OiSpark({ history }: { history: { holdVol?: number; [k: string]: unknown }[] }) {
  if (!history || history.length < 2) {
    return <span className="text-[10px] text-[var(--color-fg-faint)]">—</span>;
  }
  const vols = history.map((h) => Number(h?.holdVol ?? 0));
  const max = Math.max(...vols);
  const min = Math.min(...vols);
  if (max <= min) {
    return <span className="text-[10px] text-[var(--color-fg-faint)]">flat</span>;
  }
  const pts = vols
    .map((v, i) => {
      const x = (i / (vols.length - 1)) * 100;
      const y = 28 - ((v - min) / (max - min)) * 24;
      return `${x},${y}`;
    })
    .join(" ");
  const trend = vols[vols.length - 1] - vols[0];
  const Icon = trend > 0 ? TrendingUp : TrendingDown;
  const tone = trend > 0 ? "var(--color-success)" : "var(--color-danger)";
  return (
    <div className="flex items-center gap-1.5">
      <svg width="60" height="28" viewBox="0 0 100 28" preserveAspectRatio="none" className="flex-1">
        <polyline
          points={pts}
          fill="none"
          stroke={tone}
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <Icon size={10} style={{ color: tone }} />
    </div>
  );
}
