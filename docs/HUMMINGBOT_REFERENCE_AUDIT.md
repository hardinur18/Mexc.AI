# Hummingbot Reference Audit

## Pulled

Path:

```bash
upstream/hummingbot
```

Revision:

```text
884dd34 development
```

Local shallow clone size:

```text
22M
```

## Useful Pieces

### MEXC Spot Connector

Path:

```bash
upstream/hummingbot/hummingbot/connector/exchange/mexc
```

Useful for:

- connector file layout
- REST/WS assistant lifecycle
- MEXC spot protobuf stream decoding
- order book data source patterns
- user stream keepalive/listen-key management for spot
- order state mapping pattern

Important note: this is MEXC spot, not MEXC Futures.

### MEXC Perpetual Candles

Path:

```bash
upstream/hummingbot/hummingbot/data_feed/candles_feed/mexc_perpetual_candles
```

Useful for:

- confirmed `contract.mexc.com` futures candle endpoint usage
- interval mapping:
  - `1m` -> `Min1`
  - `5m` -> `Min5`
  - `1h` -> `Min60`
  - `4h` -> `Hour4`
  - `1d` -> `Day1`
- `sub.kline` WebSocket payload shape

### Perpetual Connector Base

Path:

```bash
upstream/hummingbot/hummingbot/connector/perpetual_derivative_py_base.py
```

Useful for:

- perpetual position tracking model
- funding info stream pattern
- leverage and position mode management shape
- dynamic trading pair add/remove lifecycle

## Not Used As Runtime Yet

Hummingbot is not installed or run as our bot runtime because:

- our target engine adapter is still NautilusTrader
- MEXC Futures connector semantics are being verified independently
- Hummingbot's MEXC connector is spot, while our account flow is futures
- live mutation remains locked until REST/WS reconciliation is proven

## How It Changes Our Plan

Hummingbot adds reference value, but does not replace the current path.

Current path stays:

1. MEXC read-only connector foundation.
2. Nautilus-compatible instrument, market data, and execution report specs.
3. Private WS parser and REST-vs-WS reconciliation.
4. Only then live submit/cancel design behind triple lock.

Hummingbot helps us design connector lifecycle and strategy executors, especially after reconciliation is stable.
