import { VerticalLadder } from "./VerticalLadder";
import { ActionHints } from "./ActionHints";
import { PositionVitals } from "./PositionVitals";
import { PriceChart } from "./PriceChart";
import { AnalysisCard } from "./AnalysisCard";
import { EntryPlanCard } from "./EntryPlanCard";
import { SmcCard } from "./SmcCard";
import { useAnalytics, useSnapshot } from "@/hooks/useSnapshot";
import type { Position } from "@/types/position";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/Tabs";
import { Target, LineChart, Crosshair, Activity, Globe } from "lucide-react";
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

interface ExpandedDetailProps {
  p: Position;
}

export function ExpandedDetail({ p }: ExpandedDetailProps) {
  const { data: analytics } = useAnalytics(p.symbol);
  const { data: snapshot } = useSnapshot();
  const patterns = analytics?.candle_pattern_summary ?? [];
  const equityUsd = snapshot?.account.equity ?? 0;
  const accounts = snapshot?.accounts ?? [];
  const direction = analytics?.signal_direction ?? "NONE";

  // Filter pattern count: only direction-aligned + skip neutral patterns (doji, inside_bar)
  const NEUTRAL_PATTERNS = new Set(["doji", "inside_bar"]);
  const BULLISH_PATTERNS = new Set([
    "bullish_engulfing", "hammer", "bullish_pin_bar", "dragonfly_doji",
    "morning_star", "three_white_soldiers", "piercing_line", "tweezer_bottom",
    "bullish_harami",
  ]);
  const BEARISH_PATTERNS = new Set([
    "bearish_engulfing", "shooting_star", "bearish_pin_bar", "gravestone_doji",
    "evening_star", "three_black_crows", "dark_cloud_cover", "tweezer_top",
    "bearish_harami",
  ]);
  const alignedPatterns = patterns.filter((p) => {
    if (NEUTRAL_PATTERNS.has(p.pattern)) return false;
    if (direction === "LONG") return BULLISH_PATTERNS.has(p.pattern);
    if (direction === "SHORT") return BEARISH_PATTERNS.has(p.pattern);
    return BULLISH_PATTERNS.has(p.pattern) || BEARISH_PATTERNS.has(p.pattern);
  });
  const patternCount = alignedPatterns.length;

  // Smart Money tab: count significant signals
  const whaleActive = analytics?.whale_accumulation?.detected ?? false;
  const sweepActive =
    (analytics?.liquidity_sweep_4h?.bullish_sweep ||
      analytics?.liquidity_sweep_4h?.bearish_sweep) ??
    false;
  const springActive = !!analytics?.wyckoff_spring_upthrust?.spring;
  const upthrustActive = !!analytics?.wyckoff_spring_upthrust?.upthrust;
  const freshSdZones =
    (analytics?.sd_zones_4h?.demand_zones?.filter((z) => z.fresh).length ?? 0) +
    (analytics?.sd_zones_4h?.supply_zones?.filter((z) => z.fresh).length ?? 0);
  const smcAlertCount =
    (whaleActive ? 1 : 0) +
    (sweepActive ? 1 : 0) +
    (springActive ? 1 : 0) +
    (upthrustActive ? 1 : 0) +
    Math.min(freshSdZones, 2) +
    (analytics?.market_structure_4h?.bos_bullish ? 1 : 0) +
    (analytics?.market_structure_4h?.bos_bearish ? 1 : 0);

  const validPlan =
    analytics?.entry_plan != null && analytics.signal_direction !== "NONE";
  const macroAlertCount =
    (analytics?.liquidation_cluster?.detected ? 1 : 0) +
    ((analytics?.btc_correlation_alignment?.alignment === "conflict") ? 1 : 0) +
    ((analytics?.cvd_historical?.divergence ? 1 : 0)) +
    ((analytics?.cvd_historical?.absorption?.detected ? 1 : 0));

  return (
    <div className="px-4 py-4 bg-gradient-to-b from-black/40 to-black/10">
      <Tabs defaultValue="entry">
        <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
          <TabsList className="flex-wrap">
            <TabsTrigger value="entry">
              <Target size={11} className="mr-1" /> Entry & Aksi
              {validPlan && (
                <span className="ml-1.5 inline-block w-1.5 h-1.5 rounded-full bg-[var(--color-success)] animate-pulse" />
              )}
            </TabsTrigger>
            <TabsTrigger value="technical">
              <LineChart size={11} className="mr-1" /> Analisa Teknikal
              {patternCount > 0 && (
                <span className="ml-1 px-1 rounded text-[8px] font-bold bg-[var(--color-accent)] text-white">
                  {patternCount}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="smc">
              <Crosshair size={11} className="mr-1" /> Smart Money
              {smcAlertCount > 0 && (
                <span className="ml-1 px-1 rounded text-[8px] font-bold bg-[var(--color-warning)] text-black">
                  {smcAlertCount}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="macro">
              <Globe size={11} className="mr-1" /> Makro & Flow
              {macroAlertCount > 0 && (
                <span className="ml-1 px-1 rounded text-[8px] font-bold bg-[var(--color-danger)] text-white">
                  {macroAlertCount}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="vitals">
              <Activity size={11} className="mr-1" /> Posisi Live
            </TabsTrigger>
          </TabsList>
          <span className="text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)]">
            {p.symbol} · {p.account_name}
          </span>
        </div>

        {/* Tab 1: Entry & Aksi (DEFAULT) — paling actionable */}
        <TabsContent value="entry">
          <div className="space-y-3">
            {/* Hero row: MTF convergence + Pattern trigger */}
            {(analytics?.mtf_convergence || analytics?.primary_pattern_trigger) && (
              <div className="grid grid-cols-1 md:grid-cols-[auto_1fr] items-stretch gap-3 px-3 py-2.5 rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)]">
                {analytics?.mtf_convergence ? (
                  <MtfConvergenceRing
                    data={analytics.mtf_convergence}
                    direction={direction}
                  />
                ) : (
                  <div />
                )}
                {analytics?.primary_pattern_trigger ? (
                  <PatternTriggerBadge
                    trigger={analytics.primary_pattern_trigger}
                    direction={direction}
                  />
                ) : (
                  <div className="text-[10px] text-[var(--color-fg-faint)] flex items-center">
                    Belum ada candle pattern trigger
                  </div>
                )}
              </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-[1.3fr_1fr] gap-3">
              <EntryPlanCard
                plan={analytics?.entry_plan}
                verdict={analytics?.verdict ?? "—"}
                score={analytics?.confluence_score ?? 0}
                sizingPct={analytics?.sizing_pct_equity}
                equityUsd={equityUsd}
              />
              <div className="space-y-3">
                <ActionHints p={p} />
              </div>
            </div>

            {/* Phase 14: Signal Quality (macro adj, vol confirm, grab, sweep 15m, funding window/arb, dynamic lev) */}
            <SignalQualityCard
              adjustments={analytics?.macro_score_adjustments}
              fundingWindow={analytics?.funding_window}
              fundingArb={analytics?.funding_arb_signal}
              volumeConfirmation={analytics?.volume_confirmation_4h}
              liquidityGrab4h={analytics?.liquidity_grab_4h}
              liquidityGrab1h={analytics?.liquidity_grab_1h}
              sweep15m={analytics?.liquidity_sweep_15m}
              dynamicLevBand={analytics?.dynamic_lev_band}
              dynamicLevMult={analytics?.dynamic_lev_mult}
              direction={direction}
            />

            {/* SL + R:R */}
            <SLInvalidationCard
              sl={analytics?.sl_invalidation}
              rr={analytics?.rr_ratio}
              entryPrice={analytics?.entry_plan?.entry_price}
              direction={direction}
            />

            {/* Per-account allocation */}
            <PerAccountAllocation plan={analytics?.entry_plan} accounts={accounts} />
          </div>
        </TabsContent>

        {/* Tab 2: Analisa Teknikal — mini chart + ladder + analysis (patterns integrated) */}
        <TabsContent value="technical">
          <div className="space-y-3">
            {/* Mini chart strip (140px, cleaner) */}
            <PriceChart p={p} height={140} compact analytics={analytics} />
            <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.4fr] gap-3">
              <VerticalLadder p={p} />
              <AnalysisCard symbol={p.symbol} patterns={alignedPatterns} />
            </div>
          </div>
        </TabsContent>

        {/* Tab 3: Smart Money — institutional flow detection */}
        <TabsContent value="smc">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <SmcCard a={analytics} />
            <LiquidityZonesCard
              zones={analytics?.sd_zones_4h}
              springUpthrust={analytics?.wyckoff_spring_upthrust}
              currentPrice={analytics?.entry_plan?.current_price ?? p.price}
            />
          </div>
        </TabsContent>

        {/* Tab 4: Makro & Flow — institutional context */}
        <TabsContent value="macro">
          <div className="space-y-3">
            {/* Market regime + BTC alignment + basis */}
            <MarketRegimeCard
              regime={analytics?.market_regime}
              btcAlignment={analytics?.btc_correlation_alignment}
              basis={analytics?.spot_futures_basis}
            />

            {analytics?.liquidation_cluster?.detected && (
              <LiquidationClusterCard data={analytics.liquidation_cluster} />
            )}
            <MacroContextCard a={analytics} />

            {/* Liquidation map estimation */}
            <LiquidationZonesPhase5Card
              zones={analytics?.liquidation_zones}
              currentPrice={analytics?.entry_plan?.current_price ?? p.price}
            />

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              <VolumeProfileCard
                data={analytics?.volume_profile_4h}
                currentPrice={analytics?.entry_plan?.current_price ?? p.price}
              />
              <CumulativeDeltaCard data={analytics?.cumulative_delta} />
            </div>
            <CVDHistoryCard data={analytics?.cvd_historical} />
            <OrderBookHeatmapCard data={analytics?.orderbook_heatmap} />
          </div>
        </TabsContent>

        {/* Tab 5: Posisi Live */}
        <TabsContent value="vitals">
          <PositionVitals p={p} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
