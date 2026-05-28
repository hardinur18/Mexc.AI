import { useEffect } from "react";
import { motion, useSpring, useTransform } from "motion/react";

interface AnimatedNumberProps {
  value: number;
  /** Decimal places. */
  decimals?: number;
  /** Include leading + for positive. */
  signed?: boolean;
  /** Suffix (e.g., "%", " USDT"). */
  suffix?: string;
  /** Format function (overrides decimals/signed). */
  format?: (n: number) => string;
  className?: string;
}

/**
 * Smoothly tweens between number values using motion useSpring.
 * Maintains tabular-nums for stable width.
 */
export function AnimatedNumber({
  value,
  decimals = 2,
  signed = false,
  suffix = "",
  format,
  className,
}: AnimatedNumberProps) {
  const spring = useSpring(value, { stiffness: 90, damping: 22, mass: 0.6 });

  useEffect(() => {
    if (!Number.isFinite(value)) return;
    spring.set(value);
  }, [value, spring]);

  const display = useTransform(spring, (latest: number) => {
    if (!Number.isFinite(latest)) return "—";
    if (format) return format(latest);
    const formatted = latest.toLocaleString("en-US", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
    const sign = signed && latest > 0 ? "+" : "";
    return `${sign}${formatted}${suffix}`;
  });

  return <motion.span className={className}>{display}</motion.span>;
}
