import { useEffect, useState, type ReactNode } from "react";
import { Card } from "@/components/ui/Card";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { pnlTone } from "@/lib/format";
import type { Account, Totals, Position } from "@/types/position";
import { motion, type Variants } from "motion/react";
import { cn } from "@/lib/cn";
import { Activity, Banknote, CircleDollarSign, Layers, TrendingUp, Wallet } from "lucide-react";

interface StatCardsProps {
  account: Account;
  totals: Totals;
  positions: Position[];
  ts: number;
}

const container: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.05, delayChildren: 0.1 } },
};
const item: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.34, 1.4, 0.4, 1] as const } },
};

export function StatCards({ account, totals, positions, ts }: StatCardsProps) {
  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="show"
      className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-5"
    >
      <Stat icon={<CircleDollarSign size={14} />} label="Ekuitas" value={account.equity} decimals={2} sub="USDT" />
      <Stat icon={<Wallet size={14} />} label="Saldo Dompet" value={account.cash} decimals={2} sub="USDT" />
      <Stat
        icon={<Activity size={14} />}
        label="PnL Berjalan"
        value={account.unrealized}
        decimals={4}
        signed
        sub="live"
        tone={pnlTone(account.unrealized)}
      />
      <Stat
        icon={<TrendingUp size={14} />}
        label="Total PnL"
        value={totals.pnl_net}
        decimals={4}
        signed
        sub="berjalan + terealisasi"
        tone={pnlTone(totals.pnl_net)}
      />
      <Stat
        icon={<Banknote size={14} />}
        label="Total Margin"
        value={totals.margin}
        decimals={3}
        sub={`/ ${totals.notional.toFixed(0)} nilai posisi`}
      />
      <motion.div variants={item}>
        <LongShortCard positions={positions} ts={ts} />
      </motion.div>
    </motion.div>
  );
}

function Stat({
  icon,
  label,
  value,
  decimals = 2,
  signed = false,
  sub,
  tone = "zero",
}: {
  icon: ReactNode;
  label: string;
  value: number;
  decimals?: number;
  signed?: boolean;
  sub?: string;
  tone?: "up" | "down" | "zero";
}) {
  const toneCls =
    tone === "up"
      ? "text-[var(--color-success)]"
      : tone === "down"
        ? "text-[var(--color-danger)]"
        : "text-[var(--color-fg)]";

  return (
    <motion.div variants={item}>
      <Card className="p-4 transition hover:ring-[var(--color-border-strong)] hover:translate-y-[-1px] hover:shadow-[var(--shadow-card)]">
        <div className="flex items-center gap-2">
          <span className="ui-icon-chip h-7 w-7">{icon}</span>
          <div className="text-[11px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-bold">
            {label}
          </div>
        </div>
        <div className={cn("text-lg font-semibold num mt-1.5", toneCls)}>
          <AnimatedNumber value={value} decimals={decimals} signed={signed} />
        </div>
        {sub && (
          <div className="text-[11px] text-[var(--color-fg-faint)] mt-1">{sub}</div>
        )}
      </Card>
    </motion.div>
  );
}

function LongShortCard({ positions, ts }: { positions: Position[]; ts: number }) {
  const long = positions.filter((p) => p.side === "LONG").length;
  const short = positions.filter((p) => p.side === "SHORT").length;
  const total = long + short;

  // Notional split
  const longNotional = positions
    .filter((p) => p.side === "LONG")
    .reduce((s, p) => s + p.notional, 0);
  const shortNotional = positions
    .filter((p) => p.side === "SHORT")
    .reduce((s, p) => s + p.notional, 0);
  const totalNotional = longNotional + shortNotional || 1;
  const longPct = (longNotional / totalNotional) * 100;

  return (
    <Card className="p-4 transition hover:ring-[var(--color-border-strong)] hover:translate-y-[-1px] hover:shadow-[var(--shadow-card)]">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="ui-icon-chip h-7 w-7"><Layers size={14} /></span>
          <div className="text-[11px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-bold">
            Posisi
          </div>
        </div>
        <TimeAgo ts={ts} />
      </div>
      <div className="text-lg font-semibold num mt-1.5">
        {total} <span className="text-[10px] text-[var(--color-fg-faint)] font-normal">total</span>
      </div>
      {/* Long / Short split bar */}
      {total > 0 && (
        <div className="mt-1.5">
          <div className="relative h-1 rounded-full overflow-hidden bg-[var(--color-border)]">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${longPct}%` }}
              transition={{ duration: 0.6, ease: [0.34, 1.4, 0.4, 1] }}
              className="absolute top-0 bottom-0 left-0"
              style={{ background: "var(--color-success)" }}
            />
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${100 - longPct}%` }}
              transition={{ duration: 0.6, ease: [0.34, 1.4, 0.4, 1] }}
              className="absolute top-0 bottom-0 right-0"
              style={{ background: "var(--color-danger)" }}
            />
          </div>
          <div className="flex justify-between text-[9px] num mt-0.5">
            <span className="text-[var(--color-success)] uppercase tracking-wider">
              {long} L
            </span>
            <span className="text-[var(--color-danger)] uppercase tracking-wider">
              {short} S
            </span>
          </div>
        </div>
      )}
    </Card>
  );
}

function TimeAgo({ ts }: { ts: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const diff = Math.max(0, now - ts);
  const sec = Math.floor(diff / 1000);
  const text = sec < 60 ? `${sec}d lalu` : `${Math.floor(sec / 60)}m lalu`;
  return (
    <span className="text-[9px] text-[var(--color-fg-faint)] uppercase tracking-wider num">
      {text}
    </span>
  );
}
