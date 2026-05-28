import { motion } from "motion/react";
import { X } from "lucide-react";
import { fmt, fmtSign } from "@/lib/format";
import type { AccountSummary } from "@/types/position";
import { useUiStore } from "@/store/ui";
import { cn } from "@/lib/cn";

const COLOR_TO_OKLCH: Record<string, string> = {
  violet: "oklch(72% 0.18 280)",
  emerald: "oklch(78% 0.17 165)",
  sky: "oklch(75% 0.13 220)",
  amber: "oklch(80% 0.17 75)",
  rose: "oklch(70% 0.22 25)",
  cyan: "oklch(80% 0.13 210)",
  fuchsia: "oklch(72% 0.22 320)",
  lime: "oklch(85% 0.18 130)",
};

interface AccountBreakdownProps {
  accounts: AccountSummary[];
}

/** Inner content — used inside InsightsPanel. */
export function AccountBreakdownInner({ accounts }: AccountBreakdownProps) {
  const toggleAccount = useUiStore((s) => s.toggleAccount);
  const totalEquity = accounts.reduce((sum, a) => sum + a.equity, 0);
  const totalUnrealized = accounts.reduce((sum, a) => sum + a.unrealized, 0);

  if (accounts.length === 0) {
    return (
      <div className="px-4 py-8 text-center text-[11px] text-[var(--color-fg-faint)]">
        Belum ada akun terkonfigurasi
      </div>
    );
  }

  return (
    <div className="px-4 py-3">
      {/* Stats summary */}
      <div className="flex items-center justify-between mb-3 text-[10px] uppercase tracking-wider text-[var(--color-fg-faint)]">
        <span>{accounts.length} akun · total {fmt(totalEquity, 2)} USDT</span>
        <span
          className="num font-semibold"
          style={{
            color:
              totalUnrealized > 0
                ? "var(--color-success)"
                : totalUnrealized < 0
                  ? "var(--color-danger)"
                  : "var(--color-fg-muted)",
          }}
        >
          {fmtSign(totalUnrealized, 2)} unrealized
        </span>
      </div>

      {/* Distribution bar (stacked) */}
      {accounts.length > 1 && totalEquity > 0 && (
        <div className="relative h-1.5 rounded-full overflow-hidden bg-[var(--color-surface)] mb-3">
          {accounts.map((a, i) => {
            const pct = (a.equity / totalEquity) * 100;
            const offset = accounts
              .slice(0, i)
              .reduce((sum, prev) => sum + (prev.equity / totalEquity) * 100, 0);
            const color = COLOR_TO_OKLCH[a.color] ?? COLOR_TO_OKLCH.violet;
            return (
              <motion.div
                key={a.id}
                initial={{ width: 0 }}
                animate={{ width: `${pct}%` }}
                transition={{
                  duration: 0.6,
                  ease: [0.34, 1.4, 0.4, 1],
                  delay: i * 0.05,
                }}
                className="absolute top-0 bottom-0"
                style={{
                  left: `${offset}%`,
                  background: color,
                  boxShadow: `0 0 6px ${color}40`,
                }}
                title={`${a.name}: ${pct.toFixed(1)}%`}
              />
            );
          })}
        </div>
      )}

      {/* Chips */}
      <div className="flex flex-wrap gap-1.5">
        {accounts.map((a) => {
          const color = COLOR_TO_OKLCH[a.color] ?? COLOR_TO_OKLCH.violet;
          const pnlTone =
            a.unrealized > 0
              ? "var(--color-success)"
              : a.unrealized < 0
                ? "var(--color-danger)"
                : "var(--color-fg-muted)";
          return (
            <div
              key={a.id}
              className={cn(
                "group inline-flex items-center gap-2 px-2.5 py-1.5 rounded-[var(--radius-md)] inner-card hover:ring-[var(--color-border-strong)] transition",
              )}
            >
              <span
                className="w-2 h-2 rounded-full"
                style={{ background: color, boxShadow: `0 0 4px ${color}` }}
              />
              <div className="leading-tight min-w-0">
                <div className="text-[11px] font-semibold truncate max-w-[140px]">
                  {a.name}
                </div>
                <div className="text-[10px] num text-[var(--color-fg-muted)]">
                  {fmt(a.equity, 2)}
                  <span className="ml-1.5 num" style={{ color: pnlTone }}>
                    {fmtSign(a.unrealized, 2)}
                  </span>
                  <span className="text-[var(--color-fg-faint)]">
                    {" "}
                    · {a.position_count} pos
                  </span>
                </div>
              </div>
              {a.error && (
                <span className="text-[9px] uppercase tracking-wider text-[var(--color-danger)] px-1.5 py-0.5 rounded bg-[var(--color-danger-soft)]">
                  ERR
                </span>
              )}
              {accounts.length > 1 && (
                <button
                  type="button"
                  onClick={() => toggleAccount(a.id)}
                  className="opacity-0 group-hover:opacity-100 transition text-[var(--color-fg-subtle)] hover:text-[var(--color-fg)]"
                  title={`Exclude ${a.name}`}
                >
                  <X size={12} />
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Default export — wrapper. Use Inner inside InsightsPanel. */
export function AccountBreakdown({ accounts }: AccountBreakdownProps) {
  return (
    <div className="glass rounded-[var(--radius-lg)] mb-5">
      <AccountBreakdownInner accounts={accounts} />
    </div>
  );
}
