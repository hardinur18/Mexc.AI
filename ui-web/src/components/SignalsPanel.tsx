import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Sparkles,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Search,
  Filter,
  ChevronDown,
  ChevronRight,
  Grid3x3,
  List,
} from "lucide-react";
import { useSignals, useSnapshot, useCircuitBreaker } from "@/hooks/useSnapshot";
import { cn } from "@/lib/cn";
import type { Signal } from "@/types/position";
import { toast } from "sonner";
import { startCascade } from "@/lib/api";
import { MtfConvergenceRing } from "@/components/analytics/MtfConvergenceRing";
import { PatternTriggerBadge } from "@/components/analytics/PatternTriggerBadge";
import { PerAccountAllocation } from "@/components/analytics/PerAccountAllocation";
import { MacroContextCard } from "@/components/analytics/MacroContextCard";
import { LiquidityZonesCard } from "@/components/analytics/LiquidityZonesCard";
import { VolumeProfileCard } from "@/components/analytics/VolumeProfileCard";
import { OrderBookHeatmapCard } from "@/components/analytics/OrderBookHeatmapCard";
import { CumulativeDeltaCard } from "@/components/analytics/CumulativeDeltaCard";
import { LiquidationClusterCard } from "@/components/analytics/LiquidationClusterCard";
import { SLInvalidationCard } from "@/components/analytics/SLInvalidationCard";
import { MarketRegimeCard } from "@/components/analytics/MarketRegimeCard";
import { LiquidationZonesPhase5Card } from "@/components/analytics/LiquidationZonesPhase5Card";
import { CVDHistoryCard } from "@/components/analytics/CVDHistoryCard";
import { SignalQualityCard } from "@/components/analytics/SignalQualityCard";
import { SignalTickerTape } from "@/components/analytics/SignalTickerTape";
import { SignalHeatmapGrid } from "@/components/analytics/SignalHeatmapGrid";
import { EntryPlanCard } from "@/components/positions/EntryPlanCard";

type DirFilter = "ALL" | "LONG" | "SHORT";
type SortKey = "score" | "volume" | "discount" | "symbol" | "mtf";

export function SignalsPanelInner() {
  const [minScore, setMinScore] = useState(45);
  const [dirFilter, setDirFilter] = useState<DirFilter>("ALL");
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"list" | "heatmap">("list");
  const { data, isLoading } = useSignals(minScore);
  const { data: snap } = useSnapshot();
  const { data: breaker } = useCircuitBreaker();
  const cascadeDisabled = !!(breaker?.tripped || breaker?.cooldown_active);
  const cascadeDisabledReason = breaker?.tripped
    ? "Circuit breaker tripped — daily loss limit"
    : breaker?.cooldown_active
      ? breaker.cooldown_reason
      : null;
  const accounts = snap?.accounts ?? [];
  const equityUsd = snap?.account.equity ?? 0;

  const filteredSignals = useMemo(() => {
    if (!data) return [];
    let list = data.signals;
    if (dirFilter !== "ALL") {
      list = list.filter((s) => s.direction === dirFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((s) => s.symbol.toLowerCase().includes(q));
    }
    const sorted = [...list].sort((a, b) => {
      switch (sortKey) {
        case "volume":
          return (b.volume_24h_usdt ?? 0) - (a.volume_24h_usdt ?? 0);
        case "discount":
          if (a.direction === "SHORT" && b.direction === "SHORT") {
            return (b.dist_from_7d_low_pct ?? 0) - (a.dist_from_7d_low_pct ?? 0);
          }
          return (a.dist_from_7d_high_pct ?? 0) - (b.dist_from_7d_high_pct ?? 0);
        case "mtf":
          return (b.mtf_convergence?.score ?? 0) - (a.mtf_convergence?.score ?? 0);
        case "symbol":
          return a.symbol.localeCompare(b.symbol);
        case "score":
        default:
          return b.confluence_score - a.confluence_score;
      }
    });
    return sorted;
  }, [data, dirFilter, sortKey, search]);

  const longCount = data?.signals.filter((s) => s.direction === "LONG").length ?? 0;
  const shortCount = data?.signals.filter((s) => s.direction === "SHORT").length ?? 0;

  return (
    <div className="px-4 pb-4">
      <div className="flex items-center justify-between py-2.5 text-[10px] text-[var(--color-fg-faint)] uppercase tracking-wider">
        <div className="flex items-center gap-3">
          <span>
            {filteredSignals.length} dari {data?.signal_count ?? 0} sinyal
          </span>
          {data && (
            <>
              <span className="text-[var(--color-fg-faint)]">·</span>
              <span className="flex items-center gap-1 text-[var(--color-success)]">
                <TrendingUp size={9} /> {longCount}L
              </span>
              <span className="flex items-center gap-1 text-[var(--color-danger)]">
                <TrendingDown size={9} /> {shortCount}S
              </span>
            </>
          )}
        </div>
        {data && (
          <span>scan {data.scanned_count} koin · {data.latency_ms}ms</span>
        )}
      </div>

      {/* Ticker tape — top signals scrolling marquee */}
      <SignalTickerTape signals={data?.signals} />

      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <SegmentedControl
          value={dirFilter}
          onChange={(v) => setDirFilter(v as DirFilter)}
          options={[
            { value: "ALL", label: "Semua" },
            { value: "LONG", label: "LONG", icon: <TrendingUp size={9} /> },
            { value: "SHORT", label: "SHORT", icon: <TrendingDown size={9} /> },
          ]}
        />
        {/* View mode toggle */}
        <div className="inline-flex items-center bg-white/5 ring-1 ring-[var(--color-border)] rounded-[var(--radius-md)] p-0.5">
          <button
            onClick={() => setViewMode("list")}
            className={cn(
              "text-[10px] px-2 py-1 rounded-[var(--radius-sm)] font-medium transition flex items-center gap-1",
              viewMode === "list"
                ? "bg-[var(--color-bg-elev-2)] text-[var(--color-accent)]"
                : "text-[var(--color-fg-subtle)] hover:text-[var(--color-fg)]",
            )}
          >
            <List size={9} /> List
          </button>
          <button
            onClick={() => setViewMode("heatmap")}
            className={cn(
              "text-[10px] px-2 py-1 rounded-[var(--radius-sm)] font-medium transition flex items-center gap-1",
              viewMode === "heatmap"
                ? "bg-[var(--color-bg-elev-2)] text-[var(--color-accent)]"
                : "text-[var(--color-fg-subtle)] hover:text-[var(--color-fg)]",
            )}
          >
            <Grid3x3 size={9} /> Heatmap
          </button>
        </div>
        <ToolbarDropdown
          icon={<Filter size={10} />}
          label="Skor"
          value={`≥${minScore}`}
          options={[
            { value: "30", label: "≥30 (longgar)" },
            { value: "45", label: "≥45 (default)" },
            { value: "60", label: "≥60 (ketat)" },
            { value: "80", label: "≥80 (premium)" },
          ]}
          onChange={(v) => setMinScore(Number(v))}
        />
        <ToolbarDropdown
          label="Urut"
          value={SORT_LABELS[sortKey]}
          options={[
            { value: "score", label: "Confluence Score" },
            { value: "mtf", label: "MTF Convergence" },
            { value: "volume", label: "Volume 24h" },
            { value: "discount", label: "Diskon terjauh" },
            { value: "symbol", label: "Symbol A-Z" },
          ]}
          onChange={(v) => setSortKey(v as SortKey)}
        />
        <div className="relative ml-auto">
          <Search
            size={11}
            className="absolute left-2 top-1/2 -translate-y-1/2 text-[var(--color-fg-faint)]"
          />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Cari koin..."
            className="text-[10px] pl-7 pr-2 py-1 w-[140px] rounded-[var(--radius-sm)] bg-white/5 ring-1 ring-[var(--color-border)] text-[var(--color-fg)] focus:outline-none focus:ring-[var(--color-accent)]/40 placeholder:text-[var(--color-fg-faint)]"
          />
        </div>
      </div>

      {/* Heatmap mode */}
      {viewMode === "heatmap" && data && (
        <SignalHeatmapGrid
          signals={filteredSignals}
          onSelect={(sym) => {
            setExpanded(sym);
            setViewMode("list");
          }}
        />
      )}

      {viewMode === "list" && isLoading ? (
        <div className="text-[11px] text-[var(--color-fg-subtle)] py-4 text-center">
          Memindai koin berkualitas...
        </div>
      ) : viewMode === "list" && filteredSignals.length === 0 ? (
        <div className="py-6 text-center">
          <div className="text-[11px] text-[var(--color-fg-subtle)] mb-1">
            Belum ada setup {dirFilter !== "ALL" ? dirFilter : ""} di skor ≥{minScore}
          </div>
          <div className="text-[10px] text-[var(--color-fg-faint)] flex items-center justify-center gap-1.5">
            <AlertTriangle size={10} />
            Sabar &gt; FOMO. Tunggu confluence kuat.
          </div>
        </div>
      ) : (
        <motion.div
          initial="hidden"
          animate="visible"
          variants={{
            hidden: {},
            visible: { transition: { staggerChildren: 0.04 } },
          }}
          className="space-y-1.5"
        >
          {viewMode === "list" &&
            filteredSignals.map((s) => (
              <SignalRow
                key={s.symbol}
                signal={s}
                isExpanded={expanded === s.symbol}
                onToggle={() => setExpanded((cur) => (cur === s.symbol ? null : s.symbol))}
                accounts={accounts}
                equityUsd={equityUsd}
                cascadeDisabled={cascadeDisabled}
                cascadeDisabledReason={cascadeDisabledReason}
              />
            ))}
        </motion.div>
      )}
    </div>
  );
}

export function SignalsPanel() {
  return <SignalsPanelInner />;
}

const SORT_LABELS: Record<SortKey, string> = {
  score: "Skor",
  mtf: "MTF",
  volume: "Volume",
  discount: "Diskon",
  symbol: "A-Z",
};

function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string; icon?: React.ReactNode }[];
}) {
  return (
    <div className="inline-flex items-center bg-white/5 ring-1 ring-[var(--color-border)] rounded-[var(--radius-md)] p-0.5">
      {options.map((opt) => {
        const active = opt.value === value;
        const tone =
          opt.value === "LONG"
            ? "var(--color-success)"
            : opt.value === "SHORT"
              ? "var(--color-danger)"
              : "var(--color-accent)";
        return (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            className={cn(
              "text-[10px] px-2.5 py-1 rounded-[var(--radius-sm)] font-medium transition flex items-center gap-1",
              active
                ? "bg-[var(--color-bg-elev-2)] shadow-sm"
                : "text-[var(--color-fg-subtle)] hover:text-[var(--color-fg)]",
            )}
            style={active ? { color: tone, boxShadow: `0 0 0 1px ${tone}40` } : undefined}
          >
            {opt.icon}
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

function ToolbarDropdown({
  icon,
  label,
  value,
  options,
  onChange,
}: {
  icon?: React.ReactNode;
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wider bg-white/5 ring-1 ring-[var(--color-border)] rounded-[var(--radius-md)] px-2 py-1 hover:bg-white/10 transition cursor-pointer">
      {icon && <span className="text-[var(--color-fg-subtle)]">{icon}</span>}
      <span className="text-[var(--color-fg-subtle)]">{label}:</span>
      <select
        value={options.find((o) => o.label.startsWith(value))?.value ?? value}
        onChange={(e) => onChange(e.target.value)}
        className="bg-transparent text-[var(--color-fg)] focus:outline-none cursor-pointer font-medium normal-case tracking-normal pr-1"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value} className="bg-[var(--color-bg-elev)]">
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function SignalRow({
  signal,
  isExpanded,
  onToggle,
  accounts,
  equityUsd,
  cascadeDisabled,
  cascadeDisabledReason,
}: {
  signal: Signal;
  isExpanded: boolean;
  onToggle: () => void;
  accounts: import("@/types/position").AccountSummary[];
  equityUsd: number;
  cascadeDisabled?: boolean;
  cascadeDisabledReason?: string | null;
}) {
  const score = signal.confluence_score;
  const verdict = signal.verdict || "WATCH";
  const direction = signal.direction ?? "NONE";
  const isLong = direction === "LONG";
  const isShort = direction === "SHORT";
  const tone = isLong
    ? "var(--color-success)"
    : isShort
      ? "var(--color-danger)"
      : score >= 45
        ? "var(--color-warning)"
        : "var(--color-fg-muted)";
  const DirIcon = isLong ? TrendingUp : isShort ? TrendingDown : Sparkles;
  const patternCount = signal.candle_pattern_summary?.length ?? 0;
  const mtfScore = signal.mtf_convergence?.score;
  const trigger = signal.primary_pattern_trigger;
  const liqCluster = signal.liquidation_cluster;
  const wyckoff = signal.wyckoff_spring_upthrust;
  const hasSpring = !!wyckoff?.spring;
  const hasUpthrust = !!wyckoff?.upthrust;

  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, x: -6 },
        visible: { opacity: 1, x: 0 },
      }}
      transition={{ duration: 0.25, ease: [0.34, 1.4, 0.4, 1] }}
      className="rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] overflow-hidden hover:ring-[var(--color-border-strong)] transition-shadow"
    >
      {/* Compact summary row */}
      <button
        type="button"
        onClick={onToggle}
        className="w-full grid grid-cols-[16px_1.2fr_56px_1fr_auto_auto] gap-3 items-center px-3 py-2 text-left hover:bg-white/[0.02] transition"
      >
        <span className="text-[var(--color-fg-subtle)]">
          {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </span>

        <div className="flex items-center gap-2 min-w-0">
          <span
            className="px-1.5 py-0.5 rounded-[var(--radius-sm)] text-[9px] font-bold uppercase tracking-wider ring-1 flex items-center gap-1 shrink-0"
            style={{
              color: tone,
              background: `color-mix(in oklch, ${tone} 12%, transparent)`,
              borderColor: `color-mix(in oklch, ${tone} 40%, transparent)`,
            }}
          >
            <DirIcon size={10} />
            {direction}
          </span>
          <div className="leading-tight min-w-0">
            <div className="text-xs font-semibold truncate flex items-center gap-1.5">
              {signal.symbol}
              {liqCluster?.detected && (
                <span
                  className="text-[8px] px-1 py-0.5 rounded font-bold uppercase tracking-wider"
                  style={{
                    color: liqCluster.side === "long_squeeze" ? "var(--color-danger)" : "var(--color-success)",
                    background: `color-mix(in oklch, ${liqCluster.side === "long_squeeze" ? "var(--color-danger)" : "var(--color-success)"} 14%, transparent)`,
                  }}
                >
                  💥 squeeze
                </span>
              )}
              {hasSpring && (
                <span
                  className="text-[8px] px-1 py-0.5 rounded font-bold uppercase tracking-wider text-[var(--color-success)] bg-[var(--color-success-soft)]"
                >
                  ⚡ spring
                </span>
              )}
              {hasUpthrust && (
                <span
                  className="text-[8px] px-1 py-0.5 rounded font-bold uppercase tracking-wider text-[var(--color-danger)] bg-[var(--color-danger-soft)]"
                >
                  ⚡ upthrust
                </span>
              )}
            </div>
            <div className="text-[10px] text-[var(--color-fg-faint)] flex items-center gap-1.5">
              {isLong && (signal.mtf_oversold_count ?? 0) > 0 && (
                <span className="text-[var(--color-success)]">
                  {signal.mtf_oversold_count}/4 oversold
                </span>
              )}
              {isShort && (signal.mtf_overbought_count ?? 0) > 0 && (
                <span className="text-[var(--color-danger)]">
                  {signal.mtf_overbought_count}/4 overbeli
                </span>
              )}
              {signal.bb_lower_touch && isLong && (
                <span className="text-[var(--color-success)]">· BB bawah</span>
              )}
              {patternCount > 0 && (
                <span className="text-[var(--color-accent)]">· {patternCount} pola</span>
              )}
            </div>
          </div>
        </div>

        <div className="text-right">
          <div className="text-base font-bold num leading-none" style={{ color: tone }}>
            {score}
          </div>
          <div className="text-[8px] uppercase tracking-wider font-bold" style={{ color: tone }}>
            {verdict}
          </div>
        </div>

        <div className="grid grid-cols-4 gap-0.5 text-[9px] num">
          <MtfRsi label="15m" v={signal.rsi_15m} />
          <MtfRsi label="1h" v={signal.rsi_1h} />
          <MtfRsi label="4h" v={signal.rsi_4h} />
          <MtfRsi label="1d" v={signal.rsi_1d} />
        </div>

        {/* MTF Convergence pill */}
        {mtfScore != null && (
          <div
            className="text-center leading-tight px-2 py-1 rounded-[var(--radius-sm)] ring-1"
            style={{
              color: mtfScore >= 60 ? tone : "var(--color-fg-muted)",
              background: `color-mix(in oklch, ${mtfScore >= 60 ? tone : "var(--color-fg-muted)"} 8%, transparent)`,
              borderColor: `color-mix(in oklch, ${mtfScore >= 60 ? tone : "var(--color-fg-muted)"} 30%, transparent)`,
            }}
            title="Multi-TF Convergence"
          >
            <div className="text-[8px] uppercase tracking-wider opacity-70">MTF</div>
            <div className="text-[11px] font-bold num">{mtfScore}</div>
          </div>
        )}

        <div className="text-right leading-tight">
          {signal.entry_plan?.entry_price != null && (
            <div className="text-[10px] num font-semibold" style={{ color: tone }}>
              entry @{" "}
              {signal.entry_plan.entry_price.toLocaleString("en-US", {
                maximumFractionDigits: 6,
              })}
            </div>
          )}
          {(signal.sizing_pct_equity ?? 0) > 0 && (
            <div className="text-[9px] text-[var(--color-accent)] font-bold">
              size {signal.sizing_pct_equity}% eq
            </div>
          )}
        </div>
      </button>

      {/* Expanded ultra-detail panel */}
      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.34, 1.4, 0.4, 1] }}
            className="overflow-hidden border-t border-[var(--color-border)]/40"
          >
            <div className="p-3 space-y-3 bg-gradient-to-b from-black/30 to-transparent">
              {/* Row 1: Pattern Trigger + MTF Convergence Ring */}
              <div className="flex flex-wrap items-center gap-3">
                {trigger && (
                  <PatternTriggerBadge trigger={trigger} direction={direction} />
                )}
                {signal.mtf_convergence && (
                  <MtfConvergenceRing
                    data={signal.mtf_convergence}
                    direction={direction}
                  />
                )}
              </div>

              {/* Row 2: Liquidation cluster (if any) */}
              {liqCluster?.detected && (
                <LiquidationClusterCard data={liqCluster} />
              )}

              {/* Row 2b: Market regime + BTC alignment + basis */}
              <MarketRegimeCard
                regime={signal.market_regime}
                btcAlignment={signal.btc_correlation_alignment}
                basis={signal.spot_futures_basis}
              />

              {/* Row 2c: Signal Quality (Phase 14 unified card) */}
              <SignalQualityCard
                adjustments={signal.macro_score_adjustments}
                fundingWindow={signal.funding_window}
                fundingArb={signal.funding_arb_signal}
                volumeConfirmation={signal.volume_confirmation_4h}
                liquidityGrab4h={signal.liquidity_grab_4h}
                liquidityGrab1h={signal.liquidity_grab_1h}
                sweep15m={signal.liquidity_sweep_15m}
                dynamicLevBand={signal.dynamic_lev_band}
                dynamicLevMult={signal.dynamic_lev_mult}
                direction={direction}
              />

              {/* Row 3: SL Invalidation + R:R */}
              <SLInvalidationCard
                sl={signal.sl_invalidation}
                rr={signal.rr_ratio}
                entryPrice={signal.entry_plan?.entry_price}
                direction={direction}
              />

              {/* Row 4: Entry plan + Per-account allocation */}
              <div className="grid grid-cols-1 lg:grid-cols-[1.3fr_1fr] gap-3">
                <EntryPlanCard
                  plan={signal.entry_plan}
                  verdict={signal.verdict ?? "—"}
                  score={score}
                  sizingPct={signal.sizing_pct_equity}
                  equityUsd={equityUsd}
                />
                <PerAccountAllocation plan={signal.entry_plan} accounts={accounts} />
              </div>

              {/* Cascade start buttons per account */}
              <div className="rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] p-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
                    Start Cascade
                  </div>
                  {cascadeDisabled && (
                    <span className="text-[9px] uppercase tracking-wider font-bold text-[var(--color-danger)] px-1.5 py-0.5 rounded bg-[var(--color-danger-soft)] ring-1 ring-[var(--color-danger)]/30">
                      🛑 BLOCKED · {cascadeDisabledReason}
                    </span>
                  )}
                </div>
                <div className={cn("flex flex-wrap gap-1.5", cascadeDisabled && "opacity-40 pointer-events-none")}>
                  {accounts.map((acc) => (
                    <CascadeStartButton
                      key={acc.id}
                      symbol={signal.symbol}
                      accountId={acc.id}
                      accountName={acc.name}
                      colorVar={`var(--color-${acc.color}, var(--color-accent))`}
                    />
                  ))}
                </div>
              </div>

              {/* Row 5: Macro context */}
              <MacroContextCard a={signal as Partial<import("@/types/position").SymbolAnalytics>} />

              {/* Row 6: Liquidity zones + Volume Profile */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                <LiquidityZonesCard
                  zones={signal.sd_zones_4h}
                  springUpthrust={signal.wyckoff_spring_upthrust}
                  currentPrice={signal.entry_plan?.current_price ?? null}
                />
                <VolumeProfileCard
                  data={signal.volume_profile_4h}
                  currentPrice={signal.entry_plan?.current_price ?? null}
                />
              </div>

              {/* Row 7: Liquidation map estimate */}
              <LiquidationZonesPhase5Card
                zones={signal.liquidation_zones}
                currentPrice={signal.entry_plan?.current_price ?? null}
              />

              {/* Row 8: Order book + Cumulative delta + CVD history */}
              <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-3">
                <OrderBookHeatmapCard data={signal.orderbook_heatmap} />
                <CumulativeDeltaCard data={signal.cumulative_delta} />
              </div>
              <CVDHistoryCard data={signal.cvd_historical} />

              {/* Confluence breakdown */}
              {signal.breakdown && signal.breakdown.length > 0 && (
                <div className="rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] px-3 py-2.5">
                  <div className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold mb-1.5">
                    Confluence breakdown
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {signal.breakdown.map((b, i) => (
                      <span
                        key={i}
                        className={cn(
                          "text-[10px] px-1.5 py-0.5 rounded ring-1 num",
                          b.points > 0
                            ? "bg-[var(--color-success-soft)] text-[var(--color-success)] ring-[var(--color-success)]/30"
                            : b.points < 0
                              ? "bg-[var(--color-danger-soft)] text-[var(--color-danger)] ring-[var(--color-danger)]/30"
                              : "bg-white/5 text-[var(--color-fg-muted)] ring-[var(--color-border)]",
                        )}
                      >
                        {b.points > 0 ? "+" : ""}
                        {b.points} · {b.name.replace(/^[✓✗]\s/, "")}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function CascadeStartButton({
  symbol,
  accountId,
  accountName,
  colorVar,
}: {
  symbol: string;
  accountId: string;
  accountName: string;
  colorVar: string;
}) {
  const [pending, setPending] = useState(false);
  const handle = async (mode: "paper" | "live") => {
    setPending(true);
    try {
      const r = await startCascade(symbol, accountId, mode, 1.0);
      toast.success(`Cascade started ${mode.toUpperCase()} on ${accountName} (${r.cascade.id})`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Cascade start failed");
    } finally {
      setPending(false);
    }
  };
  return (
    <div
      className="inline-flex items-center rounded-[var(--radius-sm)] ring-1 overflow-hidden"
      style={{ borderColor: colorVar }}
    >
      <span
        className="text-[9px] uppercase tracking-wider px-2 py-1 font-semibold"
        style={{ color: colorVar }}
      >
        {accountName}
      </span>
      <button
        type="button"
        disabled={pending}
        onClick={() => handle("paper")}
        className="text-[9px] uppercase tracking-wider px-2 py-1 hover:bg-white/[0.05] transition border-l border-[var(--color-border)]/40 disabled:opacity-40"
        style={{ color: "var(--color-fg-muted)" }}
      >
        paper
      </button>
      <button
        type="button"
        disabled={pending}
        onClick={() => {
          if (!confirm(`Start LIVE cascade on ${accountName} untuk ${symbol}? Real money!`)) return;
          handle("live");
        }}
        className="text-[9px] uppercase tracking-wider px-2 py-1 hover:bg-[var(--color-warning-soft)] transition border-l border-[var(--color-border)]/40 disabled:opacity-40"
        style={{ color: "var(--color-warning)" }}
      >
        LIVE
      </button>
    </div>
  );
}

function MtfRsi({ label, v }: { label: string; v?: number | null }) {
  const tone =
    v == null
      ? "var(--color-fg-faint)"
      : v < 30
        ? "var(--color-success)"
        : v > 70
          ? "var(--color-danger)"
          : "var(--color-fg-muted)";
  return (
    <div
      className="rounded text-center px-1 py-0.5"
      style={{ background: `color-mix(in oklch, ${tone} 8%, transparent)` }}
    >
      <div className="text-[8px] text-[var(--color-fg-faint)] uppercase tracking-wider">
        {label}
      </div>
      <div className="num font-bold text-[10px]" style={{ color: tone }}>
        {v != null ? v.toFixed(0) : "—"}
      </div>
    </div>
  );
}
