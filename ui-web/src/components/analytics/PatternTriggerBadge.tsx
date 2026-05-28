import { Flame, TrendingUp, TrendingDown, Minus, CheckCircle, Clock } from "lucide-react";
import type { PrimaryPatternTrigger } from "@/types/position";
import { fmtPrice } from "@/lib/format";

interface Props {
  trigger: PrimaryPatternTrigger | null | undefined;
  direction?: "LONG" | "SHORT" | "NONE";
}

const PATTERN_LABEL_ID: Record<string, string> = {
  bullish_engulfing: "Engulfing Bull",
  bearish_engulfing: "Engulfing Bear",
  hammer: "Hammer",
  shooting_star: "Shooting Star",
  bullish_pin_bar: "Pin Bar Bull",
  bearish_pin_bar: "Pin Bar Bear",
  dragonfly_doji: "Dragonfly Doji",
  gravestone_doji: "Gravestone Doji",
  morning_star: "Morning Star",
  evening_star: "Evening Star",
  three_white_soldiers: "3 White Soldiers",
  three_black_crows: "3 Black Crows",
  piercing_line: "Piercing Line",
  dark_cloud_cover: "Dark Cloud Cover",
  tweezer_bottom: "Tweezer Bottom",
  tweezer_top: "Tweezer Top",
  bullish_harami: "Harami Bull",
  bearish_harami: "Harami Bear",
  doji: "Doji",
  inside_bar: "Inside Bar",
};

export function PatternTriggerBadge({ trigger, direction }: Props) {
  if (!trigger) return null;
  const isBull = trigger.bullish === true;
  const isBear = trigger.bullish === false;
  const tone = isBull
    ? "var(--color-success)"
    : isBear
      ? "var(--color-danger)"
      : "var(--color-warning)";
  const Icon = isBull ? TrendingUp : isBear ? TrendingDown : Minus;
  const ageLabel =
    trigger.bar_index_from_now === 0
      ? "bar berjalan"
      : `bar -${trigger.bar_index_from_now}`;
  const label = PATTERN_LABEL_ID[trigger.pattern] || trigger.pattern;
  const directionHint =
    direction === "LONG"
      ? "entry kalau close di atas"
      : direction === "SHORT"
        ? "entry kalau close di bawah"
        : "trigger";

  return (
    <div
      className="flex items-start gap-2 px-2.5 py-1.5 rounded-[var(--radius-md)] ring-1"
      style={{
        background: `color-mix(in oklch, ${tone} 8%, transparent)`,
        borderColor: `color-mix(in oklch, ${tone} 30%, transparent)`,
      }}
    >
      <Flame size={11} style={{ color: tone }} className="mt-0.5 shrink-0" />
      <div className="leading-tight min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <Icon size={9} style={{ color: tone }} />
          <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: tone }}>
            {label}
          </span>
          <span className="text-[9px] text-[var(--color-fg-faint)] uppercase tracking-wider">
            · {trigger.tf} · {ageLabel}
          </span>
          {/* Phase 14: confirmation indicator */}
          {trigger.confirmed ? (
            <span
              className="inline-flex items-center gap-0.5 text-[8px] font-bold uppercase tracking-wider px-1 py-0.5 rounded ring-1"
              style={{
                color: "var(--color-success)",
                background: "color-mix(in oklch, var(--color-success) 14%, transparent)",
                borderColor: "color-mix(in oklch, var(--color-success) 35%, transparent)",
              }}
              title={
                trigger.confirmation_close
                  ? `Dikonfirmasi: close @ ${fmtPrice(trigger.confirmation_close)}`
                  : "Pattern dikonfirmasi"
              }
            >
              <CheckCircle size={8} /> CONFIRMED
            </span>
          ) : trigger.bar_index_from_now === 0 ? (
            <span
              className="inline-flex items-center gap-0.5 text-[8px] font-bold uppercase tracking-wider px-1 py-0.5 rounded ring-1 text-[var(--color-warning)]"
              style={{
                background: "color-mix(in oklch, var(--color-warning) 12%, transparent)",
                borderColor: "color-mix(in oklch, var(--color-warning) 30%, transparent)",
              }}
              title="Pattern di bar berjalan — tunggu close untuk konfirmasi"
            >
              <Clock size={8} /> PENDING
            </span>
          ) : null}
        </div>
        <div className="text-[10px] text-[var(--color-fg-muted)] mt-0.5">
          terbentuk di{" "}
          <span className="num font-semibold text-[var(--color-fg)]">
            {fmtPrice(trigger.close)}
          </span>
          <span className="text-[var(--color-fg-faint)]"> · </span>
          {directionHint}{" "}
          <span className="num font-semibold" style={{ color: tone }}>
            {fmtPrice(trigger.trigger_price)}
          </span>
        </div>
      </div>
    </div>
  );
}
