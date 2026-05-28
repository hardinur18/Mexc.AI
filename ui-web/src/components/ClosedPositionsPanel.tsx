import { CheckCircle, XCircle } from "lucide-react";
import { useClosedPositions } from "@/hooks/useSnapshot";
import { CoinIcon } from "@/components/ui/CoinIcon";
import { fmt, fmtPrice, fmtSign } from "@/lib/format";
import { cn } from "@/lib/cn";

/** Inner content for InsightsPanel — no wrapper, no header. */
export function ClosedPositionsPanelInner() {
  const { data } = useClosedPositions(50);

  if (!data || data.count === 0) {
    return (
      <div className="px-4 py-8 text-center text-[11px] text-[var(--color-fg-faint)]">
        Belum ada posisi tertutup di session ini
      </div>
    );
  }

  const totalPnl = data.items.reduce((s, i) => s + (i.pnl_final ?? 0), 0);
  const wins = data.items.filter((i) => i.pnl_final > 0).length;
  const losses = data.count - wins;
  const winRate = data.count > 0 ? (wins / data.count) * 100 : 0;

  return (
    <div className="px-4 pb-4">
      {/* Summary bar */}
      <div className="flex items-center justify-between py-2.5 text-[10px] text-[var(--color-fg-faint)] uppercase tracking-wider">
        <div className="flex items-center gap-3">
          <span className="text-[var(--color-success)] num">{wins}W</span>
          <span>/</span>
          <span className="text-[var(--color-danger)] num">{losses}L</span>
          <span className="text-[var(--color-fg-faint)]">·</span>
          <span>{winRate.toFixed(0)}% win-rate</span>
        </div>
        <span
          className="num font-semibold"
          style={{
            color:
              totalPnl > 0
                ? "var(--color-success)"
                : totalPnl < 0
                  ? "var(--color-danger)"
                  : "var(--color-fg-muted)",
          }}
        >
          Total: {fmtSign(totalPnl, 2)} USDT
        </span>
      </div>

      <div className="max-h-[350px] overflow-y-auto space-y-0.5">
        {data.items.map((c, i) => {
          const isWin = c.pnl_final > 0;
          const tone = isWin ? "var(--color-success)" : "var(--color-danger)";
          const Icon = isWin ? CheckCircle : XCircle;
          const ago = Date.now() - c.ts;
          const agoText =
            ago < 60_000
              ? "baru saja"
              : ago < 3600_000
                ? `${Math.floor(ago / 60000)}m lalu`
                : `${Math.floor(ago / 3600000)}j lalu`;
          return (
            <div
              key={`${c.ts}-${i}`}
              className="grid grid-cols-[20px_1fr_auto_auto] items-center gap-3 px-2 py-1.5 rounded-[var(--radius-sm)] hover:bg-white/[0.02] transition"
            >
              <Icon size={14} style={{ color: tone }} />
              <div className="flex items-center gap-2 min-w-0">
                <CoinIcon coin={c.coin} iconUrl={c.icon_url} size={22} />
                <div className="leading-tight min-w-0">
                  <div className="text-xs font-semibold truncate">
                    {c.symbol}
                    <span
                      className={cn(
                        "ml-2 text-[9px] px-1 rounded font-bold uppercase",
                        c.side === "LONG"
                          ? "text-[var(--color-success)] bg-[var(--color-success-soft)]"
                          : "text-[var(--color-danger)] bg-[var(--color-danger-soft)]",
                      )}
                    >
                      {c.side}
                    </span>
                    <span className="text-[9px] text-[var(--color-warning)] ml-1.5">
                      {c.lev}x
                    </span>
                  </div>
                  <div className="text-[10px] text-[var(--color-fg-faint)] font-mono">
                    entry {fmtPrice(c.entry)} → exit ~
                    {fmtPrice(c.exit_estimate)} · {c.account_name}
                  </div>
                </div>
              </div>
              <div className="text-right leading-tight num">
                <div className="text-sm font-bold" style={{ color: tone }}>
                  {fmtSign(c.pnl_final, 4)}
                </div>
                <div className="text-[9px] text-[var(--color-fg-faint)]">
                  margin {fmt(c.margin_used, 3)}
                </div>
              </div>
              <div className="text-[9px] text-[var(--color-fg-faint)] uppercase tracking-wider w-14 text-right">
                {agoText}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Default export — for backward compat. Use Inner inside InsightsPanel. */
export function ClosedPositionsPanel() {
  return (
    <div className="glass rounded-[var(--radius-lg)] mb-5 overflow-hidden">
      <ClosedPositionsPanelInner />
    </div>
  );
}
