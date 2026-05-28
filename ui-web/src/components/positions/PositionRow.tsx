import { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { Badge } from "@/components/ui/Badge";
import {
  fmt,
  fmtPct,
  fmtPctPlain,
  fmtPrice,
  fmtSign,
  pnlTone,
  bufferTone,
  marginRatioTone,
} from "@/lib/format";
import type { Position } from "@/types/position";
import { ChevronRight, MoreHorizontal, Copy, ExternalLink } from "lucide-react";
import { cn } from "@/lib/cn";
import { Sparkline } from "./Sparkline";
import { CoinIcon } from "@/components/ui/CoinIcon";
import { SignalBadge } from "@/components/ui/SignalBadge";
import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/Popover";
import { toast } from "sonner";
import { useUiStore } from "@/store/ui";

interface PositionRowProps {
  p: Position;
  index: number;
  expanded: boolean;
  onToggle: () => void;
}

function toneClass(t: "up" | "down" | "zero" | "ok" | "warn" | "danger"): string {
  switch (t) {
    case "up":
      return "text-[var(--color-success)]";
    case "down":
      return "text-[var(--color-danger)]";
    case "warn":
      return "text-[var(--color-warning)]";
    case "danger":
      return "text-[var(--color-danger)]";
    case "ok":
      return "text-[var(--color-success)]";
    default:
      return "text-[var(--color-fg-muted)]";
  }
}

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

function accountColor(name: string | undefined): string {
  return COLOR_TO_OKLCH[name ?? "violet"] ?? COLOR_TO_OKLCH.violet;
}

export function PositionRow({ p, index, expanded, onToggle }: PositionRowProps) {
  // Unrealized-based tones (primary display — matches MEXC web)
  const pnlUnrealT = pnlTone(p.pnl_unrealized);
  const pnlPctUnrealLev = p.margin > 0 ? (p.pnl_unrealized / p.margin) * 100 : 0;
  const pnlUnrealLevT = pnlTone(pnlPctUnrealLev);
  const priceDeltaT = pnlTone(p.price_delta_pct);
  const buffT = bufferTone(p.buffer_pct);
  const mgnT = marginRatioTone(p.margin_ratio);

  // Cursor highlight from keyboard nav
  const cursor = useUiStore((s) => s.cursor);
  const isCursor = cursor === index;

  // Detect price change → trigger flash
  const lastPriceRef = useRef(p.price);
  const [flash, setFlash] = useState<"up" | "down" | null>(null);
  useEffect(() => {
    if (lastPriceRef.current !== p.price) {
      const diff = p.price - lastPriceRef.current;
      if (Math.abs(diff) > lastPriceRef.current * 0.0001) {
        const fav = (diff > 0 && p.side === "LONG") || (diff < 0 && p.side === "SHORT");
        setFlash(fav ? "up" : "down");
        const t = setTimeout(() => setFlash(null), 600);
        return () => clearTimeout(t);
      }
      lastPriceRef.current = p.price;
    }
    lastPriceRef.current = p.price;
  }, [p.price, p.side]);

  const flashBg =
    flash === "up"
      ? "bg-[color-mix(in_oklch,var(--color-success)_8%,transparent)]"
      : flash === "down"
        ? "bg-[color-mix(in_oklch,var(--color-danger)_8%,transparent)]"
        : "";

  // Stagger entrance — cap delay so tables of 50+ rows don't lag
  const staggerDelay = Math.min(index, 20) * 0.025;

  return (
    <motion.tr
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.25 } }}
      transition={{ duration: 0.32, ease: [0.34, 1.4, 0.4, 1], delay: staggerDelay }}
      className={cn(
        "group border-t border-[var(--color-border)] hover:bg-white/[0.025] transition cursor-pointer align-middle relative",
        expanded && "bg-white/[0.025]",
        isCursor && "ring-1 ring-inset ring-[var(--color-accent)]/40 bg-white/[0.03]",
        flashBg,
      )}
      onClick={onToggle}
    >
      {/* # + chevron */}
      <td className="px-3 py-2.5 text-[var(--color-fg-faint)] text-xs w-[44px]">
        <div className="flex items-center gap-1.5">
          <ChevronRight
            size={13}
            className={cn(
              "transition-transform duration-200 text-[var(--color-fg-subtle)]",
              expanded && "rotate-90 text-[var(--color-accent)]",
            )}
          />
          <span>{index + 1}</span>
        </div>
      </td>

      {/* Account: pindah ke kiri, sebelum Aset */}
      <td className="px-3 py-2.5">
        <div className="leading-tight">
          <div className="flex items-center gap-1.5">
            <span
              className="inline-block w-2 h-2 rounded-full shrink-0"
              style={{ background: accountColor(p.account_color) }}
            />
            <span className="text-sm font-medium truncate max-w-[100px]">
              {p.account_name}
            </span>
          </div>
          <div className="text-[10px] text-[var(--color-fg-faint)] font-mono mt-0.5">
            {p.account_id}
          </div>
        </div>
      </td>

      {/* Aset: coin icon + name + symbol + signal badge */}
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-2.5">
          <CoinIcon coin={p.coin} iconUrl={p.icon_url} size={28} />
          <div className="leading-tight min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-semibold">{p.coin}</span>
              <SignalBadge
                score={p.signal_score}
                verdict={p.signal_verdict}
                oversoldN={p.signal_oversold_n}
                overboughtN={p.signal_overbought_n}
                bbLower={p.signal_bb_lower}
                dist7dHigh={p.signal_dist_7d_high}
                size="xs"
              />
            </div>
            <div className="text-[10px] text-[var(--color-fg-subtle)] font-mono truncate">
              {p.symbol}
            </div>
            <div className="text-[10px] text-[var(--color-fg-faint)]">{p.open_type}</div>
          </div>
        </div>
      </td>

      {/* Side + Lev — inline horizontal */}
      <td className="px-3 py-2.5">
        <div className="flex items-center gap-1.5">
          <Badge tone={p.side === "LONG" ? "long" : "short"} size="sm">
            {p.side}
          </Badge>
          <span className="text-[var(--color-warning)] font-bold text-xs num">
            {p.lev}x
          </span>
          <span className="text-[9px] text-[var(--color-fg-faint)] uppercase tracking-wider">
            {p.open_type.slice(0, 5)}
          </span>
        </div>
      </td>

      {/* Mark / Entry / Δ + 24h sparkline (bigger 95×30) */}
      <td className="px-3 py-2.5 leading-tight">
        <div className="flex items-center justify-end gap-3">
          <Sparkline
            data={p.sparkline || []}
            width={95}
            height={30}
            refPrice={p.entry}
            markPrice={p.price}
          />
          <div className="text-right num">
            <AnimatedNumber
              value={p.price}
              format={(v) => fmtPrice(v)}
              className="text-sm font-semibold block"
            />
            <div className="text-[10px] flex items-center justify-end gap-1.5 mt-0.5">
              <span className="text-[var(--color-fg-faint)]">{fmtPrice(p.entry)}</span>
              <AnimatedNumber
                value={p.price_delta_pct}
                format={(v) => fmtPct(v)}
                className={toneClass(priceDeltaT)}
              />
            </div>
          </div>
        </div>
      </td>

      {/* PnL: UNREALIZED primary (matches MEXC web display) + realised badge */}
      <td className="px-3 py-2.5 text-right num leading-tight">
        <AnimatedNumber
          value={p.pnl_unrealized}
          decimals={4}
          signed
          className={cn("text-sm font-bold block", toneClass(pnlUnrealT))}
        />
        <AnimatedNumber
          value={pnlPctUnrealLev}
          format={(v) => fmtPct(v)}
          className={cn("text-[11px] font-semibold mt-0.5 block", toneClass(pnlUnrealLevT))}
        />
        {Math.abs(p.pnl_realised) >= 0.5 && (
          <div
            className={cn(
              "text-[10px] mt-0.5 inline-flex items-center gap-0.5 px-1.5 rounded-[var(--radius-xs)] ring-1",
              p.pnl_realised > 0
                ? "text-[var(--color-success)] bg-[var(--color-success-soft)] ring-[var(--color-success)]/30"
                : "text-[var(--color-fg-muted)] bg-white/[0.03] ring-[var(--color-border)]",
            )}
            title={`Realised from partial TPs: ${fmtSign(p.pnl_realised, 4)} USDT`}
          >
            ◆ {fmtSign(p.pnl_realised, 2)} locked
          </div>
        )}
      </td>

      {/* Margin + Notional + risk cap warning */}
      <td className="px-3 py-2.5 text-right num leading-tight">
        <div className="text-xs text-[var(--color-fg-muted)]">
          {fmt(p.margin, 3)}
        </div>
        <div className="text-[10px] text-[var(--color-fg-faint)] mt-0.5">
          {fmt(p.notional, 1)} not.
        </div>
        {/* 5% equity cap warning — based on margin vs total margin across positions */}
      </td>

      {/* TP — 1-2 lines */}
      <td className="px-3 py-2.5 text-right num leading-tight">
        {p.tp_price ? (
          <>
            <div className="text-sm text-[var(--color-success)] font-medium">
              {fmtPrice(p.tp_price)}
            </div>
            <div className="text-[10px] text-[var(--color-success)] flex items-center justify-end gap-1 mt-0.5">
              {fmtPct(p.tp_dist_pct)}
              {p.tp_count > 1 && (
                <span className="text-[var(--color-fg-faint)]">·{p.tp_count}</span>
              )}
            </div>
          </>
        ) : (
          <span className="text-[var(--color-fg-faint)] text-xs">—</span>
        )}
      </td>

      {/* SL */}
      <td className="px-3 py-2.5 text-right num leading-tight">
        {p.sl_price ? (
          <>
            <div className="text-sm text-[var(--color-danger)] font-medium">
              {fmtPrice(p.sl_price)}
            </div>
            <div className="text-[10px] text-[var(--color-danger)] mt-0.5">
              {fmtPct(p.sl_dist_pct)}
            </div>
          </>
        ) : (
          <Badge tone="danger" pulse size="sm">
            NO SL
          </Badge>
        )}
      </td>

      {/* Mgn Ratio / Liq — 2 lines */}
      <td className="px-3 py-2.5 text-right num leading-tight">
        <div className={cn("text-xs", toneClass(mgnT))}>
          {fmtPctPlain(p.margin_ratio)}
        </div>
        <div className="text-[10px] text-[var(--color-fg-faint)] mt-0.5">
          {p.liq_price ? fmtPrice(p.liq_price) : "shared"}
        </div>
      </td>

      {/* Buffer→Liq + quick actions */}
      <td className="px-3 py-2.5 text-right num leading-tight w-[140px]">
        <div className="flex items-center justify-end gap-2">
          <div className="flex-1">
            {p.buffer_pct !== null ? (
              <>
                <div className={cn("text-xs font-semibold", toneClass(buffT))}>
                  {fmtPctPlain(p.buffer_pct)}
                </div>
                <div className="relative h-1 rounded-full mt-1 overflow-hidden bg-gradient-to-r from-[var(--color-danger)] via-[var(--color-warning)] to-[var(--color-success)]">
                  <div
                    className="absolute -top-0.5 -bottom-0.5 w-0.5 bg-white transition-[left] duration-500"
                    style={{ left: `${Math.min(Math.max(p.buffer_pct, 0), 100)}%` }}
                  />
                </div>
              </>
            ) : (
              <span className="text-[var(--color-fg-faint)] text-[10px] uppercase tracking-wider">
                cross-shared
              </span>
            )}
          </div>
          <RowKebab p={p} />
        </div>
      </td>
    </motion.tr>
  );
}

/* ─────────────── Quick Action Menu (kebab) ─────────────── */
function RowKebab({ p }: { p: Position }) {
  const copy = (text: string, label: string) => {
    navigator.clipboard
      .writeText(text)
      .then(() => toast.success(`${label} copied`, { description: text }))
      .catch(() => toast.error("Copy failed"));
  };
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          onClick={(e) => e.stopPropagation()}
          className="opacity-0 group-hover:opacity-100 focus:opacity-100 transition w-6 h-6 rounded-[var(--radius-sm)] flex items-center justify-center text-[var(--color-fg-subtle)] hover:bg-white/10 hover:text-[var(--color-fg)]"
          aria-label="Row actions"
        >
          <MoreHorizontal size={14} />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={4}
        onClick={(e) => e.stopPropagation()}
        className="min-w-[200px] p-1"
      >
        <ActionItem
          icon={<ExternalLink size={12} />}
          label="Open in MEXC"
          onClick={() =>
            window.open(`https://www.mexc.com/exchange/${p.symbol.replace("_", "_")}`, "_blank")
          }
        />
        <div className="h-px bg-[var(--color-border)]/40 my-1" />
        <ActionItem
          icon={<Copy size={12} />}
          label="Copy symbol"
          hint={p.symbol}
          onClick={() => copy(p.symbol, "Symbol")}
        />
        <ActionItem
          icon={<Copy size={12} />}
          label="Copy entry price"
          hint={String(p.entry)}
          onClick={() => copy(String(p.entry), "Entry")}
        />
        {p.tp_price && (
          <ActionItem
            icon={<Copy size={12} />}
            label="Copy nearest TP"
            hint={String(p.tp_price)}
            onClick={() => copy(String(p.tp_price), "TP")}
          />
        )}
        {p.sl_price && (
          <ActionItem
            icon={<Copy size={12} />}
            label="Copy SL"
            hint={String(p.sl_price)}
            onClick={() => copy(String(p.sl_price), "SL")}
          />
        )}
        {p.liq_price && (
          <ActionItem
            icon={<Copy size={12} />}
            label="Copy liq price"
            hint={String(p.liq_price)}
            onClick={() => copy(String(p.liq_price), "Liq")}
          />
        )}
        <ActionItem
          icon={<Copy size={12} />}
          label="Copy position ID"
          hint={String(p.position_id)}
          onClick={() => copy(String(p.position_id), "Position ID")}
        />
      </PopoverContent>
    </Popover>
  );
}

function ActionItem({
  icon,
  label,
  hint,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  hint?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-[var(--radius-sm)] text-xs text-[var(--color-fg)] hover:bg-white/5 transition"
    >
      <span className="text-[var(--color-fg-subtle)] shrink-0">{icon}</span>
      <span className="flex-1 text-left">{label}</span>
      {hint && (
        <span className="text-[10px] text-[var(--color-fg-faint)] font-mono truncate max-w-[80px]">
          {hint}
        </span>
      )}
    </button>
  );
}
