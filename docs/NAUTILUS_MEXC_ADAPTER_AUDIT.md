# Nautilus MEXC Adapter Audit

## Upstream Pulled

NautilusTrader was cloned locally into:

```bash
upstream/nautilus_trader
```

Current pulled revision:

```text
de6443c develop
```

## Adapter Pattern To Follow

Best reference: `upstream/nautilus_trader/nautilus_trader/adapters/binance`.

Why Binance Futures:

- It already models crypto perpetuals with `CryptoPerpetual`.
- It has separate instrument provider, market data client, execution client, HTTP client, WebSocket routes, schemas, and factories.
- It maps exchange contract metadata into Nautilus precision, increment, margin, fee, and quantity fields.

Template reference:

- `upstream/nautilus_trader/nautilus_trader/adapters/_template`

The template is useful for required method shape, but Binance Futures is the practical exchange adapter reference.

## MEXC To Nautilus Instrument Mapping

First local bridge implemented:

```bash
mexc-engine nautilus-instrument BTC_USDT
mexc-engine nautilus-instruments --summary-only
mexc-engine nautilus-instruments --output data/nautilus_instruments.json
```

Mapping target:

- MEXC `symbol` -> Nautilus raw symbol.
- `BTC_USDT` -> `BTC_USDT-PERP.MEXC` instrument ID.
- `baseCoin`, `quoteCoin`, `settleCoin` -> currencies.
- `priceScale`, `priceUnit` -> price precision and increment.
- `volScale`, `volUnit` -> size precision and increment.
- `contractSize` -> contract multiplier.
- `minVol`, `maxVol` -> min/max quantity.
- `initialMarginRate`, `maintenanceMarginRate` -> margin fields.
- `makerFeeRate`, `takerFeeRate` -> fee fields.
- `apiAllowed`, `state`, risk tier fields -> adapter info metadata.

## Next Implementation Order

1. MEXC instrument provider around `/api/v1/contract/detail/country`. Done locally in `mexc_futures_engine.nautilus_provider`.
2. Build public market data bridge from MEXC WS ticker/depth/deal into Nautilus quote/trade/book event specs. Done locally in `mexc_futures_engine.market_data`.
3. Build read-only execution reports from private REST: account, positions, open orders, history orders, fills. Done locally in `mexc_futures_engine.execution_reports`.
4. Add private WS event parser for account/order/position updates. Initial control/update classifier done locally in `mexc_futures_engine.private_stream`.
5. Reconcile private REST startup state with private WS login/update stream. Done for read-only idle/startup state in `mexc_futures_engine.reconciliation`.
6. Build a Nautilus adapter readiness manifest around all read-only boundaries. Done locally in `mexc_futures_engine.adapter_readiness`.
7. Package the local MEXC adapter boundary into Nautilus-style config/provider/data/execution modules. Done locally in `mexc_futures_engine.nautilus_adapter`.
8. Wire the packaged boundary into a local Nautilus runtime harness check. Done locally in `mexc_futures_engine.nautilus_adapter.runtime_harness`.
9. Wire private REST execution reports into real sandboxed Nautilus execution/account objects. Done locally in `mexc_futures_engine.nautilus_adapter.runtime_execution_wire`.
10. Combine sandboxed instrument/market/execution state into a read-only strategy handoff snapshot. Done locally in `mexc_futures_engine.nautilus_adapter.state_handoff`.
11. Persist paper-trading decisions from state handoff into local SQLite and audit samples. Done locally in `mexc_futures_engine.paper`.
12. Add paper signal gates from real market metrics and edge quality gate from saved virtual samples. Done locally in `mexc_futures_engine.paper`.
13. Only after local reconciliation and paper edge stay stable, wire submit/cancel order paths behind the existing triple live lock.

No live mutation should be exposed until the adapter can reconcile startup state from REST and stream updates from WS, then pass the explicit triple live lock.

## Public Market Data Bridge

Implemented command:

```bash
mexc-engine ws-bridge ticker BTC_USDT --messages 3
mexc-engine ws-bridge deal BTC_USDT --messages 3
mexc-engine ws-bridge depth BTC_USDT --messages 3
```

Current mapping:

- `push.ticker` -> metadata-only `QuoteTick` spec with bid/ask prices, last/fair/index/funding metadata, but no bid/ask sizes.
- `push.deal` -> `TradeTick` spec with trade id, price, size, and preserved raw MEXC side codes.
- `push.depth` -> `OrderBookDeltas` spec with L2 market-by-price deltas and sequence/version fields, plus a depth-derived `QuoteTick` from the maintained top of book once both sides have real prices and sizes.

MEXC deal side codes are preserved as raw fields until the exact enum semantics are locked against documentation or multiple live samples. The bridge uses `NO_AGGRESSOR` for now rather than guessing.

## Private REST Execution Reports

Implemented command:

```bash
mexc-engine execution-reports --symbol BTC_USDT --currency USDT --summary-only
mexc-engine execution-reports --symbol BTC_USDT --currency USDT --output data/execution_reports.json
```

Current mapping:

- account asset -> `AccountState` spec
- open positions -> `PositionStatusReport` specs
- open/history orders -> `OrderStatusReport` specs
- order deals -> `FillReport` specs

MEXC side codes are labeled as `OPEN_LONG`, `CLOSE_SHORT`, `OPEN_SHORT`, `CLOSE_LONG` and raw state codes are preserved. Submit/cancel paths remain locked and are not exposed by these report commands.

## Private WebSocket Bridge

Implemented command:

```bash
mexc-engine ws-private-bridge --messages 5
```

Current behavior:

- login/filter acknowledgements -> `ControlAck`
- account/balance/asset channels -> `AccountUpdate`
- position channels -> `PositionUpdate`
- order channels -> `OrderUpdate`
- deal/fill/trade channels -> `FillUpdate`
- unknown private channels -> `PrivateUpdate`

When the account is idle, MEXC currently returns only login/filter acknowledgements. Raw payload preservation is available with `--include-raw`.

## REST vs Private WS Reconciliation

Implemented command:

```bash
mexc-engine reconcile-engine --symbol BTC_USDT --currency USDT --summary-only
```

Current behavior:

- fetches real private REST snapshots for assets, account asset, positions, open orders, and recent orders
- builds Nautilus-style execution reports from REST snapshots and recent fills
- logs into real private WebSocket and checks `login` + `personal.filter` acknowledgements
- marks ACK-only private WS windows as reconcilable idle state when REST has no open positions/orders
- reports blockers separately from warnings, so an idle account does not look failed

Latest local real check returned `ok=true`, `restWsReconcilable=true`, `liveSafeState=true`, no open positions, and no open orders.

## Nautilus Adapter Readiness Manifest

Implemented command:

```bash
mexc-engine nautilus-adapter-check --symbol BTC_USDT --currency USDT --summary-only
```

Current behavior:

- verifies NautilusTrader upstream reference is present
- loads the MEXC contract into the local instrument provider mapping
- opens real public WebSocket streams for ticker, deal, and depth
- confirms parsed market data event specs: `QuoteTick`, `TradeTick`, `OrderBookDeltas`
- confirms private REST execution reports include account state
- confirms private WebSocket login/filter ACKs
- embeds the REST-vs-private-WS reconciliation result
- keeps live mutation status locked

Latest local real check returned `ok=true`, `readyForReadOnlyRuntime=true`, and `readyForLiveRuntime=false`.

## Packaged Adapter Boundary

Implemented package:

```text
mexc_futures_engine.nautilus_adapter
```

Modules:

- `config`: read-only adapter config and safety assertions
- `provider`: `MexcFuturesInstrumentProviderBoundary`
- `data`: `MexcFuturesDataClientBoundary`
- `execution`: `MexcFuturesExecutionClientBoundary`
- `manifest`: static package manifest

Implemented command:

```bash
mexc-engine nautilus-adapter-manifest --output data/nautilus_adapter_manifest.json
```

The package has no Nautilus runtime dependency yet. This is intentional: it lets us verify importability, capabilities, and safety locks before wiring into NautilusTrader itself. Live submit/cancel methods raise `LiveMutationUnavailable`.

## Runtime Harness Read-Only

Implemented command:

```bash
mexc-engine nautilus-runtime-harness --symbol BTC_USDT --currency USDT --summary-only
```

Current behavior:

- runs the real adapter check through packaged boundary classes
- confirms local MEXC provider/data/execution boundary methods exist
- confirms Nautilus template and Binance Futures reference files are present
- probes whether the upstream Nautilus runtime is importable
- keeps live runtime unavailable

Latest local real check returned `ok=true`, `readyForRuntimeHarness=true`, and `readyForNautilusRuntimeImport=true`.

Sandbox runtime installed:

```text
.venv-nautilus
```

Sandbox package:

```text
nautilus_trader 1.227.0a20260513
```

The upstream source checkout probe still fails on `nautilus_trader.core.data` because `upstream/nautilus_trader` itself is not built. That is acceptable now: runtime import is available through the isolated wheel sandbox. Live runtime remains unavailable.

## Runtime Wire Read-Only

Implemented command:

```bash
mexc-engine nautilus-runtime-wire --symbol BTC_USDT --summary-only
```

Current behavior:

- loads MEXC contract detail through the packaged instrument provider boundary
- converts the local MEXC instrument spec into a real Nautilus `CryptoPerpetual`
- runs the conversion inside `.venv-nautilus`
- verifies precision, increments, multiplier, margin, fee, and currency fields are accepted by Nautilus runtime
- keeps live runtime unavailable

Latest local real check returned `ok=true`, `readyForSandboxedNautilusRuntimeReadOnly=true`, and created one `CryptoPerpetual` object for `BTC_USDT-PERP.MEXC`.

## Market Data Runtime Wire Read-Only

Implemented command:

```bash
mexc-engine nautilus-market-wire --symbol BTC_USDT --messages 5 --summary-only
```

Current behavior:

- opens real MEXC WebSocket streams for ticker, deal, and depth
- converts `TradeTick` into real Nautilus `TradeTick`
- converts `OrderBookDeltas` into real Nautilus `OrderBookDeltas`
- converts depth-derived top of book into real Nautilus `QuoteTick` with matching bid/ask precision and real sizes
- skips ticker-derived `QuoteTick` because MEXC ticker does not include bid/ask sizes required by Nautilus
- keeps live runtime unavailable

Latest local real check returned `ok=true`, `readyForSandboxedNautilusMarketDataReadOnly=true`, and Nautilus sandbox objects for `QuoteTick`, `TradeTick`, and `OrderBookDeltas`. No fake bid/ask sizes are generated.

## Execution Runtime Wire Read-Only

Implemented command:

```bash
mexc-engine nautilus-execution-wire --symbol BTC_USDT --currency USDT --summary-only
```

Current behavior:

- fetches real private REST execution reports through `MexcFuturesExecutionClientBoundary`
- converts account asset into real Nautilus `AccountState`
- converts history/open order reports into real Nautilus `OrderStatusReport`
- converts deal rows into real Nautilus `FillReport`
- converts positions into real Nautilus `PositionStatusReport` when positions exist
- runs conversion inside `.venv-nautilus`
- keeps live runtime unavailable

Latest local real check returned `ok=true`, `readyForSandboxedNautilusExecutionReadOnly=true`, and created 27 Nautilus objects from 27 MEXC execution reports: one `AccountState`, 13 `OrderStatusReport`, and 13 `FillReport`.

MEXC returned a tiny balance precision mismatch where source `total=6`, `locked=0`, and `free=6.0000000052`. Nautilus `AccountBalance` enforces `total=locked+free`, so the wire normalizes model `total` to `6.0000000052` and records that adjustment in the output. No fake account/order/fill data is generated.

## State Handoff Read-Only

Implemented command:

```bash
mexc-engine nautilus-state-handoff --symbol BTC_USDT --currency USDT --summary-only
```

Current behavior:

- runs instrument wire, market data wire, and execution wire against real MEXC data
- builds a local state cache summary from sandboxed Nautilus runtime objects
- exposes account balance, open position count, active order count, recent order/fill count, latest trade, and book delta sequence
- attaches the existing real-only strategy preview and preflight status
- keeps live runtime unavailable

Latest local real check returned `ok=true`, `readyForStrategyReadOnly=true`, `safeToEvaluateSignals=true`, and `safeToOpenNewPositionPreflight=true` with zero open positions and zero active orders. The strategy preview was actionable in that sample, but it remains only a read-only/preflight handoff. No submit/cancel path is exposed.

## Paper Trading Audit Read-Only

Implemented commands:

```bash
mexc-engine nautilus-paper-decision --symbol BTC_USDT --currency USDT --summary-only --save --paper-equity 6.00000001 --min-depth-imbalance 0.12 --max-spread-bps 2.5 --max-abs-funding-rate 0.0005 --max-market-age-seconds 60 --quality-gate-lookback 50 --quality-max-sample-age-seconds 86400 --quality-rolling-windows 5,10,25,50
mexc-engine nautilus-paper-loop --symbol BTC_USDT --currency USDT --iterations 3 --interval 5 --target-samples 100 --target-closed-trades 50 --save --paper-equity 6.00000001 --min-depth-imbalance 0.12 --max-spread-bps 2.5 --max-abs-funding-rate 0.0005 --max-market-age-seconds 60 --quality-gate-lookback 50 --quality-max-sample-age-seconds 86400 --quality-rolling-windows 5,10,25,50
mexc-engine nautilus-paper-audit --symbol BTC_USDT --currency USDT --lookback 50 --min-samples 5 --edge-horizon-samples 3 --min-edge-evaluable 3 --min-edge-win-rate 0.55 --min-side-edge-evaluable 2 --min-side-edge-win-rate 0.55 --max-sample-age-seconds 86400 --rolling-windows 5,10,25,50
mexc-engine nautilus-paper-edge --symbol BTC_USDT --currency USDT --lookback 50 --horizon-samples 3 --price-simulation candle-high-low --candle-interval 1m --candle-lookback 240
mexc-engine nautilus-paper-ledger --symbol BTC_USDT --currency USDT --lookback 100 --horizon-samples 3 --include-probes --price-simulation candle-high-low --candle-interval 1m --candle-lookback 240 --output data/nautilus_paper_ledger.json
mexc-engine nautilus-paper-performance --ledger data/nautilus_paper_ledger.json --initial-equity 6.00000001 --output data/nautilus_paper_performance.json
mexc-engine readiness --symbol BTC_USDT --currency USDT --lookback 100 --target-samples 100 --rolling-windows 5,10,25,50 --price-simulation candle-high-low --candle-interval 1m --candle-lookback 240 --performance-initial-equity 6.00000001 --performance-horizon-samples 3
```

Current behavior:

- runs the real state handoff pipeline
- turns the strategy preview into a virtual paper decision
- gates virtual entries with real strategy metrics: top-10 depth imbalance direction, spread bps, and absolute funding rate
- blocks paper entries when required market metrics are missing
- checks TradeTick and OrderBookDeltas freshness when `--max-market-age-seconds` is active
- records would-open vs hold without creating any exchange order
- estimates virtual notional, margin, and taker fee from real MEXC instrument metadata
- stores `nautilus_paper_decision` events in local SQLite when `--save` is used
- audits recent samples by action, blocker reason, and consecutive would-open streak
- reviews edge by walking forward through the configured sample horizon and marking `take-profit`, `stop-loss`, or `horizon` exits
- summarizes edge both globally and by side
- sorts audit samples by timestamp/event id before latest/consecutive/recovery checks
- reports rolling quality windows and blocks live readiness when recent windows fail edge, PnL, or policy-side quality
- reports `localPaperReadinessPercent` from safety, live lock, sample volume/freshness, paper quality, policy side, and rolling quality
- applies `paperQualityGovernor` before new paper entries when `--quality-gate-lookback` is active; a paused side saves a hold sample plus an exploratory `paperProbe` candidate for recovery stats while keeping `wouldOpen=false`
- allows paused paper entries to recover only after the recent evaluable window clears win-rate and positive rough PnL
- exposes `paperQualityGate.readyForLiveCandidate`, which stays false until sample count, edge win-rate, and rough net PnL clear the configured gates
- supports REST MEXC candles through `mexc-engine klines` and optional `--trend-filter` on paper decisions
- builds a read-only paper execution ledger from saved samples with `NEW`, `OPEN`, `FILLED`, `EXPIRED`, `STOPPED`, and `TAKE_PROFIT` lifecycle states
- supports candle high/low price simulation for paper edge/ledger/readiness with conservative stop-first ambiguity policy
- builds a read-only paper performance report with equity curve, recent equity trend, max drawdown, win-rate, profit factor, expectancy, and consecutive losses
- adds a read-only volatility/regime filter from real REST candles; flat or volatile regimes can block paper entries before any virtual order is created
- keeps live mutation disabled in the local-paper build even if live flags are manually armed, including direct low-level private mutation requests
- enforces strict readiness floors inside the report builder so weaker CLI/internal threshold settings cannot create a 100% local score
- makes `nautilus-paper-loop` target-aware with `--target-samples`, `--target-closed-trades`, valid sample counting, and optional `--readiness-after` summary after saved real samples
- exposes readiness `collectionProgress` so sample count, closed virtual trade count, open paper orders, unpriced/skipped orders, latest sample, and top blockers are visible in one place
- keeps paper performance honest by excluding unpriced closed orders and probes from the strict main performance gate
- isolates live-balance preflight blockers from paper-only margin checks when explicit `--paper-equity` is supplied
- blocks strict readiness unless the recent 5-trade paper equity trend is improving
- aligns paper quality governor, standalone audit, and edge review with strict candle-high-low evaluation without sample-close fallback
- persists `entryMetrics` on paper ledger orders from paper gates and volatility filters, then lets `nautilus-profit-hunt` sweep depth/spread/funding/range filters without submitting live orders

Latest local real checks saved 22 paper decision samples. With a 3-sample horizon and candle-high-low simulation from 240 real MEXC 1m candles, the newest audit returned `readyForPaperReview=true`, but `paperQualityGate.readyForLiveCandidate=false`: 7 priced/evaluable entries had 4 wins, 3 losses, win-rate `0.571429`, and total rough net PnL `-0.019828616` USDT after the double-taker-fee estimate. `open-short` remains the only allowed strategy side and has win-rate `0.666667`, but its rough net PnL remains negative at `-0.003531642`, so `strategyPolicyQualityGate.readyForCurrentStrategyLiveCandidate=false`. Rolling windows still fail, especially the latest 5/10-sample windows with no evaluable open-short entries. The latest readiness report with target 100 samples and 50 priced closed entries returned `localPaperReadinessPercent=48.3`, `readyForLocalPaperStrategy=false`, and `readyForLive=false`. The latest ledger has `priceSimulationFallback=null`, 8 virtual entries, 7 priced closed entries, 1 unpriced/skipped closed entry, 0 open entries, and no live order submission. The latest performance report has win-rate `0.5714285714285714`, profit factor `0.6014788157640018`, expectancy `-0.002832659428571428571428571429` USDT/trade, and equity moving from `6.00000001` down to `5.980171394` USDT. Profit hunt now finds a promising research-only `open-short` entry-metric candidate (`minDepthImbalanceTop10=0.12`, `maxSpreadBps=0.02`, `maxAbsFundingRate=0.00005`) with 5 closed trades, win-rate `0.8`, profit factor `1.3187502704535838`, and net PnL `+0.007233514` USDT, but strict promotion rejects it because closed count `5` is below gate `50`. A real volatility-filter loop sample with 60 MEXC 1m candles classified the market as `flat` (`avgRangeBps=4.313322450883798774309129947`) and held the paper decision below the configured `5.0` bps floor.

All paper samples keep `liveOrderSubmitted=false`.
