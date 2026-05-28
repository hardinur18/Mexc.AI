import { motion } from "motion/react";
import {
  Activity,
  CheckCircle,
  Flame,
  Loader2,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  XCircle,
  Zap,
} from "lucide-react";
import { useAnalytics } from "@/hooks/useSnapshot";
import { cn } from "@/lib/cn";

interface AnalysisCardProps {
  symbol: string;
  patterns?: { tf: string; pattern: string }[];
}

const PATTERN_LABELS: Record<string, string> = {
  bullish_engulfing: "Bull Engulfing",
  bearish_engulfing: "Bear Engulfing",
  hammer: "Hammer",
  shooting_star: "Shooting Star",
  doji: "Doji",
  bullish_harami: "Bull Harami",
  bearish_harami: "Bear Harami",
  morning_star: "Morning Star",
  evening_star: "Evening Star",
  three_white_soldiers: "3 White Soldiers",
  three_black_crows: "3 Black Crows",
  bullish_pin_bar: "Bull Pin",
  bearish_pin_bar: "Bear Pin",
  tweezer_bottom: "Tweezer Bottom",
  tweezer_top: "Tweezer Top",
  piercing_line: "Piercing Line",
  dark_cloud_cover: "Dark Cloud",
  dragonfly_doji: "Dragonfly",
  gravestone_doji: "Gravestone",
};

const BULL_PATTERNS = new Set([
  "bullish_engulfing", "hammer", "morning_star", "three_white_soldiers",
  "bullish_harami", "bullish_pin_bar", "tweezer_bottom", "piercing_line", "dragonfly_doji",
]);
const BEAR_PATTERNS = new Set([
  "bearish_engulfing", "shooting_star", "evening_star", "three_black_crows",
  "bearish_harami", "bearish_pin_bar", "tweezer_top", "dark_cloud_cover", "gravestone_doji",
]);

export function AnalysisCard({ symbol, patterns }: AnalysisCardProps) {
  const { data, isLoading } = useAnalytics(symbol);

  if (isLoading || !data) {
    return (
      <div className="rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] px-3 py-4 flex items-center justify-center gap-2 text-[11px] text-[var(--color-fg-subtle)]">
        <Loader2 size={12} className="animate-spin" />
        Computing multi-TF analysis…
      </div>
    );
  }

  const score = data.confluence_score;
  const verdict = data.verdict;
  const scoreTone =
    score >= 85
      ? "var(--color-success)"
      : score >= 75
        ? "var(--color-success)"
        : score >= 60
          ? "var(--color-warning)"
          : score >= 40
            ? "var(--color-fg-muted)"
            : "var(--color-danger)";

  return (
    <div className="rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] px-3 py-3 space-y-3">
      {/* Header: Confluence verdict */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] flex items-center gap-1.5">
            <Sparkles size={11} />
            Kekuatan Sinyal Beli Dip
          </span>
          <span
            className="text-[10px] uppercase tracking-wider font-bold"
            style={{ color: scoreTone }}
          >
            {verdict}
          </span>
        </div>
        <div className="flex items-baseline gap-2 mb-2">
          <motion.span
            key={score}
            initial={{ opacity: 0.6, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.3 }}
            className="num text-[26px] leading-none font-bold"
            style={{ color: scoreTone }}
          >
            {score}
          </motion.span>
          <span className="text-[10px] text-[var(--color-fg-subtle)]">/ 100</span>
        </div>
        <div className="relative h-1.5 rounded-full bg-white/5 overflow-hidden">
          <div
            className="absolute top-0 bottom-0 w-px bg-[var(--color-warning)]/40"
            style={{ left: "60%" }}
          />
          <div
            className="absolute top-0 bottom-0 w-px bg-[var(--color-success)]/50"
            style={{ left: "75%" }}
          />
          <div
            className="absolute top-0 bottom-0 w-px bg-[var(--color-success)]"
            style={{ left: "85%" }}
          />
          <motion.div
            initial={false}
            animate={{ width: `${score}%` }}
            transition={{ duration: 0.6, ease: [0.34, 1.4, 0.4, 1] }}
            className="h-full rounded-full"
            style={{ background: scoreTone, boxShadow: `0 0 6px ${scoreTone}` }}
          />
        </div>
        <div className="flex justify-between text-[8px] text-[var(--color-fg-faint)] mt-0.5 uppercase tracking-wider">
          <span>hindari</span>
          <span>sabar</span>
          <span>akumulasi</span>
          <span>borong</span>
        </div>
      </div>

      <div className="h-px bg-[var(--color-border)]/40" />

      {/* Hard gates row — VITAL for dip-buy validity */}
      <div className="grid grid-cols-3 gap-1.5">
        <GateCell label="Likuiditas" pass={data.gate_volume} />
        <GateCell label="Tidak Overbeli" pass={data.gate_not_overbought} />
        <GateCell label="Diskon" pass={data.gate_discounted} />
      </div>
      {!data.all_gates_pass && (
        <div className="text-[9px] text-[var(--color-fg-faint)] italic px-0.5">
          Salah satu filter ketat belum lolos — sinyal belum valid untuk dip-buy.
        </div>
      )}

      {/* Candle Patterns row (integrated, was floating card before) */}
      {patterns && patterns.length > 0 && (
        <div>
          <div className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold mb-1.5">
            Pola Candle Multi-TF ({patterns.length})
          </div>
          <div className="flex flex-wrap gap-1">
            {patterns.map((p, i) => {
              const isBull = BULL_PATTERNS.has(p.pattern);
              const isBear = BEAR_PATTERNS.has(p.pattern);
              const tone = isBull
                ? "var(--color-success)"
                : isBear
                  ? "oklch(72% 0.16 35)"
                  : "var(--color-fg-muted)";
              const tfHeavy = p.tf === "4h" || p.tf === "1d";
              return (
                <span
                  key={`${p.tf}-${p.pattern}-${i}`}
                  className="text-[9px] px-1.5 py-0.5 rounded ring-1 flex items-center gap-1 whitespace-nowrap"
                  style={{
                    color: tone,
                    background: `color-mix(in oklch, ${tone} ${tfHeavy ? 11 : 6}%, transparent)`,
                    borderColor: `color-mix(in oklch, ${tone} ${tfHeavy ? 32 : 20}%, transparent)`,
                    fontWeight: tfHeavy ? 700 : 500,
                  }}
                  title={`${PATTERN_LABELS[p.pattern] ?? p.pattern} pada ${p.tf}`}
                >
                  <span className="opacity-60">{p.tf}</span>
                  <span>{PATTERN_LABELS[p.pattern] ?? p.pattern}</span>
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Sizing recommendation when valid signal */}
      {data.all_gates_pass && (data.sizing_pct_equity ?? 0) > 0 && (
        <div
          className="rounded-[var(--radius-sm)] px-2.5 py-1.5 ring-1 flex items-center justify-between"
          style={{
            background: "color-mix(in oklch, var(--color-accent) 10%, transparent)",
            borderColor: "color-mix(in oklch, var(--color-accent) 40%, transparent)",
          }}
        >
          <span className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)]">
            Saran Ukuran Entry
          </span>
          <span className="text-[12px] font-bold text-[var(--color-accent)] num">
            {data.sizing_pct_equity}% dari equity
          </span>
        </div>
      )}

      {/* Trend + Pattern row — inline chips, hide empty placeholders */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <TrendCell trend={data.trend_4h} pctVsEma={data.price_vs_ema50_pct} />
        {data.rsi_bullish_divergence_4h && (
          <SignalChip label="Divergensi RSI Bull" tone="good" />
        )}
        {data.rsi_bearish_divergence_4h && (
          <SignalChip label="Divergensi RSI Bear" tone="bad" />
        )}
        {data.three_bar_reversal_1h && (
          <SignalChip label="Pembalik 3-bar 1h" tone="good" />
        )}
        {!data.rsi_bullish_divergence_4h &&
          !data.rsi_bearish_divergence_4h &&
          !data.three_bar_reversal_1h && (
            <span className="text-[9px] text-[var(--color-fg-faint)] px-1.5 py-0.5">
              Belum ada sinyal pembalikan
            </span>
          )}
      </div>

      <div className="h-px bg-[var(--color-border)]/40" />

      {/* MTF RSI Grid — 4 timeframes side-by-side */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] flex items-center gap-1.5">
            <Activity size={11} />
            RSI Multi-Timeframe
          </span>
          <span className="text-[9px] text-[var(--color-fg-faint)]">
            oversold {data.mtf_oversold_count}/4 ·{" "}
            overbeli {data.mtf_overbought_count}/4
          </span>
        </div>
        <div className="grid grid-cols-4 gap-1.5">
          <RsiCell label="15m" value={data.rsi_15m} />
          <RsiCell label="1h" value={data.rsi_1h} />
          <RsiCell label="4h" value={data.rsi_4h} />
          <RsiCell label="1d" value={data.rsi_1d} />
        </div>
      </div>

      {/* BB position + lower touch */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] flex items-center gap-1.5">
            <Target size={11} />
            Bollinger 4h
          </span>
          {data.bb_lower_touch && (
            <span className="text-[9px] uppercase tracking-wider font-bold text-[var(--color-success)] flex items-center gap-0.5">
              <Zap size={10} /> SENTUH BAWAH
            </span>
          )}
        </div>
        {data.bb_position_4h !== null ? (
          <>
            <div className="relative h-2 rounded-full bg-gradient-to-r from-[var(--color-success)]/30 via-[var(--color-fg-faint)]/10 to-[var(--color-danger)]/30 overflow-hidden">
              <motion.div
                initial={false}
                animate={{ left: `${Math.max(0, Math.min(100, data.bb_position_4h * 100))}%` }}
                transition={{ duration: 0.5, ease: [0.34, 1.4, 0.4, 1] }}
                className="absolute -top-1 -bottom-1 w-0.5 bg-white"
                style={{ boxShadow: "0 0 4px white" }}
              />
            </div>
            <div className="flex justify-between text-[9px] text-[var(--color-fg-faint)] mt-0.5 num">
              <span>{data.bb_lower_4h !== null ? data.bb_lower_4h.toFixed(2) : "—"}</span>
              <span>{data.bb_middle_4h !== null ? data.bb_middle_4h.toFixed(2) : "—"}</span>
              <span>{data.bb_upper_4h !== null ? data.bb_upper_4h.toFixed(2) : "—"}</span>
            </div>
          </>
        ) : (
          <div className="text-[10px] text-[var(--color-fg-faint)]">no data</div>
        )}
      </div>

      {/* Distance from highs */}
      <div className="grid grid-cols-2 gap-2">
        <DiscountCell
          label="Diskon 7 hari"
          value={data.dist_from_7d_high_pct}
          high={data.high_7d}
        />
        <DiscountCell
          label="Diskon 30 hari"
          value={data.dist_from_30d_high_pct}
          high={data.high_30d}
        />
      </div>

      {/* Capitulation flag */}
      {data.volume_capitulation && (
        <div className="rounded-[var(--radius-sm)] bg-[var(--color-success-soft)] ring-1 ring-[var(--color-success)]/40 px-2.5 py-1.5 flex items-center gap-2">
          <Flame size={12} className="text-[var(--color-success)]" />
          <div className="leading-tight flex-1">
            <div className="text-[10px] uppercase tracking-wider font-bold text-[var(--color-success)]">
              Capitulation terdeteksi
            </div>
            <div className="text-[9px] text-[var(--color-fg-muted)]">
              Volume meledak di candle merah — seller mungkin habis
            </div>
          </div>
        </div>
      )}

      {/* VWAP + MTF Sequence */}
      <div className="grid grid-cols-2 gap-1.5 text-[10px]">
        <MiniMetric
          label="Jarak VWAP 4h"
          value={
            data.vwap_dist_pct != null
              ? `${data.vwap_dist_pct > 0 ? "+" : ""}${data.vwap_dist_pct.toFixed(2)}%`
              : "—"
          }
          hint={
            data.vwap_dist_pct == null
              ? "—"
              : data.vwap_dist_pct < -5
                ? "✓ harga institutional murah"
                : data.vwap_dist_pct < -2
                  ? "di bawah VWAP"
                  : data.vwap_dist_pct > 5
                    ? "zona premium / mahal"
                    : "harga wajar"
          }
          tone={
            data.vwap_dist_pct == null
              ? "neutral"
              : data.vwap_dist_pct < -2
                ? "good"
                : data.vwap_dist_pct > 5
                  ? "bad"
                  : "neutral"
          }
        />
        <MiniMetric
          label="Pola Telescoping"
          value={
            (data.mtf_sequence_bonus ?? 0) > 0 ? "TERDETEKSI" : "—"
          }
          hint={
            (data.mtf_sequence_bonus ?? 0) > 0
              ? "15m > 1h > 4h naik"
              : "belum ada pembalikan"
          }
          tone={(data.mtf_sequence_bonus ?? 0) > 0 ? "good" : "neutral"}
        />
      </div>

      {/* OI/Funding/OB removed — see tab "Makro & Flow" for richer view */}

      {/* Breakdown */}
      {data.confluence_breakdown && data.confluence_breakdown.length > 0 && (
        <>
          <div className="h-px bg-[var(--color-border)]/40" />
          <div>
            <div className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] mb-1.5">
              Rincian Skor
            </div>
            <div className="space-y-1">
              {data.confluence_breakdown.map((b, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between text-[10px]"
                >
                  <span className="text-[var(--color-fg-muted)] truncate flex-1">
                    {b.name}
                  </span>
                  <span className="flex items-center gap-2 shrink-0">
                    <span className="text-[var(--color-fg-faint)] num text-[9px] max-w-[140px] truncate">
                      {typeof b.value === "number" ? b.value.toFixed(2) : b.value}
                    </span>
                    <span
                      className="num font-semibold w-10 text-right"
                      style={{
                        color:
                          b.points > 0
                            ? "var(--color-success)"
                            : b.points < 0
                              ? "var(--color-danger)"
                              : "var(--color-fg-muted)",
                      }}
                    >
                      {b.points > 0 ? "+" : ""}
                      {b.points}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function RsiCell({ label, value }: { label: string; value: number | null }) {
  if (value === null) {
    return (
      <div className="rounded-[var(--radius-sm)] bg-white/[0.02] ring-1 ring-[var(--color-border)] px-1.5 py-1 flex items-center justify-between">
        <span className="text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)] font-bold">
          {label}
        </span>
        <span className="text-[11px] text-[var(--color-fg-faint)] num">—</span>
      </div>
    );
  }
  const tone =
    value < 30
      ? "var(--color-success)"
      : value > 70
        ? "var(--color-danger)"
        : value < 40
          ? "oklch(78% 0.17 165 / 0.75)"
          : value > 60
            ? "oklch(72% 0.18 30 / 0.75)"
            : "var(--color-fg-muted)";
  const showStatus = value < 30 || value > 70;
  return (
    <div
      className="rounded-[var(--radius-sm)] px-2 py-1 ring-1 flex items-center justify-between"
      style={{
        background: `color-mix(in oklch, ${tone} 10%, transparent)`,
        borderColor: `color-mix(in oklch, ${tone} 35%, transparent)`,
      }}
    >
      <span className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-bold">
        {label}
      </span>
      <div className="flex items-baseline gap-1">
        <span className="num text-[13px] font-bold leading-none" style={{ color: tone }}>
          {value.toFixed(0)}
        </span>
        {showStatus && (
          <span className="text-[8px] font-bold" style={{ color: tone }}>
            {value < 30 ? "↓OS" : "↑OB"}
          </span>
        )}
      </div>
    </div>
  );
}

function DiscountCell({
  label,
  value,
  high,
}: {
  label: string;
  value: number | null;
  high: number | null;
}) {
  if (value === null) {
    return (
      <div className="rounded-[var(--radius-sm)] bg-white/[0.02] ring-1 ring-[var(--color-border)] px-2 py-1.5">
        <div className="text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)]">
          {label}
        </div>
        <div className="text-[10px] text-[var(--color-fg-faint)]">—</div>
      </div>
    );
  }
  const tone =
    value < -20
      ? "var(--color-success)"
      : value < -10
        ? "oklch(78% 0.17 165 / 0.8)"
        : value < -3
          ? "var(--color-fg-muted)"
          : "var(--color-danger)";
  const label2 =
    value < -25
      ? "DEEP DIP"
      : value < -15
        ? "Discounted"
        : value < -8
          ? "Pullback"
          : value < -2
            ? "Mild"
            : "Near peak";
  return (
    <div
      className="rounded-[var(--radius-sm)] ring-1 px-2 py-1.5"
      style={{
        background: `color-mix(in oklch, ${tone} 8%, transparent)`,
        borderColor: `color-mix(in oklch, ${tone} 30%, transparent)`,
      }}
    >
      <div className="flex items-center justify-between mb-0.5">
        <span className="text-[8px] uppercase tracking-wider text-[var(--color-fg-subtle)]">
          {label}
        </span>
        <span className="text-[8px] uppercase tracking-wider font-bold" style={{ color: tone }}>
          {label2}
        </span>
      </div>
      <div className="num text-[13px] font-bold" style={{ color: tone }}>
        {value > 0 ? "+" : ""}
        {value.toFixed(1)}%
      </div>
      {high !== null && (
        <div className="text-[8px] text-[var(--color-fg-faint)] num truncate">
          high {high.toFixed(high >= 1 ? 2 : 6)}
        </div>
      )}
    </div>
  );
}

function GateCell({ label, pass }: { label: string; pass: boolean | undefined }) {
  const color = pass
    ? "var(--color-success)"
    : pass === false
      ? "var(--color-danger)"
      : "var(--color-fg-muted)";
  return (
    <div
      className="rounded-[var(--radius-sm)] px-2 py-1 ring-1 flex items-center justify-between gap-1"
      style={{
        background: pass
          ? "color-mix(in oklch, var(--color-success) 8%, transparent)"
          : "color-mix(in oklch, var(--color-danger) 6%, transparent)",
        borderColor: pass
          ? "color-mix(in oklch, var(--color-success) 35%, transparent)"
          : "color-mix(in oklch, var(--color-danger) 25%, transparent)",
      }}
    >
      <span className="text-[8px] uppercase tracking-wider text-[var(--color-fg-subtle)] truncate">
        {label}
      </span>
      {pass ? (
        <CheckCircle size={10} style={{ color }} />
      ) : (
        <XCircle size={10} style={{ color }} />
      )}
    </div>
  );
}

function TrendCell({
  trend,
  pctVsEma,
}: {
  trend?: string | null;
  pctVsEma?: number | null;
}) {
  const tone =
    trend === "uptrend"
      ? "var(--color-success)"
      : trend === "downtrend"
        ? "var(--color-danger)"
        : "var(--color-fg-muted)";
  const Icon =
    trend === "uptrend" ? TrendingUp : trend === "downtrend" ? TrendingDown : Activity;
  return (
    <div
      className="rounded-[var(--radius-sm)] px-2 py-1 ring-1 flex flex-col gap-0.5"
      style={{
        background: `color-mix(in oklch, ${tone} 6%, transparent)`,
        borderColor: `color-mix(in oklch, ${tone} 28%, transparent)`,
      }}
    >
      <div className="flex items-center justify-between gap-1">
        <span className="text-[8px] uppercase tracking-wider text-[var(--color-fg-subtle)]">
          Tren 4h
        </span>
        <Icon size={10} style={{ color: tone }} />
      </div>
      <div className="text-[10px] font-semibold" style={{ color: tone }}>
        {trend === "uptrend"
          ? "Naik"
          : trend === "downtrend"
            ? "Turun"
            : trend === "sideways"
              ? "Datar"
              : "—"}
      </div>
      {pctVsEma != null && (
        <div className="text-[8px] text-[var(--color-fg-faint)] num">
          {pctVsEma > 0 ? "+" : ""}
          {pctVsEma.toFixed(2)}% vs EMA50
        </div>
      )}
    </div>
  );
}

function SignalChip({
  label,
  tone,
}: {
  label: string;
  tone: "good" | "bad" | "neutral";
}) {
  const color =
    tone === "good"
      ? "var(--color-success)"
      : tone === "bad"
        ? "var(--color-danger)"
        : "var(--color-fg-muted)";
  return (
    <span
      className="inline-flex items-center gap-1 text-[9px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded-[var(--radius-sm)] ring-1"
      style={{
        color,
        background: `color-mix(in oklch, ${color} 10%, transparent)`,
        borderColor: `color-mix(in oklch, ${color} 30%, transparent)`,
      }}
    >
      ⚡ {label}
    </span>
  );
}

function MiniMetric({
  label,
  icon,
  value,
  hint,
  tone,
}: {
  label: string;
  icon?: React.ReactNode;
  value: string;
  hint?: string;
  tone: "good" | "bad" | "neutral";
}) {
  const c =
    tone === "good"
      ? "var(--color-success)"
      : tone === "bad"
        ? "var(--color-danger)"
        : "var(--color-fg-muted)";
  return (
    <div className="rounded-[var(--radius-sm)] bg-white/[0.02] ring-1 ring-[var(--color-border)] px-2 py-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[8px] uppercase tracking-wider text-[var(--color-fg-subtle)] flex items-center gap-1">
          {icon && <span style={{ color: c }}>{icon}</span>}
          {label}
        </span>
        <span
          className={cn("num font-semibold text-[11px]")}
          style={{ color: tone === "neutral" ? "var(--color-fg)" : c }}
        >
          {value}
        </span>
      </div>
      {hint && (
        <div className="text-[8px] mt-0.5 uppercase tracking-wider" style={{ color: c }}>
          {hint}
        </div>
      )}
    </div>
  );
}
