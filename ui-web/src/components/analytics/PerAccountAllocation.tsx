import { motion } from "motion/react";
import { Wallet } from "lucide-react";
import type { AccountSummary, EntryPlan } from "@/types/position";
import { fmt } from "@/lib/format";

interface Props {
  plan: EntryPlan | null | undefined;
  accounts: AccountSummary[];
  /** Optional filter — accounts to consider for allocation. Default: all. */
  filterAccountIds?: string[];
}

const TIER_TONE: Record<string, string> = {
  radar: "var(--color-warning)",
  main_1: "var(--color-accent)",
  main_2: "var(--color-accent)",
  booster: "var(--color-success)",
};

/**
 * Shows USD breakdown per account per tier.
 *
 * Math: per-tier USD = account.equity × tier.size_pct_equity / 100
 *       notional    = USD × tier.lev
 *
 * Visual: compact table with sticky header.
 */
export function PerAccountAllocation({ plan, accounts, filterAccountIds }: Props) {
  if (!plan?.tiers || plan.tiers.length === 0) return null;
  const visible = filterAccountIds
    ? accounts.filter((a) => filterAccountIds.includes(a.id))
    : accounts;

  if (visible.length === 0) return null;

  const totalEquity = visible.reduce((s, a) => s + a.equity, 0);
  const totalTierPct = plan.tiers.reduce((s, t) => s + t.size_pct_equity, 0);
  const grandUsd = (totalEquity * totalTierPct) / 100;

  return (
    <div className="lift rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] overflow-hidden">
      <div className="px-3 py-2 flex items-center gap-2 border-b border-[var(--color-border)]/50">
        <Wallet size={11} className="text-[var(--color-accent)]" />
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
          Alokasi per akun
        </span>
        <span className="text-[9px] text-[var(--color-fg-faint)] ml-auto">
          total {fmt(grandUsd, 2)} USDT across all tiers
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-[10px]">
          <thead>
            <tr className="text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)] border-b border-[var(--color-border)]/40">
              <th className="text-left px-3 py-1.5 font-semibold">Akun</th>
              <th className="text-right px-2 py-1.5 font-semibold">Equity</th>
              {plan.tiers.map((t) => (
                <th key={t.role} className="text-right px-2 py-1.5 font-semibold">
                  <span
                    className="inline-block px-1 rounded text-[8px]"
                    style={{
                      color: TIER_TONE[t.role] || "var(--color-fg-muted)",
                      background: `color-mix(in oklch, ${TIER_TONE[t.role] || "var(--color-fg-muted)"} 12%, transparent)`,
                    }}
                  >
                    {t.name}
                  </span>
                  <div className="text-[8px] font-normal text-[var(--color-fg-faint)] normal-case mt-0.5">
                    {t.size_pct_equity}% · {t.lev}x
                  </div>
                </th>
              ))}
              <th className="text-right px-3 py-1.5 font-semibold">Total</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((acc, i) => {
              const rowTotal = plan.tiers!.reduce(
                (s, t) => s + (acc.equity * t.size_pct_equity) / 100,
                0,
              );
              return (
                <motion.tr
                  key={acc.id}
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.25, delay: i * 0.03 }}
                  className="border-b border-[var(--color-border)]/20 hover:bg-white/[0.02]"
                >
                  <td className="px-3 py-1.5">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span
                        className="w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ background: `var(--color-${acc.color}, var(--color-accent))` }}
                      />
                      <span className="font-semibold truncate max-w-[100px]">{acc.name}</span>
                    </div>
                  </td>
                  <td className="text-right px-2 py-1.5 num text-[var(--color-fg-muted)]">
                    {fmt(acc.equity, 2)}
                  </td>
                  {plan.tiers!.map((t) => {
                    const usd = (acc.equity * t.size_pct_equity) / 100;
                    const notional = usd * t.lev;
                    return (
                      <td key={t.role} className="text-right px-2 py-1.5 num leading-tight">
                        <div className="font-semibold" style={{ color: TIER_TONE[t.role] }}>
                          ${fmt(usd, 2)}
                        </div>
                        <div className="text-[8px] text-[var(--color-fg-faint)]">
                          ${fmt(notional, 0)} not.
                        </div>
                      </td>
                    );
                  })}
                  <td className="text-right px-3 py-1.5 num font-bold text-[var(--color-fg)]">
                    ${fmt(rowTotal, 2)}
                  </td>
                </motion.tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
