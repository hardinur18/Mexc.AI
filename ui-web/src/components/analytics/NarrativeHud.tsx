import { motion } from "motion/react";
import { Smile, Frown, TrendingUp, TrendingDown, Bitcoin, BarChart3, Globe } from "lucide-react";
import {
  useFearGreed,
  useCoinGeckoGlobal,
  useDeribitOptions,
  useBinanceFunding,
} from "@/hooks/useSnapshot";
import { fmt, fmtPct } from "@/lib/format";

/**
 * Global market narrative HUD — Fear & Greed + CoinGecko (real BTC dom) + Deribit options + Binance.
 */
export function NarrativeHud() {
  const { data: fng } = useFearGreed();
  const { data: cg } = useCoinGeckoGlobal();
  const { data: deribitBtc } = useDeribitOptions("BTC");
  const { data: deribitEth } = useDeribitOptions("ETH");
  const { data: binBtc } = useBinanceFunding("BTCUSDT");

  return (
    <div className="lift rounded-[var(--radius-md)] inner-card overflow-hidden">
      <div className="px-3 py-2 flex items-center gap-2 border-b border-[var(--color-border)]/50">
        <Globe size={11} className="text-[var(--color-accent)]" />
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
          Global Narrative
        </span>
        <span className="text-[9px] text-[var(--color-fg-faint)] ml-auto">
          F&G · CoinGecko · Deribit · Binance
        </span>
      </div>

      <div className="p-4 grid grid-cols-2 md:grid-cols-4 gap-2">
        {/* Fear & Greed */}
        {fng?.current != null && <FngTile fng={fng} />}

        {/* Real BTC Dominance */}
        {cg?.btc_dominance_pct != null && (
          <Tile
            icon={<Bitcoin size={11} className="text-[var(--color-warning)]" />}
            label="BTC Dom (real)"
            value={`${cg.btc_dominance_pct.toFixed(2)}%`}
            sub={
              cg.market_cap_change_24h_usd_pct != null
                ? `mcap ${fmtPct(cg.market_cap_change_24h_usd_pct)}`
                : ""
            }
            tone="var(--color-warning)"
          />
        )}

        {/* Deribit BTC put/call */}
        {deribitBtc?.put_call_oi_ratio != null && (
          <Tile
            icon={
              deribitBtc.interpretation === "bullish_sentiment" ? (
                <TrendingUp size={11} className="text-[var(--color-success)]" />
              ) : deribitBtc.interpretation === "bearish_sentiment" ? (
                <TrendingDown size={11} className="text-[var(--color-danger)]" />
              ) : (
                <BarChart3 size={11} className="text-[var(--color-fg-muted)]" />
              )
            }
            label="BTC P/C"
            value={deribitBtc.put_call_oi_ratio.toFixed(2)}
            sub={
              deribitBtc.max_pain_strike
                ? `max pain ${fmt(deribitBtc.max_pain_strike, 0)}`
                : "—"
            }
            tone={
              deribitBtc.interpretation === "bullish_sentiment"
                ? "var(--color-success)"
                : deribitBtc.interpretation === "bearish_sentiment"
                  ? "var(--color-danger)"
                  : "var(--color-fg-muted)"
            }
          />
        )}

        {/* Binance BTC funding + LSR */}
        {binBtc?.funding_rate != null && (
          <Tile
            icon={<BarChart3 size={11} className="text-[var(--color-accent)]" />}
            label="BTC Binance"
            value={fmtPct(binBtc.funding_rate * 100)}
            sub={
              binBtc.long_short_ratio != null
                ? `LSR ${binBtc.long_short_ratio.toFixed(2)}`
                : "—"
            }
            tone={
              (binBtc.long_short_ratio ?? 1) > 1.5
                ? "var(--color-warning)"
                : (binBtc.long_short_ratio ?? 1) < 0.7
                  ? "var(--color-warning)"
                  : "var(--color-success)"
            }
          />
        )}
      </div>

      {/* ETH options secondary line */}
      {deribitEth?.put_call_oi_ratio != null && (
        <div className="px-3 pb-2.5 text-[9px] text-[var(--color-fg-muted)] flex items-center gap-3">
          <span>
            ETH P/C OI{" "}
            <span className="num font-bold text-[var(--color-fg)]">
              {deribitEth.put_call_oi_ratio.toFixed(2)}
            </span>
          </span>
          {deribitEth.max_pain_strike != null && (
            <span>
              ETH max pain{" "}
              <span className="num font-bold text-[var(--color-fg)]">
                ${fmt(deribitEth.max_pain_strike, 0)}
              </span>
            </span>
          )}
          {cg?.eth_dominance_pct != null && (
            <span>
              ETH dom{" "}
              <span className="num font-bold text-[var(--color-fg)]">
                {cg.eth_dominance_pct.toFixed(2)}%
              </span>
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function FngTile({ fng }: { fng: import("@/types/position").FearGreed }) {
  const v = fng.current ?? 0;
  const tone =
    v < 25
      ? "var(--color-success)"
      : v < 50
        ? "var(--color-warning)"
        : v < 75
          ? "oklch(75% 0.16 50)"
          : "var(--color-danger)";
  const Icon = v >= 60 ? Smile : v <= 30 ? Frown : BarChart3;

  // Semi-circle gauge: 180° arc from -90° (left/0) to +90° (right/100)
  // Needle rotates from -90 (val=0) → 0 (val=50) → +90 (val=100)
  const needleDeg = -90 + (v / 100) * 180;

  return (
    <div className="rounded-[var(--radius-sm)] bg-white/[0.03] px-2.5 py-2">
      <div className="flex items-center gap-1.5 text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1">
        <Icon size={11} style={{ color: tone }} />
        Fear & Greed
      </div>
      <div className="flex items-center gap-2">
        {/* Semi-circle gauge */}
        <div className="relative" style={{ width: 58, height: 32 }}>
          <svg width="58" height="36" viewBox="0 0 60 32" className="block">
            {/* Arc segments — green, yellow, orange, red */}
            {[
              { from: 180, to: 135, color: "var(--color-success)" },     // 0-25 fear
              { from: 135, to: 90, color: "var(--color-warning)" },      // 25-50
              { from: 90, to: 45, color: "oklch(75% 0.16 50)" },         // 50-75
              { from: 45, to: 0, color: "var(--color-danger)" },         // 75-100 greed
            ].map((seg, i) => {
              const r = 24;
              const cx = 30;
              const cy = 28;
              const fromRad = (seg.from * Math.PI) / 180;
              const toRad = (seg.to * Math.PI) / 180;
              const x1 = cx + r * Math.cos(fromRad);
              const y1 = cy - r * Math.sin(fromRad);
              const x2 = cx + r * Math.cos(toRad);
              const y2 = cy - r * Math.sin(toRad);
              return (
                <path
                  key={i}
                  d={`M ${x1} ${y1} A ${r} ${r} 0 0 1 ${x2} ${y2}`}
                  fill="none"
                  stroke={seg.color}
                  strokeWidth="4"
                  strokeLinecap="butt"
                  opacity="0.85"
                />
              );
            })}
            {/* Needle */}
            <motion.line
              x1="30"
              y1="28"
              x2="30"
              y2="8"
              stroke="white"
              strokeWidth="1.5"
              strokeLinecap="round"
              initial={false}
              animate={{ rotate: needleDeg }}
              style={{ originX: "30px", originY: "28px" }}
              transition={{ type: "spring", stiffness: 90, damping: 14 }}
            />
            <circle cx="30" cy="28" r="2" fill="white" />
          </svg>
        </div>
        <div className="leading-tight">
          <motion.div
            key={v}
            initial={{ scale: 0.85, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.3 }}
            className="text-base font-bold num leading-none"
            style={{ color: tone }}
          >
            {v}
          </motion.div>
          <div className="text-[8px] uppercase tracking-wider mt-0.5" style={{ color: tone }}>
            {fng.classification ?? "—"}
          </div>
        </div>
      </div>
    </div>
  );
}

function Tile({
  icon,
  label,
  value,
  sub,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
  tone: string;
}) {
  return (
    <div className="rounded-[var(--radius-sm)] bg-white/[0.03] px-2.5 py-2">
      <div className="flex items-center gap-1.5 text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1">
        {icon}
        {label}
      </div>
      <div className="text-base font-bold num leading-none" style={{ color: tone }}>
        {value}
      </div>
      <div className="text-[8px] text-[var(--color-fg-faint)] mt-1 truncate">{sub}</div>
    </div>
  );
}
