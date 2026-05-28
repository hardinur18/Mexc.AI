import { motion } from "motion/react";
import { TrendingUp, TrendingDown, Target, BarChart2, Award } from "lucide-react";
import { usePerformance } from "@/hooks/useSnapshot";
import { fmt, fmtSign } from "@/lib/format";

export function PerformanceDashboard() {
  const { data } = usePerformance();
  if (!data || data.total_trades === 0) {
    return (
      <div className="lift rounded-[var(--radius-md)] inner-card px-3 py-4">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold mb-2">
          <Award size={11} className="text-[var(--color-accent)]" />
          Performance Dashboard
        </div>
        <div className="text-[10px] text-[var(--color-fg-faint)] text-center py-4">
          Belum ada trade tertutup. Cascade engine akan mulai log outcome di sini.
        </div>
      </div>
    );
  }

  const winRate = data.win_rate ?? 0;
  const winRateTone =
    winRate >= 60 ? "var(--color-success)" : winRate >= 45 ? "var(--color-warning)" : "var(--color-danger)";
  const pnlTone = data.total_pnl > 0 ? "var(--color-success)" : "var(--color-danger)";
  const sharpeTone =
    data.sharpe == null
      ? "var(--color-fg-muted)"
      : data.sharpe >= 1.5
        ? "var(--color-success)"
        : data.sharpe >= 1
          ? "var(--color-warning)"
          : "var(--color-danger)";

  const curve = data.equity_curve ?? [];
  const curveSpark = curve.length > 1
    ? (() => {
        const max = Math.max(...curve);
        const min = Math.min(...curve);
        const range = max - min || 1;
        return curve
          .map((v, i) => `${(i / (curve.length - 1)) * 100},${50 - ((v - min) / range) * 40}`)
          .join(" ");
      })()
    : null;
  const trendUp = curve.length > 1 && curve[curve.length - 1] > curve[0];

  return (
    <div className="lift rounded-[var(--radius-md)] inner-card overflow-hidden">
      <div className="px-3 py-2 flex items-center gap-2 border-b border-[var(--color-border)]/50">
        <Award size={11} className="text-[var(--color-accent)]" />
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
          Performance Dashboard
        </span>
        <span className="text-[9px] text-[var(--color-fg-faint)] ml-auto">
          {data.total_trades} closed trades
        </span>
      </div>

      <div className="p-4 grid grid-cols-2 lg:grid-cols-4 gap-2">
        <Metric
          label="Win Rate"
          value={`${winRate.toFixed(1)}%`}
          sub={`${data.by_direction?.LONG?.wins ?? 0}L · ${data.by_direction?.SHORT?.wins ?? 0}S wins`}
          tone={winRateTone}
        />
        <Metric
          label="Total PnL"
          value={`${fmtSign(data.total_pnl, 2)} USDT`}
          sub={`expectancy ${fmtSign(data.expectancy_usdt ?? 0, 2)}`}
          tone={pnlTone}
        />
        <Metric
          label="Sharpe"
          value={data.sharpe != null ? data.sharpe.toFixed(2) : "—"}
          sub={`Sortino ${data.sortino != null ? data.sortino.toFixed(2) : "—"}`}
          tone={sharpeTone}
        />
        <Metric
          label="Max DD"
          value={data.max_drawdown_pct != null ? `${data.max_drawdown_pct.toFixed(2)}%` : "—"}
          sub={`Calmar ${data.calmar != null ? data.calmar.toFixed(2) : "—"}`}
          tone={
            (data.max_drawdown_pct ?? 0) > 20
              ? "var(--color-danger)"
              : (data.max_drawdown_pct ?? 0) > 10
                ? "var(--color-warning)"
                : "var(--color-success)"
          }
        />
      </div>

      {/* Equity curve */}
      {curveSpark && (
        <div className="px-3 pb-3">
          <div className="text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1 flex items-center gap-1">
            <BarChart2 size={9} /> Equity curve
            <span className="num font-bold ml-auto" style={{ color: trendUp ? "var(--color-success)" : "var(--color-danger)" }}>
              {trendUp ? "+" : ""}{fmt(curve[curve.length - 1] - curve[0], 2)} USDT
            </span>
          </div>
          <svg width="100%" height="50" viewBox="0 0 100 50" preserveAspectRatio="none" className="block">
            <motion.polyline
              points={curveSpark}
              fill="none"
              stroke={trendUp ? "var(--color-success)" : "var(--color-danger)"}
              strokeWidth="0.6"
              vectorEffect="non-scaling-stroke"
              strokeLinecap="round"
              strokeLinejoin="round"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 1 }}
            />
          </svg>
        </div>
      )}

      {/* Direction breakdown */}
      <div className="px-3 pb-3 grid grid-cols-2 gap-2">
        {(["LONG", "SHORT"] as const).map((d) => {
          const stats = data.by_direction[d];
          if (!stats) return null;
          const tone = d === "LONG" ? "var(--color-success)" : "var(--color-danger)";
          const Icon = d === "LONG" ? TrendingUp : TrendingDown;
          return (
            <div key={d} className="rounded-[var(--radius-sm)] bg-white/[0.03] px-2.5 py-1.5">
              <div className="flex items-center gap-1.5 text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1">
                <Icon size={9} style={{ color: tone }} />
                {d} breakdown
              </div>
              <div className="flex items-center justify-between text-[10px] num">
                <span style={{ color: tone }} className="font-bold">
                  {stats.win_rate.toFixed(1)}% WR
                </span>
                <span className="text-[var(--color-fg-faint)]">
                  {stats.wins}W · {stats.losses}L
                </span>
                <span
                  className="font-bold"
                  style={{ color: stats.pnl > 0 ? "var(--color-success)" : "var(--color-danger)" }}
                >
                  {fmtSign(stats.pnl, 2)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub: string;
  tone: string;
}) {
  return (
    <div className="rounded-[var(--radius-sm)] bg-white/[0.03] px-2.5 py-2">
      <div className="text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1">
        {label}
      </div>
      <div className="text-base font-bold num leading-none" style={{ color: tone }}>
        {value}
      </div>
      <div className="text-[8px] text-[var(--color-fg-faint)] mt-1 truncate">{sub}</div>
    </div>
  );
}

void Target;
