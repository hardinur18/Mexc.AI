import { motion } from "motion/react";
import { Trophy, TrendingUp, TrendingDown } from "lucide-react";
import { usePatternWinrate } from "@/hooks/useSnapshot";
import { fmt, fmtSign } from "@/lib/format";

const PATTERN_LABEL: Record<string, string> = {
  bullish_engulfing: "Bullish Engulfing",
  bearish_engulfing: "Bearish Engulfing",
  hammer: "Hammer",
  shooting_star: "Shooting Star",
  bullish_pin_bar: "Pin Bar Bull",
  bearish_pin_bar: "Pin Bar Bear",
  dragonfly_doji: "Dragonfly Doji",
  gravestone_doji: "Gravestone Doji",
  morning_star: "Morning Star",
  evening_star: "Evening Star",
  three_white_soldiers: "3 White Soldiers",
  three_black_crows: "3 Black Crows",
  piercing_line: "Piercing Line",
  dark_cloud_cover: "Dark Cloud Cover",
  tweezer_bottom: "Tweezer Bottom",
  tweezer_top: "Tweezer Top",
  bullish_harami: "Harami Bull",
  bearish_harami: "Harami Bear",
};

export function PatternWinrateCard() {
  const { data } = usePatternWinrate();
  if (!data) return null;

  if (data.total_closed === 0) {
    return (
      <div className="lift rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] overflow-hidden">
        <div className="px-3 py-2 flex items-center gap-2 border-b border-[var(--color-border)]/50">
          <Trophy size={11} className="text-[var(--color-accent)]" />
          <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
            Pattern Winrate
          </span>
        </div>
        <div className="p-4 text-center text-[10px] text-[var(--color-fg-faint)] italic">
          {data.note ?? "Belum ada cascade closed di journal."}
          <br />
          <span className="text-[9px]">Mulai cascade (paper / live) untuk track winrate engine.</span>
        </div>
      </div>
    );
  }

  const direction = data.by_direction ?? {};
  const scoreBands = data.by_score_band ?? {};
  const patterns = data.by_pattern ?? {};

  return (
    <div className="lift rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] overflow-hidden">
      <div className="px-3 py-2 flex items-center gap-2 border-b border-[var(--color-border)]/50">
        <Trophy size={11} className="text-[var(--color-accent)]" />
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
          Pattern Winrate
        </span>
        <span className="text-[9px] text-[var(--color-fg-faint)] ml-auto">
          {data.total_closed} closed trades
        </span>
      </div>

      <div className="p-3 space-y-3">
        {/* By direction */}
        <div className="grid grid-cols-2 gap-2">
          {(["LONG", "SHORT"] as const).map((d) => {
            const stats = direction[d];
            if (!stats) return null;
            const tone = d === "LONG" ? "var(--color-success)" : "var(--color-danger)";
            const Icon = d === "LONG" ? TrendingUp : TrendingDown;
            return (
              <motion.div
                key={d}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-[var(--radius-sm)] bg-white/[0.03] px-2.5 py-2"
              >
                <div className="flex items-center gap-1.5 text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1">
                  <Icon size={10} style={{ color: tone }} />
                  {d}
                </div>
                <div className="flex items-baseline justify-between">
                  <span className="text-base font-bold num leading-none" style={{ color: tone }}>
                    {stats.win_rate.toFixed(1)}%
                  </span>
                  <span className="text-[9px] num text-[var(--color-fg-muted)]">
                    {stats.wins}W · {stats.losses}L
                  </span>
                </div>
                <div className="text-[9px] num font-bold mt-0.5" style={{
                  color: stats.total_pnl > 0 ? "var(--color-success)" : "var(--color-danger)"
                }}>
                  {fmtSign(stats.total_pnl, 2)} USDT
                </div>
              </motion.div>
            );
          })}
        </div>

        {/* By score band */}
        {Object.keys(scoreBands).length > 0 && (
          <div>
            <div className="text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1">
              By score band
            </div>
            <div className="space-y-0.5">
              {Object.entries(scoreBands)
                .sort(([a], [b]) => b.localeCompare(a))
                .map(([band, stats]) => {
                  const wrTone =
                    stats.win_rate >= 60
                      ? "var(--color-success)"
                      : stats.win_rate >= 45
                        ? "var(--color-warning)"
                        : "var(--color-danger)";
                  return (
                    <div
                      key={band}
                      className="flex items-center justify-between text-[9px] px-2 py-1 rounded bg-white/[0.02]"
                    >
                      <span className="text-[var(--color-fg-muted)]">{band.replace("_", " ")}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-[var(--color-fg-faint)] num">
                          {stats.trades}x
                        </span>
                        <span className="num font-bold w-12 text-right" style={{ color: wrTone }}>
                          {stats.win_rate.toFixed(0)}%
                        </span>
                        <span
                          className="num w-16 text-right text-[8px]"
                          style={{
                            color: stats.total_pnl > 0 ? "var(--color-success)" : "var(--color-danger)",
                          }}
                        >
                          {fmtSign(stats.total_pnl, 2)}
                        </span>
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        )}

        {/* By pattern */}
        {Object.keys(patterns).length > 0 && (
          <div>
            <div className="text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1">
              By pattern
            </div>
            <div className="space-y-0.5">
              {Object.entries(patterns)
                .sort(([, a], [, b]) => b.trades - a.trades)
                .slice(0, 10)
                .map(([pat, stats]) => {
                  const wrTone =
                    stats.win_rate >= 60
                      ? "var(--color-success)"
                      : stats.win_rate >= 45
                        ? "var(--color-warning)"
                        : "var(--color-danger)";
                  return (
                    <div
                      key={pat}
                      className="flex items-center justify-between text-[9px] px-2 py-1 rounded bg-white/[0.02]"
                    >
                      <span className="text-[var(--color-fg-muted)] truncate">
                        {PATTERN_LABEL[pat] ?? pat}
                      </span>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-[var(--color-fg-faint)] num text-[8px]">
                          {stats.trades}x
                        </span>
                        <span className="num font-bold w-10 text-right" style={{ color: wrTone }}>
                          {stats.win_rate.toFixed(0)}%
                        </span>
                        <span
                          className="num text-[8px] w-14 text-right"
                          style={{
                            color: stats.total_pnl > 0 ? "var(--color-success)" : "var(--color-danger)",
                          }}
                        >
                          {fmtSign(stats.total_pnl, 2)}
                        </span>
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        )}
      </div>
    </div>
  );

  void fmt; // keep import for future formatting needs
}
