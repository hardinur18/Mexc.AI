import { Flame, Sparkles, Zap, Eye, Ban, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/cn";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/Tooltip";

interface SignalBadgeProps {
  score: number | null | undefined;
  verdict: string | null | undefined;
  oversoldN?: number | null;
  overboughtN?: number | null;
  bbLower?: boolean | null;
  dist7dHigh?: number | null;
  size?: "xs" | "sm" | "md";
}

export function SignalBadge({
  score,
  verdict,
  oversoldN,
  overboughtN,
  bbLower,
  dist7dHigh,
  size = "sm",
}: SignalBadgeProps) {
  if (score == null || !verdict) return null;

  const { color, bg, ring, Icon } = signalStyle(score);

  const sizeCls =
    size === "xs"
      ? "text-[9px] px-1 py-0.5 gap-0.5"
      : size === "md"
        ? "text-[11px] px-2 py-1 gap-1.5"
        : "text-[10px] px-1.5 py-0.5 gap-1";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "inline-flex items-center font-bold rounded-[var(--radius-sm)] ring-1 cursor-help select-none whitespace-nowrap",
            sizeCls,
          )}
          style={{ color, background: bg, borderColor: ring }}
        >
          <Icon size={size === "xs" ? 9 : size === "md" ? 12 : 10} />
          <span className="num">{score}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="text-[11px] max-w-[260px]">
        <div className="space-y-1">
          <div className="flex items-center justify-between gap-3">
            <span className="font-semibold uppercase tracking-wider" style={{ color }}>
              {verdict}
            </span>
            <span className="num font-bold" style={{ color }}>
              {score}/100
            </span>
          </div>
          <div className="text-[10px] text-[var(--color-fg-muted)] leading-snug">
            {verdictDescription(verdict)}
          </div>
          <div className="flex flex-wrap gap-1.5 text-[9px] mt-1.5 pt-1.5 border-t border-[var(--color-border)]">
            {oversoldN != null && oversoldN > 0 && (
              <span className="text-[var(--color-success)]">
                {oversoldN}/4 TF oversold
              </span>
            )}
            {overboughtN != null && overboughtN > 0 && (
              <span className="text-[var(--color-danger)]">
                {overboughtN}/4 TF overbought
              </span>
            )}
            {bbLower && <span className="text-[var(--color-success)]">BB lower touch</span>}
            {dist7dHigh != null && (
              <span
                className={
                  dist7dHigh < -10
                    ? "text-[var(--color-success)]"
                    : dist7dHigh > -2
                      ? "text-[var(--color-danger)]"
                      : "text-[var(--color-fg-muted)]"
                }
              >
                {dist7dHigh > 0 ? "+" : ""}
                {dist7dHigh.toFixed(1)}% from 7d high
              </span>
            )}
          </div>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

function signalStyle(score: number) {
  if (score >= 85) {
    return {
      color: "var(--color-success)",
      bg: "var(--color-success-soft)",
      ring: "color-mix(in oklch, var(--color-success) 50%, transparent)",
      Icon: Flame,
    };
  }
  if (score >= 75) {
    return {
      color: "var(--color-success)",
      bg: "var(--color-success-soft)",
      ring: "color-mix(in oklch, var(--color-success) 35%, transparent)",
      Icon: Zap,
    };
  }
  if (score >= 60) {
    return {
      color: "var(--color-warning)",
      bg: "var(--color-warning-soft)",
      ring: "color-mix(in oklch, var(--color-warning) 35%, transparent)",
      Icon: Eye,
    };
  }
  if (score >= 40) {
    return {
      color: "var(--color-fg-muted)",
      bg: "rgba(255,255,255,0.04)",
      ring: "var(--color-border)",
      Icon: Sparkles,
    };
  }
  if (score >= 25) {
    return {
      color: "var(--color-warning)",
      bg: "var(--color-warning-soft)",
      ring: "color-mix(in oklch, var(--color-warning) 30%, transparent)",
      Icon: AlertTriangle,
    };
  }
  return {
    color: "var(--color-danger)",
    bg: "var(--color-danger-soft)",
    ring: "color-mix(in oklch, var(--color-danger) 40%, transparent)",
    Icon: Ban,
  };
}

function verdictDescription(verdict: string): string {
  switch (verdict) {
    case "SCREAMING BUY":
      return "Extreme multi-TF oversold confluence. Highest conviction dip-buy zone.";
    case "ACCUMULATE":
      return "Dip-buy zone confirmed. Multiple bullish confluence triggers.";
    case "WATCH":
      return "Pullback in progress. Wait for stronger confluence before entry.";
    case "NEUTRAL":
      return "No clear setup. Neither oversold nor overheated.";
    case "AVOID":
      return "Momentum chase territory. No dip-buy edge here.";
    case "AVOID - CHASE TRAP":
      return "FOMO trap. Multi-TF overbought + near recent highs.";
    default:
      return "";
  }
}
