# MEXC Futures Engine

Fondasi awal untuk robot trading MEXC Futures:

- signer REST resmi MEXC Futures
- client REST dasar
- risk guard sebelum order
- dry-run order flow
- live order terkunci default

## Status

Tahap ini sudah punya fondasi read-only real untuk MEXC Futures: REST public/private, WebSocket public/private, mapping awal Nautilus-style, execution reports, strategy stability gate, dan rekonsiliasi REST-vs-private-WS. Live order tetap terkunci dan belum diekspos di CLI.

## Setup

```bash
cd /Users/macbookair/Windsurf/mexc-futures-engine
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
```

Isi `.env` dari catatan lokal kamu, tapi jangan commit file `.env`.

Kalau DNS lokal mengarah ke halaman blokir, aktifkan DoH resolver di `.env`:

```bash
MEXC_USE_DOH_DNS=true
MEXC_DOH_URL=https://cloudflare-dns.com/dns-query
```

## Cek Public API

```bash
mexc-engine ping
mexc-engine contract BTC_USDT
mexc-engine nautilus-instrument BTC_USDT
mexc-engine nautilus-instruments --summary-only
mexc-engine nautilus-instruments --output data/nautilus_instruments.json
mexc-engine nautilus-adapter-manifest --output data/nautilus_adapter_manifest.json
mexc-engine nautilus-adapter-check --symbol BTC_USDT --currency USDT --summary-only
mexc-engine nautilus-adapter-check --symbol BTC_USDT --currency USDT --summary-only --output data/nautilus_adapter_check.json
mexc-engine nautilus-runtime-harness --symbol BTC_USDT --currency USDT --summary-only
mexc-engine nautilus-runtime-harness --symbol BTC_USDT --currency USDT --summary-only --output data/nautilus_runtime_harness.json
mexc-engine nautilus-runtime-wire --symbol BTC_USDT --summary-only
mexc-engine nautilus-runtime-wire --symbol BTC_USDT --summary-only --output data/nautilus_runtime_wire.json
mexc-engine nautilus-market-wire --symbol BTC_USDT --messages 5 --summary-only
mexc-engine nautilus-market-wire --symbol BTC_USDT --messages 5 --summary-only --output data/nautilus_market_wire.json
mexc-engine nautilus-execution-wire --symbol BTC_USDT --currency USDT --summary-only
mexc-engine nautilus-execution-wire --symbol BTC_USDT --currency USDT --summary-only --output data/nautilus_execution_wire.json
mexc-engine nautilus-state-handoff --symbol BTC_USDT --currency USDT --summary-only
mexc-engine nautilus-state-handoff --symbol BTC_USDT --currency USDT --summary-only --output data/nautilus_state_handoff.json
mexc-engine nautilus-paper-decision --symbol BTC_USDT --currency USDT --summary-only --save --paper-equity 6.00000001 --min-depth-imbalance 0.12 --max-spread-bps 2.5 --max-abs-funding-rate 0.0005 --max-market-age-seconds 60 --quality-gate-lookback 50
mexc-engine nautilus-paper-loop --symbol BTC_USDT --currency USDT --iterations 3 --interval 5 --target-samples 100 --target-closed-trades 50 --save --paper-equity 6.00000001 --readiness-after --readiness-initial-equity 6.00000001 --min-depth-imbalance 0.12 --max-spread-bps 2.5 --max-abs-funding-rate 0.0005 --max-market-age-seconds 60 --quality-gate-lookback 50
mexc-engine nautilus-paper-audit --symbol BTC_USDT --currency USDT --lookback 50 --min-samples 5 --edge-horizon-samples 3 --min-edge-evaluable 3 --min-edge-win-rate 0.55 --rolling-windows 5,10,25,50
mexc-engine nautilus-paper-edge --symbol BTC_USDT --currency USDT --lookback 50 --horizon-samples 3 --price-simulation candle-high-low --candle-interval 1m --candle-lookback 240
mexc-engine nautilus-paper-ledger --symbol BTC_USDT --currency USDT --lookback 100 --horizon-samples 3 --include-probes --price-simulation candle-high-low --candle-interval 1m --candle-lookback 240 --output data/nautilus_paper_ledger.json
mexc-engine nautilus-paper-performance --ledger data/nautilus_paper_ledger.json --initial-equity 6.00000001 --output data/nautilus_paper_performance.json
mexc-engine nautilus-profit-hunt --symbol BTC_USDT --currency USDT --lookback 100 --horizon-samples 3 --initial-equity 6.00000001 --confidence-thresholds 0,0.65,0.7,0.75,0.8 --min-depth-imbalance-sweep 0.12,0.25,0.35,0.5,0.7 --max-spread-bps-sweep 0.02,0.05,0.1 --max-abs-funding-rate-sweep 0.00005,0.0001,0.0005 --min-closed-count 50 --output data/nautilus_profit_hunt.json
mexc-engine klines BTC_USDT --interval 1m --lookback 60 --summary-only
mexc-engine pairs
mexc-engine pairs --api-tradable-only
mexc-engine dns-check
mexc-engine network-check
mexc-engine readiness --symbol BTC_USDT --currency USDT --lookback 100 --target-samples 100 --rolling-windows 5,10,25,50 --price-simulation candle-high-low --candle-interval 1m --candle-lookback 240 --performance-initial-equity 6.00000001 --performance-horizon-samples 3
```

Kalau command mengembalikan HTML atau gagal SSL dari jaringan lokal, kemungkinan endpoint MEXC API diblokir ISP/DNS. Untuk runtime live, jalankan dari VPS atau jaringan yang bisa mengakses `https://api.mexc.com`.

## Cek Market Data REST

Semua command di bawah memukul endpoint MEXC asli.

```bash
mexc-engine ticker BTC_USDT
mexc-engine depth BTC_USDT --limit 20
mexc-engine index-price BTC_USDT
mexc-engine fair-price BTC_USDT
mexc-engine funding-rate BTC_USDT
```

## Cek Private API Read-Only

```bash
mexc-engine asset USDT
mexc-engine assets
mexc-engine positions BTC_USDT
mexc-engine open-orders
mexc-engine history-orders --symbol BTC_USDT
mexc-engine reconcile --symbol BTC_USDT --currency USDT --summary-only --save
mexc-engine execution-reports --symbol BTC_USDT --currency USDT --summary-only
mexc-engine execution-reports --symbol BTC_USDT --currency USDT --output data/execution_reports.json
mexc-engine reconcile-engine --symbol BTC_USDT --currency USDT --summary-only
mexc-engine reconcile-engine --symbol BTC_USDT --currency USDT --summary-only --output data/reconciliation_engine.json
mexc-engine store stats
mexc-engine store latest --limit 5
```

## Cek WebSocket

```bash
mexc-engine ws-public ticker BTC_USDT --messages 3
mexc-engine ws-public deal BTC_USDT --messages 3
mexc-engine ws-public depth BTC_USDT --messages 3
mexc-engine ws-private --messages 3
mexc-engine ws-private-bridge --messages 5
mexc-engine ws-bridge ticker BTC_USDT --messages 3
mexc-engine ws-bridge deal BTC_USDT --messages 3
mexc-engine ws-bridge depth BTC_USDT --messages 3
```

WebSocket private hanya login dan membaca stream private. Tidak ada endpoint order di WebSocket command ini.

`ws-bridge` membaca WebSocket public real dan mengubah pesan MEXC menjadi spec event netral untuk adapter Nautilus: `QuoteTick`, `TradeTick`, dan `OrderBookDeltas`.

## Reconciliation Engine Read-Only

Tidak mengirim order. Command ini menggabungkan snapshot REST private, execution report bundle, dan private WebSocket ACK/update stream untuk memastikan state akun bisa direkonsiliasi sebelum jalur live pernah dibuka.

```bash
mexc-engine reconcile-engine --symbol BTC_USDT --currency USDT --summary-only
```

Output `ok=true` berarti endpoint REST private sukses dan private WebSocket minimal berhasil login + `personal.filter`. Kalau akun idle, warning ACK-only itu normal: tidak ada delta order/posisi/fill karena memang tidak ada aktivitas stream selama window baca.

## Nautilus Adapter Check Read-Only

Tidak mengirim order dan tidak menginstall runtime NautilusTrader. Command ini mengecek boundary adapter MEXC Futures yang sudah kita punya: upstream Nautilus reference, instrument provider, public market data bridge, private REST execution reports, private WS stream, dan reconciliation.

```bash
mexc-engine nautilus-adapter-manifest --output data/nautilus_adapter_manifest.json
```

```bash
mexc-engine nautilus-adapter-check --symbol BTC_USDT --currency USDT --summary-only
```

`nautilus-adapter-manifest` adalah manifest package boundary statis: modul, class, capability, policy runtime, dan command verifikasi. Tidak butuh network.

Output `readyForReadOnlyRuntime=true` berarti local adapter bridge sudah cukup lengkap untuk fase packaging ke NautilusTrader runtime. Output `readyForLiveRuntime=false` tetap benar, karena submit/cancel live sengaja belum tersedia.

## Nautilus Runtime Harness Read-Only

Tidak mengirim order. Command ini mengecek apakah package boundary MEXC sudah siap dipasang ke harness runtime Nautilus read-only: manifest, real adapter check, file template/reference Nautilus, probe import runtime, dan method boundary.

```bash
mexc-engine nautilus-runtime-harness --symbol BTC_USDT --currency USDT --summary-only
```

Output `readyForRuntimeHarness=true` berarti boundary lokal sudah siap. Output `readyForNautilusRuntimeImport=false` masih normal saat NautilusTrader upstream belum dibuild/diinstall di sandbox lokal.

Sandbox runtime sudah bisa dibuat lokal tanpa menyentuh engine utama:

```bash
/Users/macbookair/miniforge3/bin/python3.13 -m venv .venv-nautilus
.venv-nautilus/bin/python -m pip install -U nautilus_trader --pre --index-url=https://packages.nautechsystems.io/simple --extra-index-url=https://pypi.org/simple
```

Setelah sandbox aktif, `nautilus-runtime-harness` membaca `.venv-nautilus` dan output `readyForNautilusRuntimeImport=true`. Source checkout di `upstream/nautilus_trader` tetap belum dibuild; runtime yang dipakai untuk import adalah wheel sandbox.

## Nautilus Runtime Wire Read-Only

Tidak mengirim order. Command ini mengambil instrument spec MEXC real lalu membangun object `CryptoPerpetual` Nautilus asli di `.venv-nautilus`.

```bash
mexc-engine nautilus-runtime-wire --symbol BTC_USDT --summary-only
```

Output `readyForSandboxedNautilusRuntimeReadOnly=true` berarti contract MEXC sudah berhasil melewati boundary provider dan diterima oleh model instrument Nautilus runtime.

## Nautilus Market Data Wire Read-Only

Tidak mengirim order. Command ini mengambil WebSocket market data MEXC real dan membangun object data Nautilus asli di `.venv-nautilus`.

```bash
mexc-engine nautilus-market-wire --symbol BTC_USDT --messages 5 --summary-only
```

Saat ini `TradeTick` dan `OrderBookDeltas` berhasil dibuat. `QuoteTick` dari ticker sengaja tidak dibuat karena MEXC ticker tidak menyediakan bid/ask size, sedangkan Nautilus `QuoteTick` membutuhkan bid/ask price dan size. Tidak ada nilai palsu.

## Nautilus Execution Wire Read-Only

Tidak mengirim order. Command ini mengambil private REST execution reports MEXC real lalu membangun object runtime Nautilus asli di `.venv-nautilus`: `AccountState`, `OrderStatusReport`, `FillReport`, dan `PositionStatusReport` kalau posisi sedang terbuka.

```bash
mexc-engine nautilus-execution-wire --symbol BTC_USDT --currency USDT --summary-only
```

Output `readyForSandboxedNautilusExecutionReadOnly=true` berarti laporan akun/order/fill MEXC sudah diterima oleh model execution Nautilus runtime. Kalau MEXC mengirim balance dengan dust kecil sehingga `equity - locked != free`, command menormalisasi `total` ke `locked + free` hanya untuk memenuhi invariant `AccountBalance` Nautilus dan mencatat adjustment di output.

## Nautilus State Handoff Read-Only

Tidak mengirim order. Command ini menggabungkan instrument wire, market data wire, execution wire, dan strategy preview real menjadi satu state cache snapshot untuk strategi lokal.

```bash
mexc-engine nautilus-state-handoff --symbol BTC_USDT --currency USDT --summary-only
```

Output `readyForStrategyReadOnly=true` berarti strategi lokal sudah punya context terpadu: instrument `CryptoPerpetual`, depth-derived `QuoteTick` dengan size asli, `TradeTick`, `OrderBookDeltas`, `AccountState`, order/fill reports, balance, open position/order count, dan preview sinyal. `safeToOpenNewPositionPreflight=true` hanya berarti boleh lanjut ke preflight read-only jika tidak ada posisi atau order aktif secara global di akun; live order tetap tidak tersedia.

## Nautilus Paper Audit Read-Only

Tidak mengirim order. Command ini mengambil state handoff real, menghitung keputusan virtual `paper-open-long`, `paper-open-short`, atau `hold`, lalu bisa menyimpan sample ke SQLite untuk diaudit.

```bash
mexc-engine nautilus-paper-decision --symbol BTC_USDT --currency USDT --summary-only --save --paper-equity 6.00000001 --min-depth-imbalance 0.12 --max-spread-bps 2.5 --max-abs-funding-rate 0.0005 --max-market-age-seconds 60 --quality-gate-lookback 50 --quality-max-sample-age-seconds 86400 --quality-rolling-windows 5,10,25,50
mexc-engine nautilus-paper-decision --symbol BTC_USDT --currency USDT --summary-only --save --paper-equity 6.00000001 --trend-filter --trend-interval 1m --trend-lookback 60 --trend-short-period 5 --trend-long-period 20
mexc-engine nautilus-paper-decision --symbol BTC_USDT --currency USDT --summary-only --save --paper-equity 6.00000001 --volatility-filter --volatility-interval 1m --volatility-lookback 60 --min-avg-range-bps 5 --max-avg-range-bps 75 --min-latest-range-bps 3 --max-latest-range-bps 120
mexc-engine nautilus-paper-loop --symbol BTC_USDT --currency USDT --iterations 3 --interval 5 --target-samples 100 --target-closed-trades 50 --save --paper-equity 6.00000001 --readiness-after --readiness-initial-equity 6.00000001 --volatility-filter --volatility-interval 1m --volatility-lookback 60 --min-avg-range-bps 5 --max-avg-range-bps 75 --min-latest-range-bps 3 --max-latest-range-bps 120 --min-depth-imbalance 0.12 --max-spread-bps 2.5 --max-abs-funding-rate 0.0005 --max-market-age-seconds 60 --quality-gate-lookback 50 --quality-max-sample-age-seconds 3600 --quality-rolling-windows 5,10,25,50
mexc-engine nautilus-paper-audit --symbol BTC_USDT --currency USDT --lookback 50 --min-samples 5 --edge-horizon-samples 3 --min-edge-evaluable 3 --min-edge-win-rate 0.55 --min-side-edge-evaluable 2 --min-side-edge-win-rate 0.55 --max-sample-age-seconds 86400 --rolling-windows 5,10,25,50
mexc-engine nautilus-paper-edge --symbol BTC_USDT --currency USDT --lookback 50 --horizon-samples 3
```

`paper-decision` dan `paper-loop` hanya mencatat keputusan virtual. Field `liveOrderSubmitted=false` harus selalu tetap begitu. `--paper-equity` memberi modal simulasi lokal untuk margin paper sehingga saldo live kecil tidak membunuh koleksi sample; alasan preflight live-balance tetap dicatat sebagai warning dan tidak pernah membuka jalur order live. `paper-loop` target-aware terhadap sample valid dan closed virtual trade melalui `--target-samples` plus `--target-closed-trades`; target collection wajib memakai `--save` agar progress lokal benar-benar maju. Keputusan virtual sekarang punya gate tambahan dari metrics market real: depth imbalance top-10 harus searah side, spread bps harus di bawah ambang, funding absolut harus di bawah ambang, dan snapshot TradeTick/OrderBookDeltas harus masih fresh bila `--max-market-age-seconds` aktif. Metric wajib yang hilang menjadi blocker, bukan warning.

Kalau `--quality-gate-lookback` aktif, `paper-decision` dan `paper-loop` juga membaca audit historis sebelum menyimpan entry baru. `paperQualityGovernor` sekarang memakai evaluasi `candle-high-low` tanpa fallback, sama seperti readiness strict. Governor akan mengubah would-open menjadi `hold` bila side tersebut sudah punya cukup sample tetapi win-rate atau rough PnL masih buruk. Kandidat yang dipause disimpan sebagai `paperProbe` eksploratif untuk recovery stats, tetapi `wouldOpen=false`, `virtualOrder=null`, dan `liveOrderSubmitted=false` tetap dijaga. Side yang dipause hanya boleh recovery untuk paper entry baru kalau window terbaru melewati win-rate minimum dan rough PnL positif.

`paper-audit` membaca event `nautilus_paper_decision` dari SQLite, mengurutkan sample berdasarkan timestamp/event id, lalu menghitung jumlah would-open/hold, blocker, freshness sample, rolling windows, dan `paperQualityGate`. Quality gate ini tetap menolak kandidat live kalau evaluable edge, win-rate, rough PnL, rolling window, atau side quality sample belum cukup.

`paper-audit` dan `paper-edge` default ke `candle-high-low` dengan 240 candle REST MEXC 1m dan tanpa fallback sample-close. `paper-edge` membandingkan entry virtual dengan market snapshot dalam horizon sample yang dipilih, lalu mengecek high/low candle untuk stop-loss/take-profit virtual. Kalau stop dan take-profit tersentuh di candle yang sama, policy konservatif memilih stop-loss dulu dan menandai `intraCandleAmbiguous=true`. Ini tetap review kualitas sinyal, bukan backtest penuh dan bukan order live.

`paper-ledger` membentuk ledger read-only dari sample tersimpan: `NEW -> FILLED -> EXPIRED/STOPPED/TAKE_PROFIT` untuk entry yang punya horizon selesai, atau `NEW -> OPEN` untuk probe/entry yang belum punya future sample cukup. Ledger sekarang bisa memakai simulasi `sample-close` atau `candle-high-low`; keduanya selalu `liveOrderSubmitted=false`.

`paper-performance` membaca ledger virtual dan menghitung equity curve, recent equity trend, drawdown, win-rate, profit factor, expectancy, consecutive loss, serta jumlah posisi virtual open/closed. Order closed yang belum punya exit/PnL terharga tidak dihitung sebagai closed trade valid; laporan menampilkan `unpricedClosedCount`/`skippedClosedCount` agar readiness tidak bisa naik dari data yang belum bisa dievaluasi. Laporan ini tetap read-only dan tidak memakai endpoint order.

`profit-hunt` membaca ledger strict dari sample real tersimpan, lalu ranking varian lokal seperti `all`, `open-long`, `open-short`, beberapa confidence threshold, dan optional entry metric sweep dari `entryMetrics` ledger (`depthImbalanceTop10`, `spreadBps`, `fundingRate`, `avgRangeBps`, `latestRangeBps`). Kandidat hanya layak promosi kalau closed count cukup, equity akhir di atas initial, expectancy positif, profit factor/win-rate/drawdown lolos, tidak ada open/unpriced/skipped order, dan recent equity trend positif. Ini alat seleksi paper, bukan izin live.

Snapshot lokal terbaru dari ledger `data/nautilus_paper_ledger.json`:

- 8 virtual entry, 8 closed, 0 open; 7 priced/evaluable dan 1 unpriced/skipped.
- price simulation: `candle-high-low` dengan 240 candle REST MEXC 1m dan `priceSimulationFallback=null`.
- win-rate closed paper: `0.5714285714285714`.
- profit factor: `0.6014788157640018`.
- expectancy: `-0.002832659428571428571428571429` USDT/trade.
- equity paper dari `6.00000001` turun ke `5.980171394` USDT.
- max drawdown paper: `0.022693358` USDT (`0.3780%`).
- `liveOrderSubmitted=false`.

Artinya equity belum naik stabil dan paper edge belum layak untuk live.

`--trend-filter` pada paper decision/loop menarik candle REST MEXC, menghitung EMA pendek/panjang, lalu memblok long saat trend tidak bullish dan short saat trend tidak bearish. Field `trendFilter` di sample menyimpan candle count, EMA, range bps, freshness, dan blocker.

`--volatility-filter` pada paper decision/loop menarik candle REST MEXC, menghitung average range bps dan latest range bps, lalu memblok paper entry jika range terlalu flat atau terlalu volatile sesuai threshold yang diberikan. Flag threshold `--min-avg-range-bps`, `--max-avg-range-bps`, `--min-latest-range-bps`, dan `--max-latest-range-bps` juga otomatis mengaktifkan filter. Sample menyimpan `volatilityFilter` dan `regimeFilter`; keduanya tetap read-only dan `liveOrderSubmitted=false`.

Real check terbaru dengan 60 candle MEXC 1m membaca regime `flat` (`avgRangeBps=4.313322450883798774309129947`) dan menahan paper decision karena berada di bawah floor `5.0` bps. Sample tersimpan naik menjadi `22 / 100`; tidak ada virtual order baru yang dibuat.

Profit hunt dengan entry metric sweep menemukan kandidat riset terbaik `open-short` pada `minDepthImbalanceTop10=0.12`, `maxSpreadBps=0.02`, dan `maxAbsFundingRate=0.00005`: 5 priced closed trade, win-rate `0.8`, profit factor `1.3187502704535838`, dan net PnL `+0.007233514` USDT. Gate strict tetap menolak promosi karena closed count `5` masih di bawah target `50`.

## Real Smoke Test

Tidak ada mock. Command ini hanya memakai endpoint MEXC asli:

```bash
mexc-engine smoke-readonly --symbol BTC_USDT --currency USDT
```

## Dry-Run Order

Command ini mengambil contract detail/account read-only, mengisi contract size untuk risk guard, lalu mengembalikan payload validasi. Command ini tidak pernah memanggil endpoint create order; output harus membawa `dryRun=true`, `wouldSubmitLive=false`, dan `liveOrderSubmitted=false`.

```bash
mexc-engine dry-run-order \
  --symbol BTC_USDT \
  --side open-long \
  --order-type limit \
  --price 60000 \
  --vol 1 \
  --contract-size 0.0001 \
  --leverage 2 \
  --open-type isolated \
  --stop-loss-price 59000
```

## Paper Readiness

`readiness` menggabungkan `audit-safety` termasuk private read-only auth probe, sample paper tersimpan, freshness, rolling windows, global edge, policy side, dan paper performance menjadi satu skor lokal. Ini bukan izin live; `readyForLive` tetap `false`.

```bash
mexc-engine readiness --symbol BTC_USDT --currency USDT --lookback 100 --target-samples 100 --min-samples 5 --edge-horizon-samples 3 --min-edge-evaluable 3 --min-edge-win-rate 0.55 --min-side-edge-evaluable 2 --min-side-edge-win-rate 0.55 --max-sample-age-seconds 3600 --rolling-windows 5,10,25,50 --price-simulation candle-high-low --candle-interval 1m --candle-lookback 240 --performance-initial-equity 6.00000001 --performance-horizon-samples 3 --output data/paper_readiness.json
```

`localPaperReadinessPercent` naik ketika safety bersih, live lock aktif, sample fresh/cukup, edge rolling positif, dan performance equity/profit-factor/expectancy lolos. Jika sample masih sedikit, PnL rolling negatif, atau performance negatif, report memberi `nextActions` dan tetap menolak `readyForLocalPaperStrategy`.

Readiness memakai profil `strict-local-paper`: target sample efektif minimal `100`, priced closed virtual trade minimal `50`, horizon evaluasi minimal 3 sample, freshness maksimal 3600 detik, win-rate minimal `0.55`, profit factor minimal `1.25`, recent equity trend 5 trade harus positif, max drawdown pct maksimal `0.02`, tidak boleh ada paper order open, rolling window wajib `5,10,25,50`, dan strict readiness selalu memakai `candle-high-low` tanpa fallback sample-close. `collectionProgress` menunjukkan sample tersisa, closed trade tersisa, open virtual order, unpriced/skipped order, latest sample, dan blocker terbesar. Live mutation client tetap disabled di kode lokal walaupun flag live diset.

## Preflight Order Real-Only

Tidak mengirim order. Ini mengambil contract detail, asset, positions, dan open orders dari MEXC asli lalu menjalankan risk guard lokal.

```bash
mexc-engine preflight-order \
  --symbol BTC_USDT \
  --side open-long \
  --order-type limit \
  --price 79000 \
  --vol 1 \
  --leverage 2 \
  --open-type isolated \
  --stop-loss-price 78000 \
  --save
```

## Strategy Sandbox Read-Only

Tidak mengirim order. Membaca ticker/depth/funding real, menghitung sinyal mikro konservatif, dan menjalankan preflight jika ada candidate order.

```bash
mexc-engine strategy-signal --symbol BTC_USDT --leverage 2 --max-notional 10 --save
mexc-engine strategy-run --symbol BTC_USDT --leverage 2 --max-notional 10 --iterations 3 --interval 5 --save
mexc-engine strategy-evaluate --symbol BTC_USDT --lookback 5 --min-consensus 3 --min-confidence 0.65
```

`strategy-evaluate` membaca event `strategy_signal` yang sudah tersimpan di SQLite. Output `actionable=true` hanya kalau sinyal terbaru bukan hold, beberapa sinyal terakhir searah, confidence melewati ambang, dan semua preflight real lolos.

Micro-signal sekarang memakai gate yang lebih ketat sebelum membuat candidate: top-10 depth imbalance minimal `0.12`, fair/index premium harus searah, spread maksimal `2.5` bps, funding absolut maksimal `0.0005`, dan estimasi take-profit bersih setelah spread + round-trip taker fee harus tetap positif melewati gate.

Side strategi bisa dibatasi dari `.env` lewat `MEXC_STRATEGY_ALLOWED_SIDES`. Untuk fase sample terbaru, long sedang dipause dari hulu dengan `MEXC_STRATEGY_ALLOWED_SIDES=open-short` karena audit paper masih menunjukkan edge long negatif.

`paperQualityGate.strategyPolicyQualityGate` menilai side yang sedang diizinkan oleh policy strategi. Ini bisa berbeda dari global quality gate: global tetap membaca semua histori, sedangkan policy gate membaca side aktif seperti `open-short` saja.

## Safety Status

```bash
mexc-engine safety-status
mexc-engine kill-switch status
mexc-engine kill-switch on
mexc-engine kill-switch off
mexc-engine audit-safety
```

## Safety Rules Awal

- `MEXC_LIVE_TRADING_ENABLED=false` secara default.
- Live mutation low-level Python client sekarang butuh triple lock: `MEXC_LIVE_TRADING_ENABLED=true`, `MEXC_LIVE_CONFIRM=I_UNDERSTAND_LIVE_MEXC_FUTURES_RISK`, dan `MEXC_LIVE_MUTATION_PHASE_ENABLED=true`.
- `MEXC_LIVE_MUTATION_PHASE_ENABLED=false` selama fase local paper; jangan aktifkan sampai readiness, rolling edge, dan paper performance positif.
- Live order belum disediakan di CLI.
- Kill switch file `.kill-switch` akan memblokir order.
- Stop loss wajib kalau `MEXC_REQUIRE_STOP_LOSS=true`.
- Symbol, leverage, volume, dan notional dibatasi dari `.env`.
- Secret tidak ditaruh di repository.

## Roadmap

1. REST read-only + dry-run order. Done.
2. WebSocket public/private read-only bridge. Done.
3. Private REST execution reports. Done.
4. Reconciliation REST/WebSocket. Done for read-only idle/startup state.
5. Strategy sandbox/stability gate. Done read-only.
6. NautilusTrader adapter readiness manifest. Done read-only.
7. NautilusTrader adapter package boundary. Done read-only.
8. NautilusTrader runtime harness read-only. Done.
9. Sandboxed Nautilus runtime install/import read-only. Done.
10. Wire instrument boundary into sandboxed Nautilus runtime read-only. Done.
11. Map market data events into sandboxed Nautilus runtime read-only. Done for `TradeTick` and `OrderBookDeltas`.
12. Map execution reports into sandboxed Nautilus runtime read-only. Done.
13. State handoff + paper trading audit with market/edge/freshness/rolling quality gates. Done read-only; still collecting edge-positive samples.
14. Paper ledger and performance equity report. Done read-only; current paper performance is negative.
15. Private order submit/cancel CLI with explicit live phase workflow. Later, after adapter reconciliation and paper edge stay stable.

Lihat juga [docs/ENGINE_PULL_PLAN.md](docs/ENGINE_PULL_PLAN.md).
Network policy: [docs/NETWORK_POLICY.md](docs/NETWORK_POLICY.md).
Nautilus adapter audit: [docs/NAUTILUS_MEXC_ADAPTER_AUDIT.md](docs/NAUTILUS_MEXC_ADAPTER_AUDIT.md).
Open source references: [docs/OPEN_SOURCE_ENGINE_REFERENCES.md](docs/OPEN_SOURCE_ENGINE_REFERENCES.md).
Hummingbot reference audit: [docs/HUMMINGBOT_REFERENCE_AUDIT.md](docs/HUMMINGBOT_REFERENCE_AUDIT.md).
