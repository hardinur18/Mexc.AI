# DCA Pyramid Strategy — Roadmap & Architecture

## Konsep

Multi-tier scaling-in strategy:
- **Radar account** — small probe entry per koin (1% equity, lev tinggi, TP jauh)
- **Utama 1, 2, ... N** — entries lebih besar saat radar drawdown ke level tertentu + technical level
- **Booster** — entry terakhir saat drawdown ekstrem

Snowball compounding: tier kemudian average down entry price aggregat; reversal even small captures profit dari semua tier sekaligus.

## Math Reality (Honest)

| Target | Daily compounding rate |
|---|---|
| $1k → $100k in 14d | +37.6%/day |
| $1k → $100k in 21d | +24.0%/day |
| $1k → $100k in 30d | +16.6%/day |

Achievable secara matematis dengan high leverage + volatility cocok, tapi **probability success per cycle rendah**. Top quant funds di crypto hit 5-15% bulanan dengan strategi systematic.

**Risk for 100x leverage DCA:**
- 1% price move against = 100% margin lost
- Cascade liq saat trend continuous (no reversal in window)
- Funding cost accumulates per posisi × waktu
- Black swan crash → all tiers wiped

**Mitigation absolute:**
1. Hard cap notional total ≤ N× equity (e.g., 5x → kalau equity $1k, max notional total $5k)
2. Per-trade margin ≤ 5% equity (yang kamu sebut)
3. Distance ke aggregate liq price ≥ X% (e.g., 15%)
4. Auto-hedge: total drawdown > Y% → force exit all tiers
5. Kill switch UI button

## SL+ (Profit Lock / Trailing TP) System

Bukan SL traditional (cut loss). Ini **trailing TP** — exit dengan profit dijaga, naik mengikuti peak.

### Mekanisme

```
Phase 1: Pre-activation
  Entry 100, Lev 100x
  Price 100-110: no SL+ yet (below activation threshold)

Phase 2: SL+ activated
  Price 120 (PnL +20% price = +2000% margin)
  → SL+ activated, lock minimum +25% margin
  → SL+ price set di 100.25 (entry + 0.25% price = +25% margin)

Phase 3: Ratchet up
  Price 130 (+3000% margin)
  → SL+ moved naik (trail behind by 50% margin = 0.5% price)
  → SL+ now at 129.5

  Price 140 (+4000% margin)
  → SL+ at 139.5

Phase 4: Trigger
  Price drops from 140 to 139.4
  → SL+ at 139.5 triggered
  → Close position at 139.4 (slippage)
  → Locked +39.4% price = +3940% margin
```

### Config Schema (Per Akun)

```jsonc
{
  "id": "main_1",
  "category": "utama",
  "strategy": {
    "sl_plus": {
      "enabled": true,
      "activation_pct_margin": 100,       // SL+ active saat PnL ≥ +100% margin (1% price di lev 100)
      "min_lock_pct_margin": 25,           // initial lock +25% margin (0.25% price)
      "trail_distance_pct_margin": 50,    // trail 50% margin di belakang peak
      "ratchet_step_pct_margin": 25       // setiap +25% margin, SL+ moves up
    }
  }
}
```

## TP Ladder (Bertahap 1, 2, 3)

```jsonc
{
  "strategy": {
    "take_profit_ladder": [
      {
        "level": 1,
        "pct_margin": 500,         // close di +500% margin (5% price)
        "close_pct_position": 33,  // close 33% posisi
        "reason": "Secure cost + small gain — RR 1:2.5"
      },
      {
        "level": 2,
        "pct_margin": 1500,
        "close_pct_position": 33,
        "reason": "RR 1:5 — main target"
      },
      {
        "level": 3,
        "pct_margin": 3000,
        "close_pct_position": 34,
        "reason": "Moonshot — RR 1:10+"
      }
    ]
  }
}
```

## DCA Trigger Conditions

```jsonc
{
  "id": "main_1",
  "strategy": {
    "role": "main",
    "tier": 1,
    "follow_radar": "radar_btc",       // ID radar yang di-follow
    "trigger": {
      "primary": {
        "type": "radar_drawdown_pct_margin",
        "threshold": -500                // trigger saat radar -500% margin
      },
      "confirmations": [
        {
          "type": "near_level",
          "level": "S1",                 // dekat pivot S1
          "tolerance_pct": 0.5
        },
        {
          "type": "rsi_oversold",        // optional indicator
          "period": 14,
          "threshold": 30
        }
      ],
      "min_confirmations": 1             // butuh minimal 1 konfirmasi selain primary
    },
    "entry_size": {
      "type": "pct_equity",
      "value": 5                          // 5% equity per entry
    },
    "leverage": 50,
    "side_follows_radar": true            // follow direction radar (LONG/SHORT)
  }
}
```

## Compounding Snowball Math (Real Numbers)

**Skenario LONG BTC:**

| Tier | Entry Price | Notional | Margin | Trigger |
|---|---|---|---|---|
| Radar | $75,000 | $100 (1% lev 100) | $1 | Manual entry |
| Main 1 | $73,500 (-2%) | $2,500 (5% equity × 50x) | $50 | Radar -500% margin + near S1 |
| Main 2 | $72,000 (-4%) | $2,500 | $50 | Radar -1000% margin + near S2 |
| Booster | $70,500 (-6%) | $5,000 (10% × 50x) | $100 | Radar -2000% margin + S3 |
| **TOTAL** | avg ~$72.5k | **$10,100 notional** | **$201 margin** | |

**Reversal scenario (price balik ke $75k):**
- Radar profit: $0 (back to entry)
- Main 1 profit: $2,500 × (75000-73500)/73500 = **+$51**
- Main 2 profit: $2,500 × (75000-72000)/72000 = **+$104**
- Booster profit: $5,000 × (75000-70500)/70500 = **+$319**
- **Total: +$474 di margin $201 = +236% on margin** (RR ~1:2.4)

**Continue ke moonshot $80k:**
- Radar: $100 × (80-75)/75 = +$6.67
- Main 1: +$222
- Main 2: +$278
- Booster: +$673
- **Total: +$1,180 di margin $201 = +587% on margin**

**Buruk scenario (continuous down ke $65k tanpa reversal):**
- Semua tier MARGIN HABIS pada level liq masing-masing
- Tergantung lev, bisa kehilangan total $201+ atau lebih kalau cross margin
- **Critical risk**: harus ada kill switch + hard liq distance enforcement

## Implementation Phases

### Phase 2a — Strategy Config Storage (DONE)
- ✅ `strategy` field di accounts.json schema
- ✅ Backend menerima + persist
- ✅ TypeScript types
- Tinggal: UI form untuk strategy editor

### Phase 2b — Live Monitor (Paper Mode)
- Backend background task: monitor radar PnL setiap 5s
- Compare dengan trigger threshold
- Compare dengan technical confirmations (Fib, S/R proximity)
- Log "would trigger" events
- Endpoint `/api/strategy/preview`
- Dashboard widget: "Pending Triggers"

### Phase 2c — Technical Analysis Layer
- Fibonacci retracement auto (✅ done — included in S/R)
- Volume profile (perlu volume data)
- Inflow/outflow on-chain (butuh provider eksternal — Coinglass, CryptoQuant, $20-200/month)
- Support/Resistance dari swing detection (perlu algo)
- RSI/MACD optional

### Phase 2d — Risk Engine
- Notional total cap per akun + global
- Per-trade margin cap 5% (hard rule)
- Liq distance minimum check
- Correlation cap (jangan all-in same direction same coin family)

### Phase 2e — Paper Execution
- Detected triggers → simulate entry
- Track simulated positions over time
- Show simulated P&L vs actual
- Validate strategy logic sebelum live

### Phase 2f — Live Execution (GATED)
- Requires: `STRATEGY_AUTO_EXEC_ENABLED=true` + `STRATEGY_EXEC_CONFIRM=<phrase>`
- Per-akun explicit toggle
- Kill switch button di UI
- Audit log semua executed orders

### Phase 2g — Backtest Mode
- Replay historical 7d/30d klines
- Simulate strategy execution
- Show: total P&L, max drawdown, hit rate, RR realized
- Tune params before going live

### Phase 2h — Alerts & Notifications
- Web Audio API: sound saat trigger
- Browser notification (with permission)
- Telegram bot integration (optional)

## On-Chain Inflow/Outflow Data

User wants real-time inflow/outflow. Options:

| Provider | Free Tier | Real-time | Coverage |
|---|---|---|---|
| Coinglass | Limited 50/day | 5min delay | All major exchanges |
| CryptoQuant | Limited | 15min delay | Top 30 coins |
| Glassnode | Trial only | EOD | BTC, ETH only |
| Etherscan | Free | Real-time | ETH only |
| Mempool.space | Free | Real-time | BTC mempool only |

**Pragmatic approach**: integrate Coinglass free tier first (5min delay OK untuk swing trading), add CryptoQuant later kalau butuh granular. Build abstraction layer supaya bisa swap provider.

## "Koin Bagus" Filter

Kriteria yang masuk akal untuk filter koin:
- **Market cap** ≥ $1B (data dari CoinGecko/CMC API)
- **24h volume** ≥ $100M (likuiditas)
- **Listed di MEXC futures** (sudah filter natural)
- **Tidak baru launch** (< 6 bulan = volatile irrational)
- **Funding rate stable** (extreme funding > 0.1% bisa indikator stress)

Implementation: nightly cron yang refresh whitelist dari CoinGecko, ban-list coin yang fail criteria.

## Validation Probability

User ingin "90%+ valid decisions". Realistic:
- **Pure technical analysis** (S/R, Fib, RSI): 50-60% baseline (slight edge over random)
- **Multi-confluence** (TA + on-chain + funding + orderbook): 65-75% achievable
- **90%+ secara berkelanjutan**: butuh quant research level — months of backtest + walk-forward + paper trade

Honest: tool akan kasih confluence score (0-100), bukan binary 90% claim. User decide threshold.

## My Recommendation

**Lakukan dalam urutan:**

1. **Stabilize current dashboard** (sudah hampir komplit)
2. **Phase 2a UI** (strategy editor di Settings) — config visible
3. **Phase 2b paper monitor** — see real triggers tanpa execute
4. **Phase 2c TA enrichment** — Fib done, volume + orderbook next
5. **Phase 2d risk engine** — enforce 5% cap, liq distance
6. **Phase 2g backtest** — validate dengan data historis
7. **Phase 2e paper exec sim** — refine logic
8. **Phase 2f live** — last, dengan extensive monitoring

Skip ke live execution sebelum 2g + 2e = recipe untuk lose modal cepat.

---

**Pertanyaan untuk kamu:**

1. Berapa modal nyata yang akan kamu pakai test sistem ini? (jangan sama yang $1k → $100k target)
2. Kamu udah punya backtest data atau intuisi pure?
3. On-chain inflow/outflow data — mau invest di Coinglass/CryptoQuant?
4. Kalau saya bangun Phase 2a-2c (config + paper monitor + TA), butuh waktu ~10 jam pengembangan. Mau lanjut sekarang atau next session?
