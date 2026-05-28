import { motion } from "motion/react";
import type { MTFConvergence } from "@/types/position";

interface Props {
  data: MTFConvergence | null | undefined;
  size?: number;
  direction?: "LONG" | "SHORT" | "NONE";
}

/** Circular ring showing MTF alignment score 0-100 with breakdown tooltip-style list. */
export function MtfConvergenceRing({ data, size = 56, direction = "NONE" }: Props) {
  const score = data?.score ?? 0;
  const r = size / 2 - 4;
  const c = 2 * Math.PI * r;
  const dash = (score / 100) * c;
  const tone =
    direction === "LONG"
      ? "var(--color-success)"
      : direction === "SHORT"
        ? "var(--color-danger)"
        : score >= 70
          ? "var(--color-success)"
          : score >= 40
            ? "var(--color-warning)"
            : "var(--color-fg-muted)";

  return (
    <div className="inline-flex items-center gap-2.5">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            stroke="var(--color-border)"
            strokeWidth="3"
            fill="none"
            opacity="0.5"
          />
          <motion.circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            stroke={tone}
            strokeWidth="3"
            fill="none"
            strokeLinecap="round"
            strokeDasharray={c}
            initial={{ strokeDashoffset: c }}
            animate={{ strokeDashoffset: c - dash }}
            transition={{ duration: 0.8, ease: [0.34, 1.4, 0.4, 1] }}
            style={{ filter: score >= 60 ? `drop-shadow(0 0 4px ${tone})` : "none" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-base font-bold num leading-none" style={{ color: tone }}>
            {score}
          </span>
          <span className="text-[7px] uppercase tracking-wider text-[var(--color-fg-faint)] mt-0.5">
            MTF
          </span>
        </div>
      </div>
      {data?.factors && data.factors.length > 0 && (
        <div className="flex flex-col gap-0.5 min-w-0">
          {data.factors.slice(0, 3).map((f, i) => (
            <span
              key={i}
              className="text-[9px] text-[var(--color-fg-muted)] truncate max-w-[180px]"
            >
              {f}
            </span>
          ))}
          {data.factors.length > 3 && (
            <span className="text-[8px] text-[var(--color-fg-faint)]">
              +{data.factors.length - 3} faktor lain
            </span>
          )}
        </div>
      )}
    </div>
  );
}
