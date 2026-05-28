# Open Source Engine References

## Current Policy

We pull large open source trading engines only when they have a direct use in the MEXC Futures build.

The local project stays small and owns the MEXC-specific safety layer, credentials handling, DNS workaround, risk checks, reconciliation, and read-only verification commands. Big engines are kept under `upstream/` as references first, not installed into runtime by default.

## Pulled References

### NautilusTrader

Path:

```bash
upstream/nautilus_trader
```

Use:

- core trading engine model
- instrument model reference, especially `CryptoPerpetual`
- live data/execution client shape
- adapter/factory layout
- reconciliation report shape

Status:

- pulled as shallow reference
- local revision: `de6443c` on `develop`
- not installed as runtime yet
- first bridge layers implemented locally: instrument specs, public market data specs, private execution report specs, private WS parsing, and REST-vs-WS reconciliation

### Hummingbot

Path:

```bash
upstream/hummingbot
```

Use:

- connector architecture reference
- exchange API client patterns
- bot operational patterns
- strategy/executor architecture reference

Status:

- pulled as shallow reference
- local revision: `884dd34` on `development`
- not installed as runtime yet
- audited for connector patterns

Relevant local paths:

```bash
upstream/hummingbot/hummingbot/connector/exchange/mexc
upstream/hummingbot/hummingbot/data_feed/candles_feed/mexc_perpetual_candles
upstream/hummingbot/hummingbot/connector/perpetual_derivative_py_base.py
upstream/hummingbot/hummingbot/strategy_v2/executors
```

Finding:

- Hummingbot has a MEXC spot connector with protobuf WebSocket handling.
- Hummingbot has a MEXC perpetual candles feed using `contract.mexc.com`.
- Hummingbot does not currently give us a ready MEXC Futures derivative connector to drop in.
- It is still useful for connector lifecycle, rate-limit, WebSocket, user-stream, and strategy executor patterns.

## Why Not Install Everything Immediately?

- Large trading engines can bring heavy build chains, conflicting dependency versions, and long setup time.
- MEXC Futures live trading has high downside if connector semantics are wrong.
- We need verified local read-only behavior first: contract mapping, WS market data, private REST reports, private WS reconciliation.
- Installing a full engine is useful only after our adapter boundaries are stable.

## Current Build Priority

1. Keep MEXC connector safety independent and tested.
2. Use NautilusTrader as the main engine target.
3. Use Hummingbot as connector/ops reference.
4. Keep private WS parsing and REST-vs-WS reconciliation under local real-only tests.
5. Next decide whether to embed the adapter into NautilusTrader runtime, package it as a separate adapter, or keep running the local engine shell until live mutation paths are ready.
