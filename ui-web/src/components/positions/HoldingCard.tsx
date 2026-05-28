import { useEffect, useState } from "react";
import { History } from "lucide-react";
import type { Position } from "@/types/position";

function formatDuration(ms: number): string {
  const sec = Math.floor(ms / 1000);
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${sec}s`;
}

interface HoldingCardProps {
  p: Position;
}

export function HoldingCard({ p }: HoldingCardProps) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  if (!p.create_time) {
    return (
      <div className="rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] px-3 py-2.5">
        <div className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] mb-1 flex items-center gap-1.5">
          <History size={11} />
          Position
        </div>
        <div className="text-[11px] text-[var(--color-fg-faint)]">No timestamp</div>
      </div>
    );
  }

  const duration = now - p.create_time;
  const text = formatDuration(duration);
  const openedAt = new Date(p.create_time).toLocaleString("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "short",
  });

  return (
    <div className="rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] px-3 py-2.5">
      <div className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] mb-1 flex items-center gap-1.5">
        <History size={11} />
        Holding
      </div>
      <div className="num text-lg font-bold text-[var(--color-fg)]">
        {text}
      </div>
      <div className="text-[10px] text-[var(--color-fg-faint)] mt-0.5">
        opened {openedAt}
      </div>
    </div>
  );
}
