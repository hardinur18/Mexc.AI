import { motion } from "motion/react";
import { ShieldCheck, AlertTriangle, Clock, Zap, Activity, Volume2 } from "lucide-react";
import type {
  MacroScoreAdjustment,
  FundingWindow,
  FundingArbSignal,
  VolumeConfirmation,
  LiquidityGrab,
  SweepData,
} from "@/types/position";
import { fmtPrice } from "@/lib/format";

interface Props {
  adjustments: MacroScoreAdjustment[] | null | undefined;
  fundingWindow: FundingWindow | null | undefined;
  fundingArb: FundingArbSignal | null | undefined;
  volumeConfirmation: VolumeConfirmation | null | undefined;
  liquidityGrab4h: LiquidityGrab | null | undefined;
  liquidityGrab1h: LiquidityGrab | null | undefined;
  sweep15m: SweepData | null | undefined;
  dynamicLevBand: string | null | undefined;
  dynamicLevMult: number | null | undefined;
  direction: "LONG" | "SHORT" | "NONE";
}

/**
 * Surfaces all Phase 7+8+9 signal-quality indicators in one card.
 * - Macro/flow score adjustments (Deribit, basis, volume, pattern, funding window)
 * - Volume confirmation
 * - Liquidity grab (strongest reversal)
 * - 15m sweep (LTF timing)
 * - Funding window warning
 * - Funding arbitrage opportunity
 * - Dynamic leverage band
 */
export function SignalQualityCard({
  adjustments,
  fundingWindow,
  fundingArb,
  volumeConfirmation,
  liquidityGrab4h,
  liquidityGrab1h,
  sweep15m,
  dynamicLevBand,
  dynamicLevMult,
  direction,
}: Props) {
  const hasContent =
    (adjustments && adjustments.length > 0) ||
    fundingWindow?.near_settlement ||
    fundingArb ||
    volumeConfirmation?.confirmed ||
    liquidityGrab4h?.bullish_grab ||
    liquidityGrab4h?.bearish_grab ||
    liquidityGrab1h?.bullish_grab ||
    liquidityGrab1h?.bearish_grab ||
    sweep15m?.bullish_sweep ||
    sweep15m?.bearish_sweep ||
    dynamicLevBand;

  if (!hasContent) return null;

  const isLong = direction === "LONG";
  const isShort = direction === "SHORT";

  const levBandTone =
    dynamicLevBand === "high_conviction"
      ? "var(--color-success)"
      : dynamicLevBand === "strong"
        ? "var(--color-success)"
        : dynamicLevBand === "moderate"
          ? "var(--color-warning)"
          : "var(--color-danger)";

  return (
    <div className="lift rounded-[var(--radius-md)] inner-card overflow-hidden">
      <div className="px-3 py-2 flex items-center gap-2 border-b border-[var(--color-border)]/50">
        <ShieldCheck size={11} className="text-[var(--color-accent)]" />
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
          Signal Quality
        </span>
        <span className="text-[9px] text-[var(--color-fg-faint)] ml-auto">
          confirmation · flow · adjustments
        </span>
      </div>

      <div className="p-4 space-y-2">
        {/* Funding window warning */}
        {fundingWindow?.near_settlement && (
          <motion.div
            initial={{ opacity: 0, y: -2 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-start gap-2 px-2.5 py-1.5 rounded ring-1"
            style={{
              background: "color-mix(in oklch, var(--color-warning) 12%, transparent)",
              borderColor: "color-mix(in oklch, var(--color-warning) 30%, transparent)",
            }}
          >
            <Clock size={11} className="text-[var(--color-warning)] mt-0.5 shrink-0" />
            <div className="leading-tight">
              <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-warning)]">
                Settle funding {fundingWindow.minutes_to_settle?.toFixed(0)} mnt lagi
              </div>
              <div className="text-[9px] text-[var(--color-fg-muted)] mt-0.5">
                {fundingWindow.settlement_warning ?? "Hindari entry baru sebelum settle"}
              </div>
            </div>
          </motion.div>
        )}

        {/* Funding arb signal */}
        {fundingArb && (
          <motion.div
            initial={{ opacity: 0, y: -2 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-start gap-2 px-2.5 py-1.5 rounded ring-1"
            style={{
              background: "color-mix(in oklch, var(--color-accent) 10%, transparent)",
              borderColor: "color-mix(in oklch, var(--color-accent) 30%, transparent)",
            }}
          >
            <Zap size={11} className="text-[var(--color-accent)] mt-0.5 shrink-0" />
            <div className="leading-tight flex-1">
              <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-[var(--color-accent)]">
                Funding Arb · {fundingArb.annualized_pct.toFixed(1)}% APY
              </div>
              <div className="text-[9px] text-[var(--color-fg-muted)] mt-0.5">
                {fundingArb.description}
              </div>
            </div>
          </motion.div>
        )}

        {/* Liquidity grab — strongest reversal */}
        {(liquidityGrab4h?.bullish_grab || liquidityGrab4h?.bearish_grab ||
          liquidityGrab1h?.bullish_grab || liquidityGrab1h?.bearish_grab) && (
          <motion.div
            initial={{ opacity: 0, y: -2 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-start gap-2 px-2.5 py-1.5 rounded ring-1"
            style={{
              background: "color-mix(in oklch, var(--color-success) 12%, transparent)",
              borderColor: "color-mix(in oklch, var(--color-success) 35%, transparent)",
            }}
          >
            <AlertTriangle size={11} className="text-[var(--color-success)] mt-0.5 shrink-0" />
            <div className="leading-tight">
              <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-success)]">
                🎯 Liquidity grab terdeteksi
              </div>
              <div className="text-[9px] text-[var(--color-fg-muted)] mt-0.5">
                {liquidityGrab4h?.bullish_grab && (
                  <>
                    4h sweep low @ {fmtPrice(liquidityGrab4h.grab_low!)}, rejection{" "}
                    {liquidityGrab4h.rejection_pct?.toFixed(0)}%
                  </>
                )}
                {liquidityGrab4h?.bearish_grab && (
                  <>
                    4h sweep high @ {fmtPrice(liquidityGrab4h.grab_high!)}, rejection{" "}
                    {liquidityGrab4h.rejection_pct?.toFixed(0)}%
                  </>
                )}
                {!liquidityGrab4h?.bullish_grab &&
                  !liquidityGrab4h?.bearish_grab &&
                  liquidityGrab1h?.bullish_grab && (
                    <>
                      1h sweep low @ {fmtPrice(liquidityGrab1h.grab_low!)}, rejection{" "}
                      {liquidityGrab1h.rejection_pct?.toFixed(0)}%
                    </>
                  )}
                {!liquidityGrab4h?.bullish_grab &&
                  !liquidityGrab4h?.bearish_grab &&
                  liquidityGrab1h?.bearish_grab && (
                    <>
                      1h sweep high @ {fmtPrice(liquidityGrab1h.grab_high!)}, rejection{" "}
                      {liquidityGrab1h.rejection_pct?.toFixed(0)}%
                    </>
                  )}
              </div>
            </div>
          </motion.div>
        )}

        {/* Compact chip row: volume confirm + 15m sweep + dynamic lev */}
        <div className="flex flex-wrap gap-1.5">
          {/* Volume confirmation chip */}
          {volumeConfirmation && volumeConfirmation.ratio != null && (
            <Chip
              icon={<Volume2 size={9} />}
              label={`Vol ${volumeConfirmation.ratio.toFixed(2)}× avg`}
              tone={volumeConfirmation.confirmed ? "good" : "neutral"}
              suffix={volumeConfirmation.confirmed ? "✓" : "below"}
            />
          )}

          {/* 15m sweep */}
          {sweep15m?.bullish_sweep && (
            <Chip
              icon={<Activity size={9} />}
              label="15m sweep bull (LTF)"
              tone={isLong ? "good" : "neutral"}
            />
          )}
          {sweep15m?.bearish_sweep && (
            <Chip
              icon={<Activity size={9} />}
              label="15m sweep bear (LTF)"
              tone={isShort ? "good" : "neutral"}
            />
          )}

          {/* Dynamic leverage band */}
          {dynamicLevBand && dynamicLevMult != null && (
            <Chip
              icon={<ShieldCheck size={9} />}
              label={`Lev ${dynamicLevBand.replace("_", " ")} · ${(dynamicLevMult * 100).toFixed(0)}%`}
              tone={
                dynamicLevBand === "high_conviction" || dynamicLevBand === "strong"
                  ? "good"
                  : dynamicLevBand === "moderate"
                    ? "neutral"
                    : "bad"
              }
            />
          )}
        </div>

        {/* Macro score adjustments breakdown */}
        {adjustments && adjustments.length > 0 && (
          <div>
            <div className="text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1">
              Macro/flow adjustments ({adjustments.length})
            </div>
            <div className="space-y-0.5">
              {adjustments.map((adj, i) => {
                const tone =
                  adj.score_delta < 0
                    ? "var(--color-danger)"
                    : adj.score_delta > 0
                      ? "var(--color-success)"
                      : "var(--color-fg-muted)";
                return (
                  <div
                    key={i}
                    className="flex items-center justify-between text-[9px] px-2 py-1 rounded bg-white/[0.02]"
                  >
                    <span className="text-[var(--color-fg-muted)] truncate">{adj.name}</span>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-[var(--color-fg-faint)] num text-[8px]">
                        {adj.value}
                      </span>
                      <span className="num font-bold w-8 text-right" style={{ color: tone }}>
                        {adj.score_delta > 0 ? "+" : ""}
                        {adj.score_delta}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );

  void levBandTone; // referenced for future highlight
}

function Chip({
  icon,
  label,
  tone,
  suffix,
}: {
  icon: React.ReactNode;
  label: string;
  tone: "good" | "bad" | "neutral";
  suffix?: string;
}) {
  const color =
    tone === "good"
      ? "var(--color-success)"
      : tone === "bad"
        ? "var(--color-danger)"
        : "var(--color-fg-muted)";
  return (
    <span
      className="inline-flex items-center gap-1 text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded ring-1"
      style={{
        color,
        background: `color-mix(in oklch, ${color} 10%, transparent)`,
        borderColor: `color-mix(in oklch, ${color} 28%, transparent)`,
      }}
    >
      {icon}
      <span>{label}</span>
      {suffix && <span className="opacity-70">{suffix}</span>}
    </span>
  );
}
