import { motion } from "motion/react";
import { Compass, TrendingUp, TrendingDown, Minus, Zap } from "lucide-react";
import type { MarketRegime, BtcAlignment, SpotFuturesBasis } from "@/types/position";

interface Props {
  regime: MarketRegime | null | undefined;
  btcAlignment?: BtcAlignment | null;
  basis?: SpotFuturesBasis | null;
}

const REGIME_TONE: Record<string, string> = {
  trending_up: "var(--color-success)",
  mild_up: "var(--color-success)",
  ranging: "var(--color-fg-muted)",
  mild_down: "var(--color-danger)",
  trending_down: "var(--color-danger)",
};

const VOL_TONE: Record<string, string> = {
  extreme: "var(--color-danger)",
  high: "var(--color-warning)",
  normal: "var(--color-accent)",
  compressed: "var(--color-fg-muted)",
};

export function MarketRegimeCard({ regime, btcAlignment, basis }: Props) {
  if (!regime) return null;
  const regimeTone = REGIME_TONE[regime.regime] || "var(--color-fg-muted)";
  const volTone = VOL_TONE[regime.volatility] || "var(--color-fg-muted)";
  const RegimeIcon =
    regime.regime.includes("up") ? TrendingUp : regime.regime.includes("down") ? TrendingDown : Minus;

  return (
    <div className="lift rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] overflow-hidden">
      <div className="px-3 py-2 flex items-center gap-2 border-b border-[var(--color-border)]/50">
        <Compass size={11} className="text-[var(--color-accent)]" />
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
          Market Regime
        </span>
        <span className="text-[9px] text-[var(--color-fg-faint)] ml-auto">
          trend × volatility × BTC alignment
        </span>
      </div>

      <div className="p-3 grid grid-cols-2 lg:grid-cols-4 gap-2.5">
        {/* Regime */}
        <Tile
          icon={<RegimeIcon size={11} />}
          label="Regime"
          value={regime.regime.replace("_", " ")}
          sub={`strength ${regime.trend_strength.toFixed(0)}%`}
          tone={regimeTone}
        />

        {/* Volatility */}
        <Tile
          icon={<Zap size={11} />}
          label="Volatility"
          value={regime.volatility}
          sub={regime.atr_pct != null ? `ATR ${regime.atr_pct.toFixed(2)}%` : "—"}
          tone={volTone}
        />

        {/* BTC alignment */}
        {btcAlignment ? (
          <Tile
            icon={btcAlignment.alignment === "aligned" ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
            label="BTC align"
            value={btcAlignment.alignment}
            sub={`corr ${btcAlignment.correlation_30bar?.toFixed(2) ?? "—"} · ${btcAlignment.btc_direction}`}
            tone={btcAlignment.alignment === "aligned" ? "var(--color-success)" : "var(--color-danger)"}
          />
        ) : (
          <Tile icon={<Minus size={11} />} label="BTC align" value="—" sub="self" tone="var(--color-fg-muted)" />
        )}

        {/* Basis */}
        {basis ? (
          <Tile
            icon={basis.basis_pct > 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
            label="Basis (perp vs spot)"
            value={`${basis.basis_pct > 0 ? "+" : ""}${basis.basis_pct.toFixed(3)}%`}
            sub={basis.bias.replace("_", " ")}
            tone={
              basis.bias.includes("contango_strong")
                ? "var(--color-warning)"
                : basis.bias.includes("backwardation_strong")
                  ? "var(--color-warning)"
                  : "var(--color-success)"
            }
          />
        ) : (
          <Tile icon={<Minus size={11} />} label="Basis" value="—" sub="n/a" tone="var(--color-fg-muted)" />
        )}
      </div>

      {/* BTC alignment penalty banner */}
      {btcAlignment && btcAlignment.penalty_pct > 0 && (
        <div className="px-3 pb-2.5">
          <motion.div
            initial={{ opacity: 0, y: -2 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-2 px-2 py-1.5 rounded ring-1 text-[10px]"
            style={{
              background: "color-mix(in oklch, var(--color-danger) 10%, transparent)",
              borderColor: "color-mix(in oklch, var(--color-danger) 30%, transparent)",
              color: "var(--color-danger)",
            }}
          >
            ⚠ BTC bergerak {btcAlignment.btc_direction} (
            {btcAlignment.btc_change_30bar_pct > 0 ? "+" : ""}
            {btcAlignment.btc_change_30bar_pct.toFixed(2)}% / 30h) — score penalty −
            {btcAlignment.penalty_pct} applied
          </motion.div>
        </div>
      )}
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
        <span style={{ color: tone }}>{icon}</span>
        {label}
      </div>
      <div
        className="text-[11px] font-bold uppercase tracking-wide truncate"
        style={{ color: tone }}
      >
        {value}
      </div>
      <div className="text-[8px] text-[var(--color-fg-faint)] mt-0.5 truncate">{sub}</div>
    </div>
  );
}
