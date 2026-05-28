# Engine Pull Plan

Status: NautilusTrader dan Hummingbot sudah di-pull lokal sebagai shallow reference pada 2026-05-14. Belum di-install sebagai runtime engine penuh, karena adapter MEXC Futures masih kita stabilkan di local shell dulu.

## Yang Sudah Di-Pull

```text
upstream/nautilus_trader  de6443c develop
upstream/hummingbot       884dd34 development
```

## Kenapa Belum Full Runtime Install?

Shallow pull sudah cukup untuk membaca adapter architecture, model instrument, execution report shape, WebSocket client pattern, dan lifecycle connector. Full install/runtime sekarang belum memberi nilai lebih besar dibanding risikonya:

- dependency besar bisa mengubah lingkungan lokal
- build chain NautilusTrader lebih berat
- Hummingbot tidak punya MEXC Futures derivative connector siap pakai
- live mutation masih di-hard-disable pada build lokal sampai rekonsiliasi stabil, paper edge positif, dan phase live execution dibuat eksplisit

## Checklist Hijau Local

1. `mexc-engine asset USDT` berhasil.
2. `mexc-engine positions BTC_USDT` berhasil.
3. `mexc-engine ws-public ticker BTC_USDT --messages 3` menerima data.
4. `mexc-engine ws-private-bridge --messages 5` login dan menerima ACK private stream.
5. Risk guard + kill switch tetap memblokir order live.
6. `mexc-engine reconcile-engine --symbol BTC_USDT --currency USDT --summary-only` mengembalikan `ok=true`.
7. `mexc-engine nautilus-adapter-check --symbol BTC_USDT --currency USDT --summary-only` mengembalikan `readyForReadOnlyRuntime=true`.
8. `mexc-engine nautilus-adapter-manifest --output data/nautilus_adapter_manifest.json` membuat manifest package boundary.
9. `mexc-engine nautilus-runtime-harness --symbol BTC_USDT --currency USDT --summary-only` mengembalikan `readyForRuntimeHarness=true`.
10. `.venv-nautilus` berhasil install wheel `nautilus_trader 1.227.0a20260513`.
11. `mexc-engine nautilus-runtime-harness --symbol BTC_USDT --currency USDT --summary-only` sekarang mengembalikan `readyForNautilusRuntimeImport=true`.
12. `mexc-engine nautilus-runtime-wire --symbol BTC_USDT --summary-only` membuat object `CryptoPerpetual` Nautilus untuk `BTC_USDT-PERP.MEXC`.
13. `mexc-engine nautilus-market-wire --symbol BTC_USDT --messages 5 --summary-only` membuat object Nautilus `QuoteTick` depth-derived dengan size asli, `TradeTick`, dan `OrderBookDeltas`.
14. `mexc-engine nautilus-execution-wire --symbol BTC_USDT --currency USDT --summary-only` membuat object Nautilus `AccountState`, `OrderStatusReport`, dan `FillReport` dari private REST MEXC real.
15. `mexc-engine nautilus-state-handoff --symbol BTC_USDT --currency USDT --summary-only` membuat state cache snapshot read-only untuk strategi lokal.
16. `mexc-engine nautilus-paper-decision --symbol BTC_USDT --currency USDT --summary-only --save` menyimpan keputusan virtual paper-trading ke SQLite.
17. `mexc-engine nautilus-paper-audit --symbol BTC_USDT --currency USDT --lookback 50 --min-samples 5 --edge-horizon-samples 3 --min-edge-evaluable 3 --min-edge-win-rate 0.55 --min-side-edge-evaluable 2 --min-side-edge-win-rate 0.55 --max-sample-age-seconds 86400 --rolling-windows 5,10,25,50` mengaudit sample paper tersimpan, freshness, rolling window, side gate, dan quality gate kandidat live.
18. `mexc-engine nautilus-paper-edge --symbol BTC_USDT --currency USDT --lookback 50 --horizon-samples 3 --price-simulation candle-high-low --candle-interval 1m --candle-lookback 240` mengevaluasi entry virtual terhadap sample market dan candle high/low MEXC real, termasuk stop-loss/take-profit virtual bila tersentuh.
19. `mexc-engine nautilus-paper-decision --symbol BTC_USDT --currency USDT --summary-only --save --paper-equity 6.00000001 --min-depth-imbalance 0.12 --max-spread-bps 2.5 --max-abs-funding-rate 0.0005 --max-market-age-seconds 60 --quality-gate-lookback 50 --quality-max-sample-age-seconds 86400 --quality-rolling-windows 5,10,25,50` memakai gate market real, paper-only equity, freshness, rolling quality, side quality governor, dan `paperProbe` recovery sebelum mencatat virtual entry.
20. `mexc-engine readiness --symbol BTC_USDT --currency USDT --lookback 100 --target-samples 100 --rolling-windows 5,10,25,50 --price-simulation candle-high-low --candle-interval 1m --candle-lookback 240 --performance-initial-equity 6.00000001 --performance-horizon-samples 3` menggabungkan safety plus private auth probe, live lock, sample volume/freshness, paper quality, policy side, rolling window, dan performance menjadi readiness report lokal.
21. `mexc-engine klines BTC_USDT --interval 1m --lookback 60 --summary-only` mengambil candle REST MEXC real untuk trend filter.
22. `mexc-engine nautilus-paper-decision --symbol BTC_USDT --currency USDT --summary-only --save --trend-filter --trend-interval 1m --trend-lookback 60 --trend-short-period 5 --trend-long-period 20` menambahkan gate trend candle EMA ke paper decision.
23. `mexc-engine nautilus-paper-ledger --symbol BTC_USDT --currency USDT --lookback 100 --horizon-samples 3 --include-probes --price-simulation candle-high-low --candle-interval 1m --candle-lookback 240 --output data/nautilus_paper_ledger.json` membentuk ledger virtual read-only dari sample tersimpan dan candle high/low MEXC real.
24. `mexc-engine nautilus-profit-hunt --symbol BTC_USDT --currency USDT --lookback 100 --horizon-samples 3 --initial-equity 6.00000001 --confidence-thresholds 0,0.65,0.7,0.75,0.8 --min-depth-imbalance-sweep 0.12,0.25,0.35,0.5,0.7 --max-spread-bps-sweep 0.02,0.05,0.1 --max-abs-funding-rate-sweep 0.00005,0.0001,0.0005 --min-closed-count 50 --output data/nautilus_profit_hunt.json` mencari varian side/confidence/entry-metric terbaik dari ledger real tersimpan, tetap read-only dan tetap menolak promosi bila sample belum cukup.
24. `mexc-engine nautilus-paper-performance --ledger data/nautilus_paper_ledger.json --initial-equity 6.00000001 --output data/nautilus_paper_performance.json` menghitung equity curve, recent equity trend, drawdown, win-rate, profit factor, expectancy, dan consecutive loss dari ledger virtual.
25. `mexc-engine nautilus-paper-decision --symbol BTC_USDT --currency USDT --summary-only --volatility-filter --volatility-interval 1m --volatility-lookback 60 --min-avg-range-bps 5 --max-avg-range-bps 75 --min-latest-range-bps 3 --max-latest-range-bps 120` menambahkan gate volatility/regime dari candle REST MEXC real; check terbaru membaca regime `flat` dan menahan entry paper.
26. `mexc-engine nautilus-paper-loop --symbol BTC_USDT --currency USDT --iterations 1 --target-samples 100 --target-closed-trades 50 --save --paper-equity 6.00000001 --readiness-after --readiness-initial-equity 6.00000001 --volatility-filter ...` menyimpan sample real tambahan dan langsung merangkum readiness strict lokal dengan target sample plus priced closed virtual trade.

## Kapan Full Engine Runtime?

Setelah ini, langkah berikutnya bukan pull ulang besar-besaran. Langkah berikutnya adalah memilih bentuk integrasi:

1. execution report MEXC dipetakan ke object/report NautilusTrader sandbox. Done.
2. connect read-only Nautilus state cache ke strategy handoff lokal. Done.
3. persist state handoff loop dan paper-trading audit read-only. Done.
4. collect minimal paper sample window dan review edge/gate. Started untuk 20 sample awal; belum valid secara statistik.
5. tighten signal gates berdasarkan paper edge review. Started: strategy microstructure gate, strategy allowed-side policy, market gate, freshness gate, rolling quality gate, side quality governor, recovery window, paper quality gate, dan readiness score sudah masuk; global edge dan rolling edge masih negatif.
6. Quote-like top-of-book dibuat dari depth/top-book stream bila data ukuran real tersedia.
7. Candle/kline trend filter dan volatility/regime filter read-only ditambahkan sebelum membuka live path.
8. Paper execution ledger dibuat untuk virtual lifecycle/fill/slippage, sekarang dengan mode candle high/low opsional.
9. Paper performance report dibuat dan dipakai sebagai readiness gate; current result masih negatif.
10. Hummingbot tetap jadi referensi connector/ops, bukan target utama runtime.
11. submit/cancel order baru dibuka terakhir, setelah build lokal diganti ke explicit live execution phase dan tetap di belakang triple live lock.

Current next phase from local adapter readiness:

```text
collect-more-paper-samples-and-tighten-signal-quality-gates
```
