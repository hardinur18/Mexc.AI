import { useEffect, useState } from "react";
import { Clock } from "lucide-react";
import { fmtPct } from "@/lib/format";
import type { Position } from "@/types/position";
import { cn } from "@/lib/cn";

function useCountdown(targetMs: number): string {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const diff = Math.max(0, targetMs - now);
  const h = Math.floor(diff / 3600_000);
  const m = Math.floor((diff % 3600_000) / 60_000);
  const s = Math.floor((diff % 60_000) / 1000);
  return h > 0
    ? `${h}h ${m.toString().padStart(2, "0")}m`
    : `${m}:${s.toString().padStart(2, "0")}`;
}

interface FundingCardProps {
  p: Position;
}

export function FundingCard({ p }: FundingCardProps) {
  const f = p.funding;
  if (!f) {
    return (
      <div className="rounded-[var(--radius-md)] inner-card px-3 py-2.5">
        <div className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] mb-1 flex items-center gap-1.5">
          <Clock size={11} />
          Funding
        </div>
        <div className="text-[11px] text-[var(--color-fg-faint)]">No funding data</div>
      </div>
    );
  }
  const ratePct = f.rate * 100;
  // Direction effect — LONG pays positive funding, SHORT pays negative
  const youPay =
    (p.side === "LONG" && ratePct > 0) || (p.side === "SHORT" && ratePct < 0);
  const youReceive =
    (p.side === "LONG" && ratePct < 0) || (p.side === "SHORT" && ratePct > 0);

  const tone = youPay
    ? "var(--color-danger)"
    : youReceive
      ? "var(--color-success)"
      : "var(--color-fg-muted)";
  const status = youPay ? "You pay" : youReceive ? "You receive" : "Neutral";
  const countdown = useCountdown(f.next_settle_ms);

  return (
    <div className="rounded-[var(--radius-md)] inner-card px-3 py-2.5">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] flex items-center gap-1.5">
          <Clock size={11} />
          Funding
        </span>
        <span
          className="text-[9px] uppercase tracking-wider font-bold"
          style={{ color: tone }}
        >
          {status}
        </span>
      </div>
      <div className="flex items-baseline gap-2 mb-1">
        <span
          className="num text-lg font-bold"
          style={{ color: tone }}
        >
          {fmtPct(ratePct)}
        </span>
        <span className="text-[10px] text-[var(--color-fg-faint)]">per {f.collect_cycle_hours}h</span>
      </div>
      <div className="flex items-center justify-between text-[10px]">
        <span className="text-[var(--color-fg-subtle)] uppercase tracking-wider">
          Next settle in
        </span>
        <span
          className={cn(
            "num font-semibold",
            youPay ? "text-[var(--color-danger)]" : "text-[var(--color-fg-muted)]",
          )}
        >
          {countdown}
        </span>
      </div>
    </div>
  );
}
