import { Banknote, Crosshair, TrendingUp, TrendingDown } from "lucide-react";
import type { SymbolAnalytics } from "@/types/position";
import { fmtPrice } from "@/lib/format";
import { cn } from "@/lib/cn";

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
      <div className="rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] px-3 py-3 text-[10px] text-[var(--color-fg-faint)]">
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
    <div className="rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] px-3 py-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] flex items-center gap-1.5">
          <Crosshair size={11} />
          Smart Money Concepts
        </span>
        <span className="text-[9px] text-[var(--color-fg-faint)] uppercase tracking-wider">
          institutional zones · stop hunts · market structure
        </span>
      </div>

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
        <div className="rounded-[var(--radius-sm)] ring-1 ring-[var(--color-border)] bg-white/[0.02] px-2.5 py-1.5">
          <div className="flex items-center justify-between">
            <span className="text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)]">
              Market Structure 4h
            </span>
            <span className="text-[10px] font-semibold text-[var(--color-fg)]">
              {struct.structure ?? "—"}
            </span>
          </div>
          <div className="flex items-center gap-3 mt-1 text-[9px]">
            {struct.bos_bullish && (
              <span className="text-[var(--color-success)] flex items-center gap-1">
                <TrendingUp size={9} />
                BOS bullish @ {struct.last_swing_high && fmtPrice(struct.last_swing_high)}
              </span>
            )}
            {struct.bos_bearish && (
              <span className="text-[var(--color-danger)] flex items-center gap-1">
                <TrendingDown size={9} />
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
  );
}

function SweepCell({ label, data }: { label: string; data?: { bullish_sweep: boolean; bearish_sweep: boolean; sweep_strength: number } | null }) {
  if (!data) {
    return (
      <div className="rounded-[var(--radius-sm)] bg-white/[0.02] ring-1 ring-[var(--color-border)] px-2 py-1.5">
        <div className="text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)]">
          {label}
        </div>
        <div className="text-[10px] text-[var(--color-fg-faint)]">—</div>
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
  return (
    <div
      className="rounded-[var(--radius-sm)] ring-1 px-2 py-1.5"
      style={{
        background:
          isBull || isBear
            ? `color-mix(in oklch, ${tone} 10%, transparent)`
            : "rgba(255,255,255,0.02)",
        borderColor: `color-mix(in oklch, ${tone} ${isBull || isBear ? 40 : 20}%, transparent)`,
      }}
    >
      <div className="flex items-center justify-between">
        <span className="text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)]">
          {label}
        </span>
        {(isBull || isBear) && (
          <span className="text-[8px] num font-bold" style={{ color: tone }}>
            ⚡ {(data.sweep_strength * 100).toFixed(0)}%
          </span>
        )}
      </div>
      <div className="text-[10px] mt-0.5 font-semibold" style={{ color: tone }}>
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
      className={cn(
        "rounded-[var(--radius-sm)] ring-1 px-2 py-1.5",
        has ? "" : "bg-white/[0.02] ring-[var(--color-border)]",
      )}
      style={
        has
          ? {
              background: "rgba(255,255,255,0.02)",
              borderColor: "var(--color-border-strong)",
            }
          : undefined
      }
    >
      <div className="text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-0.5">
        {label}
      </div>
      {bullishZone && (
        <div className="text-[10px] text-[var(--color-success)] num">
          ↑ {fmtPrice(bullishZone.low)} – {fmtPrice(bullishZone.high)}
        </div>
      )}
      {bearishZone && (
        <div className="text-[10px] text-[var(--color-danger)] num">
          ↓ {fmtPrice(bearishZone.low)} – {fmtPrice(bearishZone.high)}
        </div>
      )}
      {!has && <div className="text-[10px] text-[var(--color-fg-faint)]">—</div>}
    </div>
  );
}
