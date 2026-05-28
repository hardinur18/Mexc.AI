/**
 * Tipe data yang di-return dari /api/snapshot.
 * Sumber truth: server.py response shape.
 */

export type Side = "LONG" | "SHORT";
export type OpenType = "cross" | "isolated";

export interface AccountMeta {
  id: string;
  name: string;
  color: string;
  category: string;
}

export interface CategoriesResponse {
  categories: string[];
  used: string[];
}

export interface AnalyticsBreakdownItem {
  name: string;
  points: number;
  value: number | string;
}

export interface SymbolAnalytics {
  symbol: string;
  // Multi-timeframe RSI
  rsi_15m: number | null;
  rsi_1h: number | null;
  rsi_4h: number | null;
  rsi_1d: number | null;
  mtf_oversold_count: number;
  mtf_overbought_count: number;
  // Bollinger Bands 4h
  bb_lower_4h: number | null;
  bb_middle_4h: number | null;
  bb_upper_4h: number | null;
  bb_position_4h: number | null;
  bb_lower_touch: boolean;
  // Distance from highs
  high_7d: number | null;
  high_30d: number | null;
  dist_from_7d_high_pct: number | null;
  dist_from_30d_high_pct: number | null;
  // Capitulation
  volume_capitulation: boolean;
  volume_24h_usdt: number | null;
  // OI & funding
  oi_delta_5m_pct: number | null;
  funding_rate_pct: number | null;
  funding_trend_1h?: string | null;
  // Orderbook
  ob_imbalance_pct?: number | null;
  ob_bias?: string | null;
  // EMA trend
  ema_20_4h?: number | null;
  ema_50_4h?: number | null;
  trend_4h?: "uptrend" | "downtrend" | "sideways" | null;
  price_vs_ema50_pct?: number | null;
  // Pattern detection
  rsi_bullish_divergence_4h?: boolean;
  rsi_bearish_divergence_4h?: boolean;
  three_bar_reversal_1h?: boolean;
  mtf_sequence_bonus?: number;
  // VWAP
  vwap_4h?: number | null;
  vwap_dist_pct?: number | null;
  // Hard gates
  gate_volume?: boolean;
  gate_not_overbought?: boolean;
  gate_discounted?: boolean;
  all_gates_pass?: boolean;
  // Position sizing recommendation
  sizing_pct_equity?: number;
  // Composite
  confluence_score: number;
  confluence_breakdown: AnalyticsBreakdownItem[];
  verdict: string;
  bias: "bullish" | "bearish" | "neutral";
  // Multi-direction signal
  signal_direction?: "LONG" | "SHORT" | "NONE";
  score_long?: number;
  score_short?: number;
  candle_pattern_summary?: { tf: string; pattern: string }[];
  low_7d?: number | null;
  dist_from_7d_low_pct?: number | null;
  entry_plan?: EntryPlan | null;
  // Smart Money Concepts
  liquidity_sweep_4h?: SweepData | null;
  liquidity_sweep_1h?: SweepData | null;
  order_block_4h?: OrderBlockData | null;
  fair_value_gap_4h?: FvgData | null;
  market_structure_4h?: MarketStructureData | null;
  wyckoff_phase?: WyckoffData | null;
  whale_accumulation?: WhaleData | null;
  // Phase 1+2 enrichments
  candle_patterns_rich?: Record<string, RichCandlePattern[]>;
  primary_pattern_trigger?: PrimaryPatternTrigger | null;
  wyckoff_spring_upthrust?: WyckoffSpringUpthrust | null;
  sd_zones_4h?: SDZonesData | null;
  volume_profile_4h?: VolumeProfileData | null;
  liquidation_cluster?: LiquidationCluster | null;
  mtf_convergence?: MTFConvergence | null;
  oi_history_api?: OiHistoryPoint[];
  long_short_ratio?: LongShortRatioSample | null;
  long_short_ratio_history?: LongShortRatioSample[];
  funding_history?: FundingHistoryPoint[];
  funding_rate_7d_avg?: number | null;
  cumulative_delta?: CumulativeDelta | null;
  orderbook_heatmap?: OrderbookHeatmap | null;
  // Phase 5 enrichments
  sl_invalidation?: SlInvalidation | null;
  rr_ratio?: RRRatio | null;
  tier_anchor_sources?: TierAnchorSources | null;
  atr_4h?: number | null;
  atr_pct_4h?: number | null;
  anchored_vwap_swing_low?: number | null;
  anchored_vwap_swing_high?: number | null;
  market_regime?: MarketRegime | null;
  spot_futures_basis?: SpotFuturesBasis | null;
  liquidation_zones?: LiquidationZones | null;
  cvd_historical?: CVDHistorical | null;
  btc_correlation_alignment?: BtcAlignment | null;
  // Phase 7+8+9 additions
  liquidity_grab_4h?: LiquidityGrab | null;
  liquidity_grab_1h?: LiquidityGrab | null;
  liquidity_sweep_15m?: SweepData | null;
  volume_confirmation_4h?: VolumeConfirmation | null;
  volume_confirmation_1h?: VolumeConfirmation | null;
  funding_window?: FundingWindow | null;
  macro_score_adjustments?: MacroScoreAdjustment[];
  funding_arb_signal?: FundingArbSignal | null;
  dynamic_lev_band?: string | null;
  dynamic_lev_mult?: number | null;
}

export interface SweepData {
  bullish_sweep: boolean;
  bearish_sweep: boolean;
  sweep_strength: number;
  prior_high?: number;
  prior_low?: number;
}
export interface OrderBlockData {
  bullish_ob_zone?: { high: number; low: number; bar_index_from_now: number } | null;
  bearish_ob_zone?: { high: number; low: number; bar_index_from_now: number } | null;
}
export interface FvgData {
  bullish_fvg?: { high: number; low: number; bar_index_from_now: number } | null;
  bearish_fvg?: { high: number; low: number; bar_index_from_now: number } | null;
}
export interface MarketStructureData {
  bos_bullish: boolean;
  bos_bearish: boolean;
  structure: string | null;
  last_swing_high?: number | null;
  last_swing_low?: number | null;
}
export interface WyckoffData {
  phase: string;
  confidence: number;
  price_slope_pct?: number;
  volatility_pct?: number;
  vol_ratio?: number;
  oi_trend?: string;
}
export interface WhaleData {
  detected: boolean;
  intensity: number;
  oi_change_pct?: number;
  price_change_pct?: number;
}

// ─── Phase 1+2 enrichments ───
export interface RichCandlePattern {
  pattern: string;
  bullish: boolean | null;
  bar_index_from_now: number;
  open: number;
  high: number;
  low: number;
  close: number;
  trigger_price: number;
}

export interface PrimaryPatternTrigger {
  tf: string;
  pattern: string;
  bullish: boolean | null;
  bar_index_from_now: number;
  close: number;
  high: number;
  low: number;
  trigger_price: number;
  confirmed?: boolean;
  confirmation_close?: number | null;
}

export interface WyckoffSpringUpthrust {
  spring: boolean;
  upthrust: boolean;
  spring_bar_index_from_now?: number | null;
  upthrust_bar_index_from_now?: number | null;
  spring_low?: number | null;
  upthrust_high?: number | null;
  broken_support?: number | null;
  broken_resistance?: number | null;
}

export interface SDZone {
  high: number;
  low: number;
  mid: number;
  bar_index_from_now: number;
  tested: boolean;
  fresh: boolean;
  impulse_strength: number;
}

export interface SDZonesData {
  demand_zones: SDZone[];
  supply_zones: SDZone[];
}

export interface VolumeProfileBin {
  price: number;
  volume: number;
  ratio: number;
}

export interface VolumeProfileData {
  poc: number | null;
  vah: number | null;
  val: number | null;
  range_high: number;
  range_low: number;
  histogram: VolumeProfileBin[];
  hvn: { price: number; volume_ratio: number }[];
  lvn: { price: number; volume_ratio: number }[];
}

export interface LiquidationCluster {
  detected: boolean;
  side: "long_squeeze" | "short_squeeze" | null;
  oi_surge_pct: number | null;
  funding_extreme: "long_crowded" | "short_crowded" | null;
  compression: boolean;
  range_pct: number | null;
}

export interface MTFConvergence {
  score: number;
  factors: string[];
  tf_breakdown: {
    trend_4h: string | null;
    bos_4h_bullish: boolean;
    bos_4h_bearish: boolean;
    sweep_4h_bullish: boolean;
    sweep_4h_bearish: boolean;
    candle_4h_net: number;
    candle_1h_net: number;
    candle_15m_net: number;
  };
}

export interface CumulativeDelta {
  buy_vol: number;
  sell_vol: number;
  delta: number;
  buy_pct: number;
  bias: "buy" | "sell" | "neutral";
}

export interface OrderbookHeatmap {
  best_bid: number;
  best_ask: number;
  spread_pct: number;
  bid_walls: { price: number; volume: number }[];
  ask_walls: { price: number; volume: number }[];
  bid_total_vol: number;
  ask_total_vol: number;
  bids_top: { price: number; volume: number }[];
  asks_top: { price: number; volume: number }[];
}

export interface LongShortRatioSample {
  /** MEXC returns raw object; we keep loose typing */
  timestamp?: number;
  longShortRatio?: number;
  longRatio?: number;
  shortRatio?: number;
  [k: string]: number | string | undefined;
}

export interface OiHistoryPoint {
  timestamp?: number;
  holdVol?: number;
  [k: string]: number | string | undefined;
}

export interface FundingHistoryPoint {
  symbol?: string;
  fundingRate?: number;
  settleTime?: number;
  [k: string]: number | string | undefined;
}

// ─── Phase 5 enrichments ───
export interface SlInvalidation {
  price: number | null;
  reason: string;
  distance_pct: number | null;
}

export interface RRRatio {
  tp1: number | null;
  tp2: number | null;
  tp3: number | null;
  risk_pct: number | null;
}

export interface TierAnchorSources {
  utama1: string | null;
  utama2: string | null;
  booster: string | null;
}

export interface MarketRegime {
  regime: string;
  trend_strength: number;
  slope_pct_per_bar: number;
  volatility: string;
  atr_pct: number | null;
}

export interface SpotFuturesBasis {
  spot_price: number;
  futures_price: number;
  basis_pct: number;
  bias: string;
}

export interface LiquidationZoneCluster {
  price: number;
  lev: number;
  est_value_usdt: number | null;
  pct_from_current: number;
}

export interface LiquidationZones {
  long_clusters: LiquidationZoneCluster[];
  short_clusters: LiquidationZoneCluster[];
  long_share_estimate: number;
  dominant_side: string;
}

export interface CVDBar {
  ts: number;
  price_close: number;
  delta: number;
  cvd: number;
  buy_vol: number;
  sell_vol: number;
  trades: number;
}

export interface CVDHistorical {
  history: CVDBar[];
  current_cvd: number;
  divergence: { type: string; detail: string } | null;
  absorption: { detected: boolean; side: string; delta: number; range_pct: number; detail: string } | null;
}

export interface BtcAlignment {
  correlation_30bar: number | null;
  btc_change_30bar_pct: number;
  btc_direction: string;
  alignment: string;
  penalty_pct: number;
}

// Phase 7+8+9 additions
export interface MacroScoreAdjustment {
  source: string;
  name: string;
  value: string;
  score_delta: number;
  applies_to: string;
}

export interface FundingWindow {
  near_settlement: boolean;
  minutes_to_settle: number | null;
  settlement_warning: string | null;
}

export interface FundingArbSignal {
  type: "short_perp_long_spot" | "long_perp_short_spot";
  funding_rate_pct: number;
  annualized_pct: number;
  description: string;
}

export interface VolumeConfirmation {
  confirmed: boolean;
  ratio: number | null;
  recent_avg: number | null;
  baseline_avg: number | null;
}

export interface LiquidityGrab {
  bullish_grab: boolean;
  bearish_grab: boolean;
  bar_index_from_now: number | null;
  grab_low: number | null;
  grab_high: number | null;
  broken_low: number | null;
  broken_high: number | null;
  rejection_pct: number | null;
}

export interface PatternWinrate {
  total_closed: number;
  by_direction?: Record<string, { wins: number; losses: number; total_pnl: number; win_rate: number }>;
  by_score_band?: Record<string, { wins: number; losses: number; total_pnl: number; trades: number; win_rate: number }>;
  by_pattern?: Record<string, { wins: number; losses: number; trades: number; win_rate: number; total_pnl: number }>;
  note?: string;
}

export interface MacroContext {
  ts: number;
  btc_dominance: {
    btc_dominance_pct: number | null;
    eth_btc_ratio: number | null;
    btc_change_24h_pct: number;
    top10_share_pct: number | null;
  } | null;
  btc_regime: MarketRegime;
  btc_trend_4h: string | null;
  btc_rsi_4h: number | null;
  alt_season: string | null;
  market_mood: string;
}

export interface PortfolioHeat {
  ts: number;
  total_equity: number;
  heat: {
    total_heat_pct: number;
    open_positions: number;
    max_single_heat_pct: number;
    warning_level: "ok" | "moderate" | "high" | "critical";
  };
  per_account: Array<{
    account_id: string;
    account_name: string;
    total_heat_pct: number;
    open_positions: number;
    max_single_heat_pct: number;
    warning_level: string;
  }>;
  size_recommendation?: {
    multiplier: number;
    reason: string;
  };
  correlation?: {
    raw_position_count: number;
    effective_position_count: number;
    clusters: Array<{ symbols: string[]; size: number }>;
  };
}

export interface CircuitBreaker {
  ts: number;
  daily_realised: number;
  daily_pct_equity: number;
  threshold_pct: number;
  tripped: boolean;
  recommendation: string;
  cooldown_active?: boolean;
  cooldown_reason?: string | null;
  cooldown_until_ms?: number | null;
  minutes_until_cooldown_ends?: number | null;
}

// ─── Phase 6 enrichments ───
export interface CascadeTier {
  role: string;
  name: string;
  target_price: number;
  size_usdt: number;
  lev: number;
  filled: boolean;
  fill_price: number | null;
  fill_ts_ms: number | null;
  order_id: string | null;
}

export interface CascadeTp {
  tp_num: number;
  target_price: number;
  close_pct: number;
  filled: boolean;
  fill_ts_ms: number | null;
  pnl_usdt: number | null;
  order_id: string | null;
}

export interface Cascade {
  id: string;
  symbol: string;
  direction: "LONG" | "SHORT";
  score: number;
  started_ts_ms: number;
  state: string;
  mode: "paper" | "live";
  account_id: string;
  account_name: string;
  tiers: CascadeTier[];
  tps: CascadeTp[];
  sl_price: number;
  sl_original: number;
  sl_breakeven_armed: boolean;
  sl_trail_armed: boolean;
  sl_reason: string;
  weighted_avg_entry: number | null;
  total_filled_usdt: number;
  realized_pnl_usdt: number;
  last_seen_price: number | null;
  closed_ts_ms: number | null;
  outcome: string | null;
  notes: string[];
  last_event_ts_ms: number;
}

export interface CascadeActiveResponse {
  count: number;
  live_enabled: boolean;
  items: Cascade[];
}

export interface PerformanceMetrics {
  total_trades: number;
  win_rate: number | null;
  expectancy_usdt: number | null;
  total_pnl: number;
  max_drawdown_pct: number | null;
  sharpe: number | null;
  sortino: number | null;
  calmar: number | null;
  avg_win_usdt: number;
  avg_loss_usdt: number;
  best_trade: number | null;
  worst_trade: number | null;
  equity_curve?: number[];
  by_direction: Record<
    string,
    { wins: number; losses: number; pnl: number; win_rate: number }
  >;
}

export interface FearGreed {
  current: number | null;
  classification?: string;
  timestamp?: number;
  history?: { value: number; ts: number; class?: string }[];
}

export interface CoinGeckoGlobal {
  total_market_cap_usd: number | null;
  total_volume_24h_usd: number | null;
  btc_dominance_pct: number | null;
  eth_dominance_pct: number | null;
  active_cryptocurrencies: number | null;
  market_cap_change_24h_usd_pct: number | null;
  updated_at: number | null;
}

export interface DeribitOptions {
  currency: string;
  put_call_oi_ratio: number | null;
  put_call_vol_ratio: number | null;
  total_call_oi: number;
  total_put_oi: number;
  max_pain_strike: number | null;
  max_pain_oi: number;
  top_strikes_by_oi: { strike: number; total_oi: number; call_oi: number; put_oi: number }[];
  interpretation: "bullish_sentiment" | "bearish_sentiment" | "neutral";
}

export interface BinanceFunding {
  funding_rate: number | null;
  next_funding_ms: number | null;
  mark_price: number | null;
  index_price: number | null;
  open_interest: number | null;
  long_short_ratio: number | null;
  long_account_pct: number | null;
  short_account_pct: number | null;
  lsr_history?: { ts: number; ratio: number }[];
}

export interface CryptoPanicItem {
  title: string;
  url: string;
  published_at: string;
  source?: string;
  currencies: string[];
  votes?: Record<string, number>;
}

export interface CryptoPanicNews {
  count: number;
  items: CryptoPanicItem[];
}

export interface BacktestResult {
  symbol: string;
  interval: string;
  bars_scanned: number;
  trades: Array<{
    dir: string;
    entry: number;
    exit?: number;
    sl: number;
    tp: number;
    pnl_pct?: number;
    outcome?: string;
    ts?: number;
  }>;
  metrics: {
    total_trades: number;
    win_rate_pct: number;
    total_return_pct: number;
    expectancy_pct: number;
    avg_win_pct: number;
    avg_loss_pct: number;
    max_drawdown_pct: number;
    final_equity: number;
  };
  equity_curve: number[];
}

export interface EntryTier {
  name: string;
  role: string;
  price: number | null;
  size_pct_equity: number;
  lev: number;
  trigger_label: string;
  trigger_at?: string | null;
  rationale: string;
}

export interface CascadeProjection {
  weighted_avg_price: number | null;
  total_size_pct_equity: number;
  worst_case_price: number | null;
  worst_case_loss_pct_equity: number;
  explanation: string;
}

export interface TpLevel {
  tp: number;
  price: number | null;
  pct_price: number;
  pct_margin_100x: number;
  close_pct: number;
  reason: string;
}

export interface EntryPlan {
  direction: "LONG" | "SHORT";
  current_price: number | null;
  entry_price: number | null;
  entry_zone_label: string;
  reasoning: string[];
  stop_plus_hint: string | null;
  tiers?: EntryTier[];
  tp_ladder?: TpLevel[];
  cascade_projection?: CascadeProjection;
  // Phase 5
  sl_invalidation?: SlInvalidation | null;
  rr_ratio?: RRRatio | null;
  tier_anchor_sources?: TierAnchorSources | null;
  // legacy
  tp_ladder_hint?: { pct_margin: number; close_pct: number; reason: string }[];
}

export interface Signal {
  symbol: string;
  confluence_score: number;
  breakdown: AnalyticsBreakdownItem[];
  rsi_15m?: number | null;
  rsi_1h?: number | null;
  rsi_4h?: number | null;
  rsi_1d?: number | null;
  mtf_oversold_count?: number;
  bb_lower_touch?: boolean;
  dist_from_7d_high_pct?: number | null;
  volume_capitulation?: boolean;
  oi_delta_5m_pct?: number | null;
  funding_rate_pct?: number | null;
  volume_24h_usdt?: number | null;
  verdict?: string;
  trend_4h?: string | null;
  rsi_bullish_divergence_4h?: boolean;
  rsi_bearish_divergence_4h?: boolean;
  three_bar_reversal_1h?: boolean;
  // NEW for direction + entry plan
  direction?: "LONG" | "SHORT" | "NONE";
  score_long?: number;
  score_short?: number;
  mtf_overbought_count?: number;
  dist_from_7d_low_pct?: number | null;
  candle_pattern_summary?: { tf: string; pattern: string }[];
  entry_plan?: EntryPlan | null;
  sizing_pct_equity?: number;
  // Phase 1+2 enrichments
  primary_pattern_trigger?: PrimaryPatternTrigger | null;
  mtf_convergence?: MTFConvergence | null;
  wyckoff_spring_upthrust?: WyckoffSpringUpthrust | null;
  wyckoff_phase?: WyckoffData | null;
  liquidity_sweep_4h?: SweepData | null;
  liquidation_cluster?: LiquidationCluster | null;
  sd_zones_4h?: SDZonesData | null;
  volume_profile_4h?: VolumeProfileData | null;
  long_short_ratio?: LongShortRatioSample | null;
  funding_rate_7d_avg?: number | null;
  cumulative_delta?: CumulativeDelta | null;
  orderbook_heatmap?: OrderbookHeatmap | null;
  // Phase 5
  sl_invalidation?: SlInvalidation | null;
  rr_ratio?: RRRatio | null;
  tier_anchor_sources?: TierAnchorSources | null;
  atr_4h?: number | null;
  atr_pct_4h?: number | null;
  anchored_vwap_swing_low?: number | null;
  anchored_vwap_swing_high?: number | null;
  market_regime?: MarketRegime | null;
  spot_futures_basis?: SpotFuturesBasis | null;
  liquidation_zones?: LiquidationZones | null;
  cvd_historical?: CVDHistorical | null;
  btc_correlation_alignment?: BtcAlignment | null;
  // Phase 7+8+9
  liquidity_grab_4h?: LiquidityGrab | null;
  liquidity_grab_1h?: LiquidityGrab | null;
  liquidity_sweep_15m?: SweepData | null;
  volume_confirmation_4h?: VolumeConfirmation | null;
  funding_window?: FundingWindow | null;
  macro_score_adjustments?: MacroScoreAdjustment[];
  funding_arb_signal?: FundingArbSignal | null;
  dynamic_lev_band?: string | null;
  dynamic_lev_mult?: number | null;
  sd_zones_1d?: SDZonesData | null;
  sd_zones_1h?: SDZonesData | null;
  volume_profile_1d?: VolumeProfileData | null;
  volume_profile_1h?: VolumeProfileData | null;
}

export interface SignalsResponse {
  ts: number;
  latency_ms: number;
  min_score_threshold: number;
  scanned_count: number;
  signal_count: number;
  signals: Signal[];
}

export interface ClosedPosition {
  ts: number;
  account_id: string;
  account_name: string;
  symbol: string;
  side: string;
  coin: string;
  icon_url?: string | null;
  lev: number;
  entry: number;
  exit_estimate: number;
  pnl_final: number;
  pnl_unrealized_last: number;
  pnl_realised_last: number;
  margin_used: number;
}

export interface ClosedPositionsResponse {
  count: number;
  items: ClosedPosition[];
}

export interface AccountSummary extends AccountMeta {
  equity: number;
  available: number;
  unrealized: number;
  position_margin: number;
  position_count: number;
  error?: string | null;
}

export interface Account {
  equity: number;
  available: number;
  cash: number;
  position_margin: number;
  unrealized: number;
  frozen: number;
}

export interface Totals {
  pnl_unrealized: number;
  pnl_realised: number;
  pnl_net: number;
  margin: number;
  notional: number;
  pos_count: number;
}

export interface SRLevel {
  /** Label semantic: PP, R1, R2, S1, S2, etc */
  label: string;
  price: number;
  /** "support" | "resistance" | "pivot" */
  kind: "support" | "resistance" | "pivot";
  /** Signed distance from mark to this level, % */
  distance_pct: number;
}

export interface ActionHint {
  level: "info" | "warning" | "danger" | "success";
  title: string;
  detail?: string;
}

export interface Position {
  no: number;
  coin: string;
  icon_url?: string | null;
  symbol: string;
  side: Side;
  open_type: OpenType;
  lev: number;
  margin: number;
  notional: number;
  price: number;
  entry: number;
  price_delta_pct: number;
  pnl_usdt: number;
  pnl_unrealized: number;
  pnl_realised: number;
  pnl_pct_real: number;
  pnl_pct_lev: number;
  margin_ratio: number;
  liq_price: number | null;
  buffer_pct: number | null;
  tp_price: number | null;
  tp_price_farthest: number | null;
  tp_count: number;
  tp_dist_pct: number | null;
  tp_all: number[];
  sl_price: number | null;
  sl_count: number;
  sl_dist_pct: number | null;
  sl_all: number[];
  position_id: number;
  update_time: number;
  /** Optional, populated when backend computes pivots. */
  sr_levels?: SRLevel[];
  /** Optional, populated when backend computes hints. */
  hints?: ActionHint[];
  /** Funding rate snapshot. */
  funding?: {
    rate: number;
    next_settle_ms: number;
    collect_cycle_hours: number;
    max_rate: number;
    min_rate: number;
  };
  /** Sparkline 24h: array of [time_ms, close]. */
  sparkline?: number[][];
  /** Position opened timestamp (ms). */
  create_time?: number;
  /** Multi-account tagging. */
  account_id: string;
  account_name: string;
  account_color: string;
  /** Cross-signal enrichment — analysis for this position's symbol. */
  signal_score?: number | null;
  signal_verdict?: string | null;
  signal_oversold_n?: number | null;
  signal_overbought_n?: number | null;
  signal_bb_lower?: boolean | null;
  signal_dist_7d_high?: number | null;
}

export interface Snapshot {
  ts: number;
  latency_ms: number;
  selected_account_ids: string[];
  accounts: AccountSummary[];
  account: Account;
  totals: Totals;
  positions: Position[];
}

export interface AccountsResponse {
  accounts: AccountMeta[];
}
