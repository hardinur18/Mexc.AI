import { Banknote, Crosshair, TrendingUp, TrendingDown } from "lucide-react";
import type { SymbolAnalytics } from "@/types/position";
import { fmtPrice } from "@/lib/format";

interface SmcCardProps {
  a: SymbolAnalytics | undefined;
}

const WYCKOFF_LABELS: Record<string, { text: string; tone: string; emoji: string }> = {
  accumulation: { text: "Akumulasi (smart money beli)", tone: "var(--color-success)", emoji: "📈" },
  distribution: { text: "Distribusi (smart money jual)", tone: "var(--color-danger)", emoji: "📉" },
  "mark-up": { text: "Mark-up (uptrend kuat)", tone: "var(--color-success)", emoji: "🚀" },
  "mark-down": { text: "Mark-down (downtrend)", tone: "var(--color-danger)", emoji: "🔻" },
  capitulation: { text: "Capitulation (panic sell)", tone: "var(--color-warning)", emoji: "💥" },
  consolidation: { text: "Konsolidasi (range tight)", tone: "var(--color-fg-muted)", emoji: "⏸" },
  unknown: { text: "Tidak teridentifikasi", tone: "var(--color-fg-faint)", emoji: "—" },
};

export function SmcCard({ a }: SmcCardProps) {
  if (!a) {
    return (
      <div className="rounded-[var(--radius-md)] inner-card px-3 py-3 text-[10px] text-[var(--color-fg-faint)]">
        Menghitung analisa smart money...
      </div>
    );
  }

  const sweep4 = a.liquidity_sweep_4h;
  const sweep1 = a.liquidity_sweep_1h;
  const ob = a.order_block_4h;
  const fvg = a.fair_value_gap_4h;
  const struct = a.market_structure_4h;
  const wyckoff = a.wyckoff_phase;
  const whale = a.whale_accumulation;

  const wyckoffInfo = WYCKOFF_LABELS[wyckoff?.phase ?? "unknown"] ?? WYCKOFF_LABELS.unknown;

  return (
    <div className="inner-card overflow-hidden space-y-0">
      <div className="ui-panel-header px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <span className="ui-icon-chip" style={{ color: "var(--color-accent)" }}>
            <Crosshair size={13} />
          </span>
          <span className="ui-section-title">Smart Money Concepts</span>
        </div>
        <span className="text-[11px] text-[var(--color-fg-faint)]">
          institutional flow
        </span>
      </div>

      <div className="px-4 py-4 space-y-3">

      {/* Wyckoff phase */}
      <div
        className="rounded-[var(--radius-sm)] ring-1 px-2.5 py-2 flex items-center justify-between"
        style={{
          background: `color-mix(in oklch, ${wyckoffInfo.tone} 6%, transparent)`,
          borderColor: `color-mix(in oklch, ${wyckoffInfo.tone} 30%, transparent)`,
        }}
      >
        <div className="leading-tight">
          <div className="text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)]">
            Wyckoff Phase
          </div>
          <div
            className="text-[11px] font-semibold"
            style={{ color: wyckoffInfo.tone }}
          >
            {wyckoffInfo.emoji} {wyckoffInfo.text}
          </div>
        </div>
        {wyckoff && wyckoff.confidence > 0 && (
          <span
            className="text-[10px] num font-bold"
            style={{ color: wyckoffInfo.tone }}
          >
            {wyckoff.confidence}%
          </span>
        )}
      </div>

      {/* Whale accumulation flag */}
      {whale?.detected && (
        <div className="rounded-[var(--radius-sm)] ring-1 ring-[var(--color-accent)]/40 bg-[var(--color-accent-soft)] px-2.5 py-2 flex items-center gap-2">
          <Banknote size={14} className="text-[var(--color-accent)] shrink-0" />
          <div className="leading-tight flex-1">
            <div className="text-[10px] uppercase tracking-wider font-bold text-[var(--color-accent)]">
              🐋 Whale Stealth Accumulation
            </div>
            <div className="text-[9px] text-[var(--color-fg-muted)]">
              OI naik +{whale.oi_change_pct?.toFixed(1)}% sementara harga flat (
              {whale.price_change_pct?.toFixed(2)}%) — uang gede masuk diam-diam
            </div>
          </div>
          <span className="text-[12px] num font-bold text-[var(--color-accent)]">
            {whale.intensity}
          </span>
        </div>
      )}

      {/* Liquidity sweeps */}
      <div className="grid grid-cols-2 gap-1.5">
        <SweepCell label="Sweep 4h" data={sweep4} />
        <SweepCell label="Sweep 1h" data={sweep1} />
      </div>

      {/* Order Block + FVG */}
      <div className="grid grid-cols-2 gap-1.5">
        <ZoneCell
          label="Order Block 4h"
          bullishZone={ob?.bullish_ob_zone}
          bearishZone={ob?.bearish_ob_zone}
        />
        <ZoneCell
          label="Fair Value Gap 4h"
          bullishZone={fvg?.bullish_fvg}
          bearishZone={fvg?.bearish_fvg}
        />
      </div>

      {/* Market Structure */}
      {struct && (
        <div className="ui-subcard px-3 py-2.5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] uppercase tracking-wider text-[var(--color-fg-faint)] font-medium">
              Market Structure 4h
            </span>
            <span className="text-[12px] font-semibold text-[var(--color-fg)]">
              {struct.structure ?? "—"}
            </span>
          </div>
          <div className="flex items-center gap-3 mt-1.5 text-[11px]">
            {struct.bos_bullish && (
              <span className="text-[var(--color-success)] flex items-center gap-1.5">
                <TrendingUp size={11} />
                BOS bullish @ {struct.last_swing_high && fmtPrice(struct.last_swing_high)}
              </span>
            )}
            {struct.bos_bearish && (
              <span className="text-[var(--color-danger)] flex items-center gap-1.5">
                <TrendingDown size={11} />
                BOS bearish @ {struct.last_swing_low && fmtPrice(struct.last_swing_low)}
              </span>
            )}
            {!struct.bos_bullish && !struct.bos_bearish && (
              <span className="text-[var(--color-fg-faint)]">tidak ada break</span>
            )}
          </div>
        </div>
      )}
      </div>
    </div>
  );
}

function SweepCell({ label, data }: { label: string; data?: { bullish_sweep: boolean; bearish_sweep: boolean; sweep_strength: number } | null }) {
  if (!data) {
    return (
      <div className="ui-subcard px-3 py-2">
        <div className="text-[11px] uppercase tracking-wider text-[var(--color-fg-faint)] font-medium">
          {label}
        </div>
        <div className="text-[11px] text-[var(--color-fg-faint)] mt-0.5">—</div>
      </div>
    );
  }
  const isBull = data.bullish_sweep;
  const isBear = data.bearish_sweep;
  const tone = isBull
    ? "var(--color-success)"
    : isBear
      ? "var(--color-danger)"
      : "var(--color-fg-muted)";
  const txt = isBull
    ? "BULL sweep (stop hunt low)"
    : isBear
      ? "BEAR sweep (stop hunt high)"
      : "tidak ada sweep";
  const active = isBull || isBear;
  return (
    <div
      className="ui-subcard px-3 py-2"
      style={active ? {
        background: `color-mix(in oklch, ${tone} 10%, var(--color-bg-elev))`,
        borderColor: `color-mix(in oklch, ${tone} 40%, transparent)`,
      } : undefined}
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-wider text-[var(--color-fg-faint)] font-medium">
          {label}
        </span>
        {active && (
          <span className="text-[11px] num font-bold" style={{ color: tone }}>
            {(data.sweep_strength * 100).toFixed(0)}%
          </span>
        )}
      </div>
      <div className="text-[11px] mt-0.5 font-semibold" style={{ color: tone }}>
        {txt}
      </div>
    </div>
  );
}

function ZoneCell({
  label,
  bullishZone,
  bearishZone,
}: {
  label: string;
  bullishZone?: { high: number; low: number; bar_index_from_now: number } | null;
  bearishZone?: { high: number; low: number; bar_index_from_now: number } | null;
}) {
  const has = !!bullishZone || !!bearishZone;
  return (
    <div
      className="ui-subcard px-3 py-2"
      style={has ? { borderColor: "var(--color-border-strong)" } : undefined}
    >
      <div className="text-[11px] uppercase tracking-wider text-[var(--color-fg-faint)] font-medium mb-1">
        {label}
      </div>
      {bullishZone && (
        <div className="text-[11px] text-[var(--color-success)] num font-medium">
          {fmtPrice(bullishZone.low)} – {fmtPrice(bullishZone.high)}
        </div>
      )}
      {bearishZone && (
        <div className="text-[11px] text-[var(--color-danger)] num font-medium">
          {fmtPrice(bearishZone.low)} – {fmtPrice(bearishZone.high)}
        </div>
      )}
      {!has && <div className="text-[11px] text-[var(--color-fg-faint)]">—</div>}
    </div>
  );
}
