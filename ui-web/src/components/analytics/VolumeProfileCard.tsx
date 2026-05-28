import { motion } from "motion/react";
import { BarChart3 } from "lucide-react";
import type { VolumeProfileData } from "@/types/position";
import { fmtPrice } from "@/lib/format";

interface Props {
  data: VolumeProfileData | null | undefined;
  currentPrice?: number | null;
  height?: number;
}

/**
 * Horizontal volume profile with POC/VAH/VAL markers.
 * Bars grow left-to-right; price increases bottom-to-top.
 */
export function VolumeProfileCard({ data, currentPrice, height = 220 }: Props) {
  if (!data || !data.histogram || data.histogram.length === 0 || data.poc == null) {
    return null;
  }

  const bins = data.histogram;
  const maxVol = Math.max(...bins.map((b) => b.volume), 1);
  const lo = data.range_low;
  const hi = data.range_high;
  const range = hi - lo || 1;

  return (
    <div className="inner-card overflow-hidden">
      <div className="ui-panel-header px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <span className="ui-icon-chip" style={{ color: "var(--color-accent)" }}>
            <BarChart3 size={13} />
          </span>
          <span className="ui-section-title">Volume Profile</span>
        </div>
        <span className="text-[11px] text-[var(--color-fg-faint)]">POC · VAH · VAL · HVN</span>
      </div>

      <div className="flex gap-2 px-4 py-4">
        {/* Histogram */}
        <div className="relative" style={{ width: 110, height }}>
          {bins.map((b, i) => {
            const w = (b.volume / maxVol) * 100;
            const isPoc = data.poc != null && Math.abs(b.price - data.poc) < range / bins.length;
            const inValueArea =
              data.val != null && data.vah != null && b.price >= data.val && b.price <= data.vah;
            return (
              <motion.div
                key={i}
                initial={{ width: 0 }}
                animate={{ width: `${w}%` }}
                transition={{ duration: 0.4, delay: i * 0.01, ease: [0.34, 1.4, 0.4, 1] }}
                className="absolute left-0"
                style={{
                  bottom: (i / bins.length) * height,
                  height: height / bins.length,
                  background: isPoc
                    ? "var(--color-warning)"
                    : inValueArea
                      ? "color-mix(in oklch, var(--color-accent) 50%, transparent)"
                      : "color-mix(in oklch, var(--color-fg-muted) 30%, transparent)",
                }}
                title={`${fmtPrice(b.price)} · ${b.volume.toFixed(0)} (${b.ratio.toFixed(1)}×)`}
              />
            );
          })}

          {/* Current price line */}
          {currentPrice != null && (
            <div
              className="absolute left-0 right-0 h-px"
              style={{
                bottom: ((currentPrice - lo) / range) * height,
                background: "var(--color-accent)",
                boxShadow: "0 0 4px var(--color-accent)",
              }}
            />
          )}
        </div>

        {/* Labels & values */}
        <div className="flex-1 flex flex-col justify-between py-1 text-[9px]">
          <Marker
            label="VAH"
            price={data.vah}
            tone="var(--color-accent)"
            hint="value area high"
          />
          <Marker
            label="POC"
            price={data.poc}
            tone="var(--color-warning)"
            hint="point of control"
            big
          />
          <Marker
            label="VAL"
            price={data.val}
            tone="var(--color-accent)"
            hint="value area low"
          />
          {currentPrice != null && (
            <div className="mt-1 pt-1 border-t border-[var(--color-border)]/30">
              <div className="text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)]">
                Mark
              </div>
              <div className="num font-bold text-[var(--color-accent)] text-[10px]">
                {fmtPrice(currentPrice)}
              </div>
              {data.poc != null && (
                <div className="text-[8px] text-[var(--color-fg-faint)] mt-0.5">
                  {currentPrice > data.poc ? "atas POC" : "bawah POC"} ·{" "}
                  {(((currentPrice - data.poc) / data.poc) * 100).toFixed(2)}%
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* HVN/LVN chips */}
      {(data.hvn.length > 0 || data.lvn.length > 0) && (
        <div className="px-3 pb-2.5 flex flex-wrap gap-1 border-t border-[var(--color-border)]/30 pt-2">
          {data.hvn.slice(0, 3).map((n, i) => (
            <span
              key={`h-${i}`}
              className="text-[9px] px-1.5 py-0.5 rounded num font-semibold"
              style={{
                color: "var(--color-warning)",
                background: "color-mix(in oklch, var(--color-warning) 14%, transparent)",
              }}
            >
              HVN {fmtPrice(n.price)} · {n.volume_ratio}×
            </span>
          ))}
          {data.lvn.slice(0, 3).map((n, i) => (
            <span
              key={`l-${i}`}
              className="text-[9px] px-1.5 py-0.5 rounded num"
              style={{
                color: "var(--color-fg-faint)",
                background: "rgba(255,255,255,0.04)",
              }}
            >
              LVN {fmtPrice(n.price)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Marker({
  label,
  price,
  tone,
  hint,
  big,
}: {
  label: string;
  price: number | null;
  tone: string;
  hint: string;
  big?: boolean;
}) {
  if (price == null) return null;
  return (
    <div>
      <div className="text-[8px] uppercase tracking-wider" style={{ color: tone }}>
        {label} <span className="text-[var(--color-fg-faint)] normal-case font-normal">· {hint}</span>
      </div>
      <div
        className={`num font-bold ${big ? "text-[11px]" : "text-[10px]"}`}
        style={{ color: tone }}
      >
        {fmtPrice(price)}
      </div>
    </div>
  );
}
