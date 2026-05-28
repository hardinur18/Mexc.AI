# Live Readiness Criteria

This project is not live-trading ready until every item below is true.

## Current Snapshot

Latest local paper readiness:

- `localPaperReadinessPercent`: `48.3`
- saved paper samples: `22 / 100`
- priced/evaluable paper entries: `7 / 50`
- unpriced/skipped closed entries: `1`
- price simulation: `candle-high-low` with 240 real MEXC 1m candles
- global edge win rate: `0.571429`
- global rough net PnL: `-0.019828616` USDT
- paper performance ending equity from `6.00000001` initial equity: `5.980171394` USDT
- paper performance max drawdown: `0.022693358` USDT (`0.3780%`)
- paper performance profit factor: `0.6014788157640018`
- paper performance expectancy: `-0.002832659428571428571428571429` USDT/trade
- active policy side: `open-short`
- policy side win rate: `0.666667`
- policy side rough net PnL: `-0.003531642` USDT
- best profit-hunt research candidate: `open-short`, `minDepthImbalanceTop10=0.12`, `maxSpreadBps=0.02`, `maxAbsFundingRate=0.00005`, 5 closed trades, win-rate `0.8`, profit factor `1.3187502704535838`
- best profit-hunt blocker: `closed count 5 below gate 50`
- `readyForLocalPaperStrategy`: `false`
- `readyForLive`: `false`
- `liveMutationPhaseEnabled`: `false`
- `liveOrderSubmitted`: `false`
- live mutation client: disabled in this local-paper build
- readiness profile: `strict-local-paper`

The connector/read-only runtime is healthy enough for local paper collection:

- market wire is `ok=true`
- state handoff is `ok=true`
- private read-only auth probe passes
- live submit/cancel remains intentionally unavailable

But the strategy edge is not proven.

## Minimum Local Gates

Do not run live trading, even with tiny size, until these local gates pass:

- Safety audit has no findings.
- Private read-only auth probe passes.
- Live flags are off during paper collection.
- State handoff has no blockers.
- Market wire builds real `QuoteTick`, `TradeTick`, and `OrderBookDeltas`.
- Paper sample count is at least `100`.
- Evaluable closed virtual entries are at least `50`; paper probes do not count toward the main performance gate.
- Unpriced/invalid closed paper orders are surfaced as skipped and cannot inflate win-rate, expectancy, or readiness.
- `candle-high-low` readiness uses real candle coverage without sample-close fallback.
- Readiness cannot be inflated by weaker CLI thresholds; strict local floors are enforced again inside the report builder.
- Edge/performance horizons are floored at 3 samples and freshness is capped at 3600 seconds for strict readiness.
- Global edge win rate is at least the configured gate, currently `0.55`.
- Global rough net PnL is positive after double-taker-fee estimate.
- Active policy side rough net PnL is positive.
- Rolling windows `5`, `10`, `25`, and `50` are all positive enough to pass readiness.
- Paper performance has at least `50` priced closed virtual trades, no open virtual orders, ending equity above initial equity, recent 5-trade equity trend positive, expectancy above zero, profit factor at least `1.25`, win-rate at least `0.55`, max drawdown pct at most `0.02`, and consecutive losses at most `3`.
- No live order path is exposed outside the explicit triple-lock live implementation phase.
- `MEXC_LIVE_MUTATION_PHASE_ENABLED` remains `false` until the live phase is deliberately opened.

## Statistical Validity

Current validity is low:

- `20` samples is not thousands of samples.
- `8` evaluable entries is too small to trust, and probe entries are only recovery telemetry.
- The current rough PnL is negative.
- Paper ledger now supports candle high/low simulation, but 1m candles still cannot determine exact intra-candle order path when stop and take-profit are both touched.

Target validity before any live consideration:

- at least `100` saved local paper samples for basic local readiness
- preferably `500+` samples before serious confidence
- preferably `1000+` samples across different market regimes before live mutation work
- separate analysis for long and short sides
- out-of-sample window after any strategy or gate change

## Next Engineering Work

Highest priority:

1. Collect more real local paper samples until at least `100 / 100` saved samples and at least `50` priced closed virtual entries.
2. Tune and observe the new volatility/regime filter across several market regimes.
3. Keep persisting paper execution lifecycle and performance snapshots after every sample batch.
4. Add longer out-of-sample windows after every strategy/gate change.
5. Keep live submit/cancel locked until readiness, policy-side quality, rolling windows, and paper performance are all positive.
