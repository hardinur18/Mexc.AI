import { TrendingUp, TrendingDown, Circle } from "lucide-react";

const BULLISH = new Set([
  "bullish_engulfing",
  "hammer",
  "morning_star",
  "three_white_soldiers",
  "bullish_harami",
]);

const BEARISH = new Set([
  "bearish_engulfing",
  "shooting_star",
  "evening_star",
  "three_black_crows",
  "bearish_harami",
]);

const LABELS: Record<string, string> = {
  bullish_engulfing: "Bullish Engulfing",
  bearish_engulfing: "Bearish Engulfing",
  hammer: "Hammer",
  shooting_star: "Shooting Star",
  doji: "Doji",
  bullish_harami: "Bullish Harami",
  bearish_harami: "Bearish Harami",
  morning_star: "Morning Star",
  evening_star: "Evening Star",
  three_white_soldiers: "3 White Soldiers",
  three_black_crows: "3 Black Crows",
};

interface Props {
  patterns: { tf: string; pattern: string }[];
}

export function CandlePatternsRow({ patterns }: Props) {
  if (!patterns || patterns.length === 0) {
    return (
      <div className="rounded-[var(--radius-md)] inner-card px-3 py-2 text-[10px] text-[var(--color-fg-faint)] flex items-center gap-1.5">
        <Circle size={10} />
        Tidak ada pola candle penting di MTF
      </div>
    );
  }

  return (
    <div className="rounded-[var(--radius-md)] inner-card px-3 py-2.5 space-y-1.5">
      <div className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
        Pola Candle Multi-TF ({patterns.length})
      </div>
      <div className="flex flex-wrap gap-1.5">
        {patterns.map((p, i) => {
          const isBull = BULLISH.has(p.pattern);
          const isBear = BEARISH.has(p.pattern);
          // Softer chip colors — toned-down vs full danger/success
          const tone = isBull
            ? "var(--color-success)"
            : isBear
              ? "oklch(72% 0.16 35)"  // softer orange-red instead of full danger
              : "var(--color-fg-muted)";
          const Icon = isBull ? TrendingUp : isBear ? TrendingDown : Circle;
          const tfHeavy = p.tf === "4h" || p.tf === "1d";
          return (
            <span
              key={`${p.tf}-${p.pattern}-${i}`}
              className="text-[10px] px-1.5 py-0.5 rounded ring-1 font-medium flex items-center gap-1 whitespace-nowrap"
              style={{
                color: tone,
                background: `color-mix(in oklch, ${tone} ${tfHeavy ? 11 : 6}%, transparent)`,
                borderColor: `color-mix(in oklch, ${tone} ${tfHeavy ? 35 : 22}%, transparent)`,
                fontWeight: tfHeavy ? 700 : 500,
              }}
              title={`${LABELS[p.pattern] ?? p.pattern} pada ${p.tf}`}
            >
              <Icon size={9} />
              <span className="opacity-70">{p.tf}</span>
              <span>{LABELS[p.pattern] ?? p.pattern}</span>
            </span>
          );
        })}
      </div>
    </div>
  );
}
