import { motion } from "motion/react";
import { Bitcoin, Activity, Shield, AlertTriangle } from "lucide-react";
import { useMacro, useCircuitBreaker, usePortfolioRisk } from "@/hooks/useSnapshot";
import { fmt, fmtPct } from "@/lib/format";

/**
 * Floating top-of-screen HUD: BTC dominance + ETH/BTC + market mood +
 * portfolio heat + circuit breaker status.
 *
 * Always-visible institutional context for ratusan-layar trader feel.
 */
export function MacroHud() {
  const { data: macro } = useMacro();
  const { data: heat } = usePortfolioRisk();
  const { data: breaker } = useCircuitBreaker();

  if (!macro && !heat && !breaker) return null;

  const moodTone =
    macro?.market_mood === "risk_on"
      ? "var(--color-success)"
      : macro?.market_mood === "risk_off"
        ? "var(--color-danger)"
        : macro?.market_mood === "defensive"
          ? "var(--color-warning)"
          : macro?.market_mood === "constructive"
            ? "var(--color-success)"
            : "var(--color-fg-muted)";

  const heatTone =
    heat?.heat?.warning_level === "critical"
      ? "var(--color-danger)"
      : heat?.heat?.warning_level === "high"
        ? "var(--color-warning)"
        : heat?.heat?.warning_level === "moderate"
          ? "var(--color-warning)"
          : "var(--color-success)";

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="flex items-center gap-2.5 px-3 py-1.5 rounded-[var(--radius-md)] glass ring-1 ring-[var(--color-border)] text-[10px] flex-wrap"
    >
      {/* BTC dominance + change */}
      {macro?.btc_dominance && (
        <HudCell
          icon={<Bitcoin size={11} className="text-[var(--color-warning)]" />}
          label="BTC dom"
          value={
            macro.btc_dominance.btc_dominance_pct != null
              ? `${macro.btc_dominance.btc_dominance_pct.toFixed(1)}%`
              : "—"
          }
          sub={
            macro.btc_dominance.btc_change_24h_pct != null
              ? fmtPct(macro.btc_dominance.btc_change_24h_pct)
              : ""
          }
          subTone={
            (macro.btc_dominance.btc_change_24h_pct ?? 0) > 0
              ? "var(--color-success)"
              : "var(--color-danger)"
          }
        />
      )}

      {/* ETH/BTC ratio */}
      {macro?.btc_dominance?.eth_btc_ratio != null && (
        <HudCell
          label="ETH/BTC"
          value={macro.btc_dominance.eth_btc_ratio.toFixed(5)}
          sub={macro.alt_season?.replace("_", " ")}
          subTone={
            macro.alt_season === "alt_season_likely"
              ? "var(--color-success)"
              : "var(--color-fg-faint)"
          }
        />
      )}

      {/* Market mood */}
      {macro?.market_mood && (
        <HudCell
          icon={<Activity size={11} style={{ color: moodTone }} />}
          label="Mood"
          value={macro.market_mood.replace("_", " ")}
          tone={moodTone}
        />
      )}

      {/* Portfolio heat */}
      {heat && (
        <HudCell
          icon={<Shield size={11} style={{ color: heatTone }} />}
          label="Heat"
          value={`${heat.heat.total_heat_pct.toFixed(1)}%`}
          sub={`${heat.heat.open_positions} pos`}
          tone={heatTone}
        />
      )}

      {/* Circuit breaker */}
      {breaker && (
        <HudCell
          icon={
            breaker.tripped ? (
              <AlertTriangle size={11} className="text-[var(--color-danger)] animate-pulse" />
            ) : (
              <Shield size={11} className="text-[var(--color-success)]" />
            )
          }
          label="Daily"
          value={fmtPct(breaker.daily_pct_equity)}
          sub={breaker.tripped ? "TRIPPED" : "ok"}
          tone={
            breaker.tripped
              ? "var(--color-danger)"
              : breaker.daily_pct_equity > 0
                ? "var(--color-success)"
                : "var(--color-fg-muted)"
          }
        />
      )}
    </motion.div>
  );
}

function HudCell({
  icon,
  label,
  value,
  sub,
  tone,
  subTone,
}: {
  icon?: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  tone?: string;
  subTone?: string;
}) {
  return (
    <div className="flex items-center gap-1.5">
      {icon}
      <div className="leading-tight">
        <div className="text-[8px] uppercase tracking-wider text-[var(--color-fg-faint)]">
          {label}
        </div>
        <div className="flex items-baseline gap-1">
          <span
            className="text-[11px] font-bold num"
            style={{ color: tone || "var(--color-fg)" }}
          >
            {value}
          </span>
          {sub && (
            <span className="text-[9px] num" style={{ color: subTone || "var(--color-fg-faint)" }}>
              {sub}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// Mute unused import warnings — fmt is loaded for parity
void fmt;
