import { motion } from "motion/react";
import { ShieldX, AlertOctagon } from "lucide-react";
import type { SlInvalidation, RRRatio } from "@/types/position";
import { fmtPrice } from "@/lib/format";

interface Props {
  sl: SlInvalidation | null | undefined;
  rr: RRRatio | null | undefined;
  entryPrice?: number | null;
  direction?: "LONG" | "SHORT" | "NONE";
}

/**
 * Stop loss invalidation level + R:R panel.
 *
 * Pro trader rule: tiap trade harus tahu di harga mana wrong & R-multiple to TP.
 */
export function SLInvalidationCard({ sl, rr, entryPrice, direction }: Props) {
  if (!sl?.price) return null;
  const isLong = direction === "LONG";
  const tone = isLong ? "var(--color-danger)" : "var(--color-danger)";
  const rrTone = (r: number | null | undefined): string => {
    if (r == null) return "var(--color-fg-muted)";
    if (r >= 3) return "var(--color-success)";
    if (r >= 2) return "var(--color-accent)";
    if (r >= 1) return "var(--color-warning)";
    return "var(--color-danger)";
  };

  return (
    <div className="inner-card overflow-hidden">
      <div className="ui-panel-header px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <span className="ui-icon-chip" style={{ color: tone }}>
            <ShieldX size={13} />
          </span>
          <span className="ui-section-title">Stop Loss + Risk:Reward</span>
        </div>
        <span className="text-[11px] text-[var(--color-fg-faint)]">
          invalidation + R-multiple
        </span>
      </div>

      <div className="px-4 py-4 space-y-3">
        {/* Stop Loss */}
        <div className="ui-subcard px-3.5 py-3">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] uppercase tracking-wider text-[var(--color-danger)] font-bold flex items-center gap-1.5">
              <AlertOctagon size={11} />
              Invalidation Level
            </span>
            <span className="text-[11px] num text-[var(--color-fg-faint)]">
              {sl.distance_pct?.toFixed(2)}% dari entry
            </span>
          </div>
          <div className="flex items-baseline gap-2.5">
            <motion.span
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.4, ease: [0.34, 1.4, 0.4, 1] }}
              className="text-xl font-bold num leading-none"
              style={{ color: "var(--color-danger)" }}
            >
              {fmtPrice(sl.price)}
            </motion.span>
            {entryPrice != null && (
              <span className="text-[11px] text-[var(--color-fg-faint)]">
                vs entry <span className="num font-medium">{fmtPrice(entryPrice)}</span>
              </span>
            )}
          </div>
          {sl.reason && (
            <div className="text-[11px] text-[var(--color-fg-muted)] mt-1.5">{sl.reason}</div>
          )}
        </div>

        {/* R:R per TP */}
        <div className="grid grid-cols-3 gap-2">
          {[
            { label: "TP1", r: rr?.tp1 },
            { label: "TP2", r: rr?.tp2 },
            { label: "TP3", r: rr?.tp3 },
          ].map((t, i) => (
            <motion.div
              key={t.label}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: i * 0.05 }}
              className="ui-subcard px-3 py-2.5 text-center"
            >
              <div className="text-[11px] uppercase tracking-wider text-[var(--color-fg-faint)] font-medium">
                {t.label}
              </div>
              <div
                className="text-lg font-bold num mt-1"
                style={{ color: rrTone(t.r) }}
              >
                {t.r != null ? `${t.r.toFixed(2)}R` : "—"}
              </div>
              <div className="text-[11px] text-[var(--color-fg-faint)] mt-0.5">
                {t.r == null
                  ? ""
                  : t.r >= 3
                    ? "premium"
                    : t.r >= 2
                      ? "ok"
                      : t.r >= 1
                        ? "marginal"
                        : "skip"}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
