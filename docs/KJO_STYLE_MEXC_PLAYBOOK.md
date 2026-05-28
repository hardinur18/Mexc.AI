# KJO-Style MEXC Trading Playbook

Status: practical SOP draft from public evidence, 2026-05-14

This playbook converts public KJO-related evidence into bot-friendly operating
rules for the local MEXC futures engine. It is not private alpha, not a leaked
course, and not a guarantee of returns. Every rule here must be tested with
paper trading, realistic fees, slippage, and out-of-sample validation before
live use.

## Evidence Basis

Public evidence already captured in `KJO_PUBLIC_STRATEGY_RESEARCH.md` points to
these repeatable themes:

- Top-down market reading before any pair entry.
- BTC structure, USDT dominance, BTC dominance, TOTAL3, ETH/BTC, and macro/on-chain
  context are used as regime filters.
- Capital allocation changes with regime. Cash is a valid position.
- Futures are tactical. Leverage is secondary to stop distance, risk, and margin
  control.
- Entries are based on confluence: support/resistance, demand/supply,
  breakout/retest, trendline, Fibonacci zone, and candle close confirmation.
- Management uses SL+, partial profit, and trailing rather than hoping a winner
  keeps running without protection.

Public-source limitations:

- Instagram stories and private/expired group content are not accessible unless
  the user provides screenshots or links.
- Public images and chart previews are sometimes blocked or incomplete.
- KJO's exact internal framework is proprietary unless he publicly discloses it.
- This document is a reconstruction from public patterns.

## Core Philosophy

The bot should not ask, "Which coin pumps next?"

The bot should ask in order:

1. Is the broad crypto regime worth risking capital in?
2. If yes, should exposure be cash, spot-like watchlist, or futures?
3. Which pairs have liquidity, clean structure, and relative strength?
4. Is price at a high-quality location with clear invalidation?
5. Can the trade be sized so the stop loss is survivable?
6. Can the winner be protected quickly with SL+ and trailing?
7. Does the strategy version remain profitable after fees, slippage, and bad
   regimes?

## End-to-End SOP

### 1. Daily Preparation

Manual trader checklist:

- Check BTC daily and 4H structure.
- Mark major BTC support, resistance, demand, supply, neckline, and trendline.
- Check whether BTC is breaking out, ranging, correcting, reclaiming, or losing
  support.
- Check USDT.D direction when data is available.
- Check BTC.D direction when data is available.
- Check TOTAL3 direction when data is available.
- Check ETH/BTC or ETH relative strength as a proxy for alt appetite.
- Check known event risk: FOMC, CPI, major ETF/news/liquidation events.
- Decide mode before scanning pairs: `risk_on`, `neutral`, `defensive`, or
  `cash`.

Bot preparation pseudo-rule:

```text
load_market_universe()
load_account_equity()
load_open_positions()
load_kill_switch()
load_recent_candles(BTC_USDT, 1h, 4h, 1d)
load_pair_candles(all_mexc_pairs, 15m, 1h, 4h)
load_microstructure(all_mexc_pairs): spread, depth, funding, fair/index
load_optional_external_context(): USDT.D, BTC.D, TOTAL3, ETH/BTC
```

Hard preparation gates:

```text
if kill_switch_active:
  block_new_trades

if live_trading_enabled is false:
  paper_only

if market_data_stale:
  block_new_trades

if account_equity_unknown:
  block_new_trades
```

### 2. Regime Scan

Regime is the first gate. A strong pair setup is ignored if the market regime
is hostile.

Regime scoring:

```text
score = 0

if BTC 4H and daily structure are bullish:
  score += 2
if BTC holds or reclaims major support after correction:
  score += 1
if USDT.D is falling:
  score += 1
if BTC.D is falling while BTC is stable/up:
  score += 1
if TOTAL3 breaks out or successfully retests:
  score += 1
if ETH/BTC or ETH relative strength is rising:
  score += 1

if BTC loses major support:
  score -= 2
if USDT.D is rising:
  score -= 1
if BTC.D rises hard while alts weaken:
  score -= 1
if funding is overheated against the intended direction:
  score -= 1
if spreads/depth are poor across the market:
  score -= 1
```

Regime classification:

```text
if score >= 4:
  regime = risk_on
elif score >= 2:
  regime = neutral
elif score >= 0:
  regime = defensive
else:
  regime = cash
```

Action by regime:

```text
risk_on:
  allow selective futures
  allow long bias if pair confirms
  allow up to 3 open futures positions

neutral:
  allow only A-grade setups
  reduce risk per trade
  prefer BTC/ETH/large liquid pairs
  allow max 1 open futures position

defensive:
  no new futures by default
  optional micro futures only in paper mode
  spot-watchlist only

cash:
  block all new futures
  close or tighten weak open positions
  protect winners with SL+ or trailing
```

Assumptions to test:

- `score >= 4` should materially improve expectancy versus taking all signals.
- External dominance/TOTAL3 data may be unavailable locally. Until integrated,
  use proxy scores from BTC trend, ETH relative strength, and pair breadth.

### 3. Pair Selection

The pair must be tradable before it can be interesting.

Liquidity gate:

```text
reject if spread_bps > max_spread_bps
reject if top10_depth_usdt < min_depth_usdt
reject if 24h_volume_usdt < min_volume_usdt
reject if funding_abs > max_abs_funding
reject if candle_gap_count > max_gap_count
reject if price_precision or contract_size unknown
```

Strength gate for longs:

```text
pair_strength = pair_return_4h - BTC_return_4h
trend_strength = EMA20_slope_1h + EMA50_slope_4h
breakout_quality = close_above_recent_range and volume_or_range_expansion

long_pair_score =
  +1 if pair_strength > 0
  +1 if pair_strength_rank in top 20%
  +1 if EMA trend is up on 1h and 4h
  +1 if price is above key reclaim level
  +1 if pullback holds fib/support zone
```

Strength gate for shorts:

```text
pair_weakness = BTC_return_4h - pair_return_4h

short_pair_score =
  +1 if pair_weakness > 0
  +1 if pair_weakness_rank in top 20%
  +1 if EMA trend is down on 1h and 4h
  +1 if price loses key support
  +1 if retest fails at resistance/supply
```

Pair selection rule:

```text
if regime in [cash, defensive]:
  selected_pairs = []

if regime == neutral:
  selected_pairs = top liquid pairs with pair_score >= 4

if regime == risk_on:
  selected_pairs = top liquid pairs with pair_score >= 3
```

Assumptions to test:

- Relative strength should be computed per timeframe. A pair can be strong on
  15m but weak on 4H. The bot should prefer 1H/4H alignment for futures.
- Low-liquidity MEXC pairs can show huge moves, but slippage can erase edge.

### 4. Setup Location

KJO-style entries appear location-based, not random indicator crosses.

Long setup location:

```text
valid_long_location if any:
  price retests breakout level and holds
  price pulls back into 0.5 to 0.618 fib zone in uptrend
  price taps demand/support and closes back above it
  price reclaims lost support with strong close
  price breaks range high then retests without losing structure
```

Short setup location:

```text
valid_short_location if any:
  price retests breakdown level and rejects
  price pulls back into 0.5 to 0.618 fib zone in downtrend
  price taps supply/resistance and closes back below it
  price loses support and fails reclaim
  price breaks range low then retests without reclaim
```

Fibonacci rule:

```text
long fib:
  swing_low = clean HTF impulse low
  swing_high = clean HTF impulse high
  preferred_entry_zone = 0.5 to 0.618 retracement
  deep_entry_zone = 0.65 to 0.786 retracement, smaller size only
  invalidation = below swing_low or below structure that made the setup valid

short fib:
  swing_high = clean HTF impulse high
  swing_low = clean HTF impulse low
  preferred_entry_zone = 0.5 to 0.618 retracement
  deep_entry_zone = 0.65 to 0.786 retracement, smaller size only
  invalidation = above swing_high or above structure that made the setup valid
```

Setup score:

```text
setup_score = 0

if valid_location:
  setup_score += 2
if close_confirmation:
  setup_score += 1
if RR_to_TP1 >= 2.0:
  setup_score += 1
if spread/depth/funding pass:
  setup_score += 1
if pair relative strength agrees with side:
  setup_score += 1
if BTC/regime agrees with side:
  setup_score += 1
if entry is chasing after extended candle:
  setup_score -= 2
if stop must be too wide for allowed risk:
  setup_score -= 2
```

Entry rule:

```text
enter only if:
  regime_score >= 2
  setup_score >= 5
  RR_to_TP1 >= 2.0
  candle_close_confirmation is true
  stop_loss is structural
  liquidation is safely beyond stop
```

Paper-only aggressive rule:

```text
enter only if:
  regime_score >= 4
  setup_score >= 6
  RR_to_TP1 >= 2.5
  risk is split across max 3 positions
  total_open_risk <= 5%
```

Assumptions to test:

- Public evidence references 0.618 and confluence, but exact Fib anchoring is an
  inference. Swing selection must be tested.
- Candle close confirmation may reduce false entries but can reduce reward. Test
  15m, 1H, and 4H confirmation separately.

### 5. Entry Execution

Do not market-buy any signal blindly.

Limit-first rule:

```text
if spread_bps <= tight_spread_gate:
  use post-only or limit order near bid/ask
else:
  wait

if order not filled within max_wait_seconds:
  cancel

if price moves away and RR drops below gate:
  cancel
```

No-chase rule:

```text
reject long if current_price > planned_entry * (1 + max_chase_bps/10000)
reject short if current_price < planned_entry * (1 - max_chase_bps/10000)
```

Breakout exception:

```text
allow breakout entry only if:
  regime == risk_on
  breakout candle closes above/below level
  volume/range expands
  stop can sit behind breakout structure
  RR_to_TP1 still >= 2.0
```

### 6. Sizing

Sizing is based on invalidation, not confidence hype.

Formula:

```text
risk_usdt = equity_usdt * risk_pct
stop_distance_pct = abs(entry_price - stop_price) / entry_price
notional_usdt = risk_usdt / stop_distance_pct
contracts = notional_usdt / (entry_price * contract_size)
margin_usdt = notional_usdt / leverage
margin_ratio = margin_usdt / equity_usdt
```

Risk by regime:

```text
cash:
  risk_pct = 0

defensive:
  risk_pct = 0
  optional paper micro risk <= 0.25%

neutral:
  risk_pct <= 0.50%
  total_open_risk <= 1.00%

risk_on:
  risk_pct <= 1.00%
  total_open_risk <= 3.00%

paper_aggressive:
  risk_pct <= 1.67% per position
  max_positions = 3
  total_open_risk <= 5.00%
```

Rejection rules:

```text
reject if stop_distance_pct <= min_stop_distance_pct
reject if stop_distance_pct >= max_stop_distance_pct
reject if contracts < exchange_min_contracts
reject if notional_usdt > max_notional_usdt
reject if margin_ratio > max_margin_ratio
reject if total_open_risk_after_entry > regime_total_risk_cap
```

Assumptions to test:

- Public evidence includes high-risk examples, but the bot should default to
  conservative risk until positive out-of-sample expectancy is proven.

### 7. Leverage

Leverage is chosen after notional is calculated.

Leverage rule:

```text
notional_usdt = risk_usdt / stop_distance_pct

choose lowest leverage such that:
  margin_usdt = notional_usdt / leverage
  margin_ratio <= max_margin_ratio
  liquidation_price is beyond stop_price by liquidation_buffer_pct
  leverage <= max_allowed_leverage
```

Suggested defaults:

```text
neutral:
  max_leverage = 3x to 5x
  max_margin_ratio = 1%

risk_on:
  max_leverage = 5x to 10x
  max_margin_ratio = 2%

paper_aggressive:
  max_leverage can be higher only in paper
  liquidation buffer must still pass
```

Hard rule:

```text
if liquidation_price is closer than stop_price:
  reject

if liquidation_buffer_pct < configured_min:
  reject
```

Interpretation:

- 100x leverage does not make the setup better.
- High leverage only reduces margin requirement and moves liquidation closer.
- The bot should never increase risk just because leverage is available.

### 8. Stop Loss

Every futures entry needs a stop before entry.

Stop placement:

```text
long stop candidates:
  below retest low
  below demand zone
  below fib zone plus ATR buffer
  below swing low that defines the setup

short stop candidates:
  above retest high
  above supply zone
  above fib zone plus ATR buffer
  above swing high that defines the setup
```

Stop buffer:

```text
atr_buffer = ATR(14) * atr_stop_multiplier

long_stop = structural_level - atr_buffer
short_stop = structural_level + atr_buffer
```

Stop validation:

```text
reject if stop is only arbitrary percent without structure
reject if stop is inside normal spread/noise
reject if RR_to_TP1 < 2.0 after stop placement
reject if liquidation is too close to stop
```

### 9. Take Profit

Targets must be known before entry.

Long TP candidates:

```text
TP1 = nearest resistance/supply or 1R to 1.5R
TP2 = next supply/resistance or 2R to 3R
TP3 = fib extension 1.272 or 1.618 if trend continues
```

Short TP candidates:

```text
TP1 = nearest support/demand or 1R to 1.5R
TP2 = next demand/support or 2R to 3R
TP3 = fib extension 1.272 or 1.618 if trend continues
```

Bot TP rule:

```text
at TP1:
  close 25% to 40%
  move stop to SL+

at TP2:
  close another 25% to 40%
  trail remaining position

at TP3 or regime deterioration:
  close runner
```

RR gate:

```text
reject if TP1_R < 1.5
prefer if TP1_R >= 2.0
promote if TP2_R >= 3.0 and regime is risk_on
```

### 10. SL+ Management

SL+ is the center of the KJO-style risk protection.

Definition:

```text
SL+ = stop moved to breakeven plus fees plus small profit buffer
```

SL+ formula:

```text
fee_buffer_pct = expected_round_trip_fee_pct + spread_buffer_pct

long_sl_plus = entry_price * (1 + fee_buffer_pct + min_profit_buffer_pct)
short_sl_plus = entry_price * (1 - fee_buffer_pct - min_profit_buffer_pct)
```

Activation rules:

```text
if unrealized_R >= 1.0:
  move stop to SL+

if price closes beyond TP1 level:
  partial_close 25% to 40%
  move stop to SL+

if regime worsens while trade is positive:
  move stop to SL+ immediately
```

Do not move to SL+ too early:

```text
if unrealized_R < 0.7 and price has not confirmed:
  keep original stop
```

Assumptions to test:

- Moving to SL+ at +1R may improve drawdown but may reduce large winners.
- Test SL+ activation at +0.8R, +1.0R, +1.2R, and after TP1 candle close.

### 11. Trailing

Trailing is for the remaining runner after partial profit.

Trailing options:

```text
ATR trail:
  long_stop = max(current_stop, close - ATR(14) * atr_trail_multiplier)
  short_stop = min(current_stop, close + ATR(14) * atr_trail_multiplier)

swing trail:
  long_stop = max(current_stop, latest_higher_low - buffer)
  short_stop = min(current_stop, latest_lower_high + buffer)

trendline trail:
  long_stop = max(current_stop, trendline_support - buffer)
  short_stop = min(current_stop, trendline_resistance + buffer)
```

Regime-aware trailing:

```text
if regime remains risk_on:
  use wider trail for runner

if regime drops to neutral:
  tighten trail

if regime drops to defensive or cash:
  close or hard-tighten runner
```

### 12. Reduce and Cash Rules

KJO-style public evidence repeatedly shows cash/reduction during weak regimes.
The bot must be able to do nothing.

Reduce rules:

```text
if BTC loses major support:
  block new longs
  reduce weak open longs
  move profitable longs to SL+

if USDT.D rises and BTC.D rises while alts weaken:
  block alt longs
  close weakest alt positions

if portfolio drawdown_from_peak >= 5%:
  cut risk_pct by 50%

if portfolio drawdown_from_peak >= 10%:
  cash mode
  block new futures
  require manual review or next-day reset

if daily_loss >= daily_loss_limit:
  activate kill switch for the day
```

Cash rules:

```text
cash_mode when:
  regime_score < 0
  market_data unreliable
  major event window is active and volatility is abnormal
  daily loss limit hit
  max consecutive losses hit
  open positions cannot be reconciled with exchange
```

### 13. Journaling

Every signal and order must be explainable after the fact.

Required journal fields:

```text
timestamp
strategy_version
symbol
side
regime_score
regime_label
pair_score
setup_score
entry_price
stop_price
tp1_price
tp2_price
tp3_price
risk_pct
risk_usdt
notional_usdt
leverage
margin_ratio
liquidation_price
liquidation_buffer_pct
spread_bps
funding_rate
depth_imbalance
fib_zone
structure_reason
confirmation_timeframe
entry_reason
rejection_reason
management_events
exit_reason
gross_pnl
net_pnl_after_fees
R_multiple
slippage_bps
```

Decision logging:

```text
log holds, not only entries
log rejected trades with exact blocker
log regime changes
log SL+ movement
log partial TP
log trailing updates
log kill-switch triggers
```

### 14. Validation

Win rate alone is not enough.

Promotion gates:

```text
closed_trades >= 500
expectancy_R > 0
profit_factor >= 1.25
max_drawdown_pct <= configured_gate
ending_equity > initial_equity
recent_equity_trend_improving is true
no open/unpriced/skipped orders in report
fees and slippage included
outlier_sensitivity remains positive
```

Out-of-sample gates:

```text
split history into walk-forward windows
optimize only on training window
validate on later unseen window
reject strategy if only one market regime works
reject strategy if removing top 5 trades makes expectancy negative
reject strategy if one pair creates all profit
```

Regime validation:

```text
report expectancy by:
  risk_on
  neutral
  defensive
  cash-blocked signals

report performance by:
  pair
  side
  timeframe
  fib zone
  setup type
  entry hour
  funding bucket
  spread bucket
```

Live-readiness gates:

```text
paper version hash is frozen
paper result passes promotion gates
dry-run order construction passes
private account stream works
reconciliation works
kill switch works
max loss/day works
manual live flag enabled
smallest possible live size first
```

## Bot Pseudo-Rules

Full decision loop:

```text
for each cycle:
  context = load_context()

  if safety_gate_fails(context):
    cancel_stale_orders()
    protect_open_positions()
    continue

  regime = compute_regime(context)

  manage_existing_positions(regime)

  if regime.label in [cash, defensive]:
    block_new_futures()
    continue

  candidates = []

  for symbol in mexc_universe:
    if liquidity_gate_fails(symbol):
      journal_reject(symbol, "liquidity")
      continue

    pair_score = compute_pair_score(symbol, regime)
    if pair_score < min_pair_score(regime):
      journal_reject(symbol, "pair_score")
      continue

    setup = detect_setup(symbol, regime)
    if setup.score < min_setup_score(regime):
      journal_reject(symbol, "setup_score")
      continue

    if setup.rr_to_tp1 < min_rr_to_tp1:
      journal_reject(symbol, "rr")
      continue

    sizing = compute_size(
      equity=context.equity,
      entry=setup.entry,
      stop=setup.stop,
      risk_pct=risk_pct_for_regime(regime),
      contract_size=symbol.contract_size,
    )

    leverage = choose_leverage(sizing, setup, regime)

    if risk_gate_fails(sizing, leverage, setup, context):
      journal_reject(symbol, "risk")
      continue

    candidates.append(build_trade_plan(symbol, regime, setup, sizing, leverage))

  ranked = rank_candidates(candidates)
  selected = enforce_portfolio_caps(ranked, context.open_positions, regime)

  for plan in selected:
    place_limit_order(plan)
    journal_plan(plan)
```

Position manager:

```text
for each open_position:
  update_unrealized_R()
  update_regime()

  if hard_invalidated:
    close_position("invalidation")
    continue

  if daily_loss_limit_hit:
    close_or_reduce_position("daily_loss_limit")
    continue

  if unrealized_R >= 1.0 and not sl_plus_active:
    partial_close(25% to 40%)
    move_stop_to_sl_plus()
    journal_management("sl_plus")

  if reached_TP2:
    partial_close(25% to 40%)
    activate_trailing()

  if trailing_active:
    update_trailing_stop()

  if regime_deteriorates:
    tighten_stop_or_close()
```

## Implementation Mapping

Already partially present:

- `strategy.py`: micro signal from spread, depth, funding, fair/index alignment.
- `risk.py`: leverage, notional, stop-loss requirement, kill-switch gate.
- `profit_hunt.py`: promotion-style filters for win rate, profit factor,
  drawdown, expectancy, and recent equity trend.
- `KJO_PUBLIC_STRATEGY_RESEARCH.md`: public evidence and high-level framework.

Needed next:

1. `regime.py`
   - BTC trend proxy.
   - Optional external dominance/TOTAL3 inputs.
   - Regime score and label.

2. `pair_selection.py`
   - Liquidity gate.
   - Relative strength ranking.
   - Pair score.

3. `structure.py`
   - Swing high/low.
   - Support/resistance.
   - Breakout/retest.
   - Fib zones.

4. `position_sizing.py`
   - Risk-based contract sizing.
   - Margin ratio.
   - Liquidation buffer gate.

5. `trade_management.py`
   - SL+.
   - Partial TP.
   - Trailing stop.
   - Reduce/cash logic.

6. Journal extension
   - Regime fields.
   - Pair/setup/risk fields.
   - Management event fields.

7. Validation extension
   - Expectancy by regime.
   - Pair-level performance.
   - Outlier sensitivity.
   - Walk-forward report.

## Practical Default Config

Conservative local paper defaults:

```text
min_regime_score = 2
min_pair_score_neutral = 4
min_pair_score_risk_on = 3
min_setup_score_neutral = 6
min_setup_score_risk_on = 5
min_rr_to_tp1 = 2.0
risk_pct_neutral = 0.25% to 0.50%
risk_pct_risk_on = 0.50% to 1.00%
max_total_open_risk_neutral = 1.00%
max_total_open_risk_risk_on = 3.00%
max_open_positions_neutral = 1
max_open_positions_risk_on = 3
sl_plus_activation_R = 1.0
tp1_close_pct = 25% to 40%
tp2_close_pct = 25% to 40%
daily_loss_limit = 2% paper, lower for first live test
drawdown_reduce_threshold = 5%
drawdown_cash_threshold = 10%
```

Aggressive paper-only KJO-inspired mode:

```text
min_regime_score = 4
min_pair_score = 4
min_setup_score = 6
min_rr_to_tp1 = 2.5
max_positions = 3
max_total_open_risk = 5%
risk_per_position = max_total_open_risk / max_positions
SL+ required at +1R
no martingale
cash mode after 10% drawdown
```

## Low-Frequency High-Conviction Model

Verified public Instagram recaps show two low-frequency, high-asymmetry
monthly futures performance screenshots:

```text
2025-07-22, https://www.instagram.com/p/DMZZEx2P5n0/
Total PnL = +Rp4,541,379,431
Win rate = 80.95%
Positions = 21
Risk/reward ratio = 1:18.64

2025-08-13, https://www.instagram.com/p/DNSCg8PvVQW/
Total PnL = +Rp4,314,910,557
Win rate = 61.54%
Positions = 26
Risk/reward ratio = 1:7.46
```

This confirms that public KJO-style monthly recaps are low frequency and high
asymmetry. The engine must not behave like a high-frequency signal bot.

Core implication:

```text
21 positions/month means roughly 0.70 closed positions/day
26 positions/month means roughly 0.86 closed positions/day
31 positions/month means roughly 1.03 closed positions/day
```

For a USD 2,000 account to become USD 250,000, the required multiplier is 125x.
If that happens across only 26-31 entries, the required compounded return per
entry is extremely high:

```text
26 entries: average +20.41% per entry
31 entries: average +16.85% per entry
```

This cannot be achieved by ordinary low-risk scalping. It requires a small
number of very high-conviction entries, strong regime alignment, asymmetric
RR, active compounding, and very strict protection once the trade moves in
profit. The verified recaps are especially important because they show two
different ways the edge can appear: 80.95% win rate with extreme 1:18.64
payoff asymmetry, and 61.54% win rate with still-large 1:7.46 payoff
asymmetry. In both cases, frequency stays low and average winner/loss
asymmetry is the main signature.

### What This Means For The Bot

Add a monthly trade budget:

```text
max_entries_per_month = 31
target_entries_per_month = 20 to 31
max_entries_per_day = 2
default_entries_per_day = 0 or 1
```

Entry quality must rise as the quota gets smaller:

```text
if entries_taken_this_month >= 20:
  require setup_score >= 7
  require regime_score >= 5
  require RR_to_TP1 >= 2.5

if entries_taken_this_month >= 26:
  require setup_score >= 8
  require regime_score >= 6
  require RR_to_TP1 >= 3.0
```

No-trade is expected:

```text
if no A++ setup:
  do not trade

if BTC/USDT.D/BTC.D/TOTAL3 conflict:
  do not trade

if price is mid-range:
  do not trade
```

### 125x Requirement Table

Minimum win counts to reach 125x across limited entries, assuming fixed
fractional compounding, no slippage, and every winner reaches the stated RR:

```text
26 entries:
  5% risk, 5R winners   -> needs about 23 wins out of 26
  10% risk, 3R winners  -> needs about 21 wins out of 26
  10% risk, 5R winners  -> needs about 15 wins out of 26
  15% risk, 3R winners  -> needs about 17 wins out of 26
  20% risk, 3R winners  -> needs about 16 wins out of 26

31 entries:
  5% risk, 5R winners   -> needs about 24 wins out of 31
  10% risk, 3R winners  -> needs about 23 wins out of 31
  10% risk, 5R winners  -> needs about 16 wins out of 31
  15% risk, 3R winners  -> needs about 19 wins out of 31
  20% risk, 3R winners  -> needs about 17 wins out of 31
```

Interpretation:

- At 0.5%-1% risk, 125x in one month is not mathematically realistic.
- At 3%-5% risk, the win rate and RR required are still extreme.
- At 10%-20% risk, the target becomes mathematically possible but account
  survival becomes fragile.
- Therefore this belongs in paper mode first, with hard drawdown stops.

### KJO-Style Aggressive Paper Variant

Use only for local paper testing:

```text
mode = kjo_low_frequency_aggressive
starting_equity = 2000
target_equity = 250000
max_entries_per_month = 31
max_entries_per_day = 2
min_regime_score = 6
min_setup_score = 8
min_RR_to_TP1 = 3.0
risk_per_trade = 3% to 5% initially
max_total_open_risk = 5%
max_open_positions = 3
SL+ activation = +1R
partial_take_profit = 20% to 40% at TP1
runner_allowed = true
monthly_drawdown_stop = 20%
daily_drawdown_stop = 5%
no_martingale = true
```

Promotion rule:

```text
do not increase risk above 5% unless:
  exact strategy version has 500+ closed paper trades
  expectancy remains positive after fees/slippage
  max drawdown is survivable
  removing top 5 outlier wins does not destroy profitability
```

### Strategy Shape

This low-frequency interpretation changes the engine priority:

1. Fewer entries.
2. Higher confluence.
3. Higher RR.
4. Winners must be allowed to run.
5. SL+ protects capital after confirmation.
6. Cash mode is common, not a bug.

## Final Strategy Summary

KJO-style from public evidence, translated into a full trading sequence:

1. Read the market regime first.
2. Stay mostly cash when BTC/dominance/alt breadth are hostile.
3. Scan only liquid pairs with relative strength or weakness.
4. Wait for price to reach a real location: support, demand, supply,
   breakout/retest, trendline, or Fib zone.
5. Enter only after close confirmation and RR validation.
6. Size from stop distance and fixed account risk.
7. Use the lowest leverage that satisfies margin constraints.
8. Reject trades where liquidation is too close.
9. Take partial profit and move to SL+ around +1R or TP1.
10. Trail the runner while the regime stays valid.
11. Reduce or go cash when BTC/regime breaks, drawdown expands, or loss limits
    trigger.
12. Journal every decision.
13. Promote to live only after the exact version survives large paper samples,
    walk-forward testing, realistic fees/slippage, and outlier sensitivity.
