import { useMemo } from "react";
import { motion } from "motion/react";
import { fmtPct, fmtPrice } from "@/lib/format";
import type { Position, SRLevel } from "@/types/position";
import { cn } from "@/lib/cn";

type Kind =
  | "tp"
  | "resistance"
  | "pivot"
  | "support"
  | "entry"
  | "mark"
  | "sl"
  | "liq";

interface Level {
  key: string;
  kind: Kind;
  price: number;
  label: string;
  distance_pct: number;
}

interface VerticalLadderProps {
  p: Position;
}

const ACTION_ZONE_WINDOW_PCT = 8; // levels within ±8% of mark counted as "action zone"
const MOONSHOT_THRESHOLD_PCT = 30; // TP/SL >30% away = moonshot, shown as compact badge not full row

/** Build full level list from position. */
function buildLevels(p: Position): Level[] {
  const out: Level[] = [];
  (p.tp_all || []).forEach((tp, i) =>
    out.push({
      key: `tp${i}`,
      kind: "tp",
      price: tp,
      label: `TP${i + 1}`,
      distance_pct: distFromMark(p, tp),
    }),
  );
  (p.sr_levels || []).forEach((sr: SRLevel) =>
    out.push({
      key: sr.label,
      kind:
        sr.kind === "support"
          ? "support"
          : sr.kind === "resistance"
            ? "resistance"
            : "pivot",
      price: sr.price,
      label: sr.label,
      distance_pct: sr.distance_pct,
    }),
  );
  out.push({
    key: "entry",
    kind: "entry",
    price: p.entry,
    label: "ENTRY",
    distance_pct: distFromMark(p, p.entry),
  });
  out.push({
    key: "mark",
    kind: "mark",
    price: p.price,
    label: "LIVE",
    distance_pct: 0,
  });
  (p.sl_all || []).forEach((sl, i) =>
    out.push({
      key: `sl${i}`,
      kind: "sl",
      price: sl,
      label: p.sl_count > 1 ? `SL${i + 1}` : "SL",
      distance_pct: distFromMark(p, sl),
    }),
  );
  if (p.liq_price)
    out.push({
      key: "liq",
      kind: "liq",
      price: p.liq_price,
      label: "LIQ",
      distance_pct: distFromMark(p, p.liq_price),
    });
  return out;
}

function distFromMark(p: Position, target: number): number {
  if (!p.price) return 0;
  const raw = ((target - p.price) / p.price) * 100;
  return p.side === "LONG" ? raw : -raw;
}

/* ─────────────── Color helpers ─────────────── */
function colorFor(k: Kind): string {
  switch (k) {
    case "tp":
      return "var(--color-success)";
    case "support":
      return "var(--color-success)";
    case "resistance":
      return "var(--color-danger)";
    case "pivot":
      return "var(--color-fg-muted)";
    case "entry":
      return "var(--color-fg)";
    case "mark":
      return "var(--color-accent)";
    case "sl":
      return "var(--color-danger)";
    case "liq":
      return "var(--color-danger)";
  }
}

function isDashed(k: Kind): boolean {
  return k === "support" || k === "resistance" || k === "pivot";
}

/* ─────────────── Main component ─────────────── */
export function VerticalLadder({ p }: VerticalLadderProps) {
  const allLevels = useMemo(() => buildLevels(p), [p]);

  // Partition into 3 bands + moonshot separate bucket
  const { profitLevels, actionLevels, lossLevels, moonshotProfit, moonshotLoss } = useMemo(() => {
    const profitArr: Level[] = [];
    const actionArr: Level[] = [];
    const lossArr: Level[] = [];
    const moonProf: Level[] = [];
    const moonLoss: Level[] = [];

    for (const lv of allLevels) {
      if (lv.kind === "mark") {
        actionArr.push(lv);
        continue;
      }
      if (lv.kind === "entry") {
        actionArr.push(lv);
        continue;
      }
      // Moonshot: TP or SL extremely far away
      if ((lv.kind === "tp" || lv.kind === "sl") && Math.abs(lv.distance_pct) > MOONSHOT_THRESHOLD_PCT) {
        if (lv.distance_pct > 0) moonProf.push(lv);
        else moonLoss.push(lv);
        continue;
      }
      // Far zones
      if (lv.kind === "tp" || (lv.kind === "resistance" && lv.distance_pct > ACTION_ZONE_WINDOW_PCT)) {
        profitArr.push(lv);
        continue;
      }
      if (lv.kind === "liq" || lv.kind === "sl" || (lv.kind === "support" && lv.distance_pct < -ACTION_ZONE_WINDOW_PCT)) {
        lossArr.push(lv);
        continue;
      }
      // Near zone S/R go into action
      if (Math.abs(lv.distance_pct) <= ACTION_ZONE_WINDOW_PCT) {
        actionArr.push(lv);
      } else {
        if (lv.distance_pct > 0) profitArr.push(lv);
        else lossArr.push(lv);
      }
    }

    profitArr.sort((a, b) => b.price - a.price);
    actionArr.sort((a, b) => b.price - a.price);
    lossArr.sort((a, b) => b.price - a.price);
    moonProf.sort((a, b) => Math.abs(a.distance_pct) - Math.abs(b.distance_pct));
    moonLoss.sort((a, b) => Math.abs(a.distance_pct) - Math.abs(b.distance_pct));

    if (p.side === "SHORT") {
      profitArr.reverse();
      actionArr.reverse();
      lossArr.reverse();
    }

    return {
      profitLevels: profitArr,
      actionLevels: actionArr,
      lossLevels: lossArr,
      moonshotProfit: moonProf,
      moonshotLoss: moonLoss,
    };
  }, [allLevels, p.side]);

  const isCrossShared = p.liq_price == null;

  // Compute analytical context
  const nearestResAbove = actionLevels.find(
    (l) =>
      (l.kind === "resistance" || l.kind === "tp") &&
      l.distance_pct > 0,
  );
  const nearestSupBelow = actionLevels.find(
    (l) =>
      (l.kind === "support" || l.kind === "sl") &&
      l.distance_pct < 0,
  );
  const upsideRoom = nearestResAbove?.distance_pct ?? null;
  const downsideRoom = nearestSupBelow ? Math.abs(nearestSupBelow.distance_pct) : null;

  // Bias: more upside room than downside = "bullish positioned", reverse = "bearish positioned"
  let bias: "bullish" | "bearish" | "neutral" = "neutral";
  if (upsideRoom != null && downsideRoom != null) {
    const ratio = upsideRoom / downsideRoom;
    if (ratio >= 1.5) bias = "bullish";
    else if (ratio <= 0.66) bias = "bearish";
  }

  return (
    <div className="inner-card overflow-hidden">
      {/* Header with analytical context */}
      <div className="px-4 py-3 border-b border-[var(--color-border)]">
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-2.5">
            <span className="ui-section-title">
              Aksi Harga
            </span>
            <span className="text-[11px] text-[var(--color-fg-faint)] font-mono">
              · {p.symbol}
            </span>
          </div>
          {/* Bias chip */}
          <span
            className="text-[9px] uppercase tracking-wider font-bold px-2 py-0.5 rounded-[var(--radius-sm)] ring-1"
            style={{
              color:
                bias === "bullish"
                  ? "var(--color-success)"
                  : bias === "bearish"
                    ? "var(--color-danger)"
                    : "var(--color-fg-muted)",
              background:
                bias === "bullish"
                  ? "var(--color-success-soft)"
                  : bias === "bearish"
                    ? "var(--color-danger-soft)"
                    : "var(--color-surface)",
              borderColor:
                bias === "bullish"
                  ? "color-mix(in oklch, var(--color-success) 40%, transparent)"
                  : bias === "bearish"
                    ? "color-mix(in oklch, var(--color-danger) 40%, transparent)"
                    : "var(--color-border)",
            }}
          >
            {bias === "bullish" ? "↑ RUANG NAIK" : bias === "bearish" ? "↓ RUANG TURUN" : "SEIMBANG"}
          </span>
        </div>

        {/* Up/down room context */}
        <div className="flex items-center gap-2 text-[10px]">
          <div className="flex-1 flex items-center gap-1.5">
            <span className="text-[var(--color-fg-faint)] uppercase tracking-wider">↑</span>
            <span className="text-[var(--color-success)] num font-medium">
              {upsideRoom != null ? `+${upsideRoom.toFixed(2)}%` : "—"}
            </span>
            <span className="text-[var(--color-fg-faint)] truncate">
              {nearestResAbove ? `ke ${nearestResAbove.label}` : "tidak ada target"}
            </span>
          </div>
          <div className="w-px h-3 bg-[var(--color-border)]" />
          <div className="flex-1 flex items-center gap-1.5 justify-end">
            <span className="text-[var(--color-fg-faint)] truncate">
              {nearestSupBelow ? `ke ${nearestSupBelow.label}` : "tidak ada support"}
            </span>
            <span className="text-[var(--color-danger)] num font-medium">
              {downsideRoom != null ? `-${downsideRoom.toFixed(2)}%` : "—"}
            </span>
            <span className="text-[var(--color-fg-faint)] uppercase tracking-wider">↓</span>
          </div>
        </div>

        {/* Visual scale: where mark is in upside-vs-downside range */}
        {upsideRoom != null && downsideRoom != null && (
          <div className="mt-2">
            <div className="relative h-1 rounded-full bg-gradient-to-r from-[var(--color-danger)]/40 via-white/10 to-[var(--color-success)]/40 overflow-hidden">
              <motion.div
                initial={false}
                animate={{
                  left: `${50 - (downsideRoom / (upsideRoom + downsideRoom)) * 50 + 50 * (upsideRoom / (upsideRoom + downsideRoom))}%`,
                }}
                transition={{ duration: 0.6, ease: [0.34, 1.4, 0.4, 1] }}
                className="absolute -top-0.5 -bottom-0.5 w-0.5 bg-[var(--color-accent)]"
                style={{ boxShadow: "0 0 6px var(--color-accent)" }}
              />
            </div>
          </div>
        )}
      </div>

      {/* PROFIT ZONE band */}
      <Band
        label="Zona Untung"
        zone="profit"
        emptyText="Belum ada take profit terpasang"
        accessory={
          moonshotProfit.length > 0 ? (
            <MoonshotBadge levels={moonshotProfit} side="profit" />
          ) : null
        }
      >
        {profitLevels.map((lv) => (
          <LevelRow key={lv.key} lv={lv} />
        ))}
      </Band>

      {/* ACTION ZONE band */}
      <Band label="Zona Aksi" zone="action" emptyText="—" highlight>
        <ActionZoneLevels levels={actionLevels} p={p} />
      </Band>

      {/* LOSS ZONE band */}
      <Band
        label="Zona Rugi"
        zone="loss"
        emptyText={
          isCrossShared
            ? "Harga liq dibagi rata dengan equity akun (cross margin)"
            : "Belum ada stop loss atau likuidasi yang terpasang"
        }
        accessory={
          moonshotLoss.length > 0 ? (
            <MoonshotBadge levels={moonshotLoss} side="loss" />
          ) : null
        }
      >
        {lossLevels.map((lv) => (
          <LevelRow key={lv.key} lv={lv} />
        ))}
        {isCrossShared && lossLevels.length === 0 && (
          <CrossSharedPill />
        )}
      </Band>
    </div>
  );
}

/* ─────────────── Moonshot badge — collapses far TP/SL into a single pill ─────────────── */
function MoonshotBadge({
  levels,
  side,
}: {
  levels: Level[];
  side: "profit" | "loss";
}) {
  if (levels.length === 0) return null;
  const tone = side === "profit" ? "var(--color-warning)" : "var(--color-danger)";
  const closest = levels[0];
  return (
    <span
      className="inline-flex items-center gap-1 text-[8px] uppercase tracking-wider px-1.5 py-0.5 rounded-full ring-1 font-bold"
      style={{
        color: tone,
        background: `color-mix(in oklch, ${tone} 12%, transparent)`,
        borderColor: `color-mix(in oklch, ${tone} 30%, transparent)`,
      }}
      title={levels
        .map((l) => `${l.label} @ ${fmtPrice(l.price)} (${fmtPct(l.distance_pct)})`)
        .join("\n")}
    >
      🌙 {levels.length === 1 ? closest.label : `${levels.length} moonshot`}
      <span className="num font-semibold opacity-70">{fmtPct(closest.distance_pct)}</span>
    </span>
  );
}

/* ─────────────── Band container ─────────────── */
function Band({
  label,
  zone,
  emptyText,
  highlight = false,
  accessory,
  children,
}: {
  label: string;
  zone: "profit" | "action" | "loss";
  emptyText?: string;
  highlight?: boolean;
  accessory?: React.ReactNode;
  children: React.ReactNode;
}) {
  const childArr = Array.isArray(children) ? children : [children];
  const hasContent = childArr.flat().filter(Boolean).length > 0;

  const bgClass =
    zone === "profit"
      ? "bg-[color-mix(in_oklch,var(--color-success)_4%,transparent)]"
      : zone === "loss"
        ? "bg-[color-mix(in_oklch,var(--color-danger)_4%,transparent)]"
        : "bg-[color-mix(in_oklch,var(--color-accent)_4%,transparent)]";

  const dotColor =
    zone === "profit"
      ? "bg-[var(--color-success)]"
      : zone === "loss"
        ? "bg-[var(--color-danger)]"
        : "bg-[var(--color-accent)]";

  return (
    <div
      className={cn(
        "border-b border-[var(--color-border)] last:border-b-0 relative",
        bgClass,
        highlight && "ring-1 ring-inset ring-[var(--color-accent)]/20",
      )}
    >
      <div className="px-3 pt-2 pb-1 flex items-center gap-1.5">
        <span className={cn("w-1.5 h-1.5 rounded-full", dotColor)} />
        <span className="text-[9px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
          {label}
        </span>
        {accessory && <span className="ml-auto">{accessory}</span>}
      </div>
      <div className="px-1 pb-1">
        {hasContent ? (
          <div className="divide-y divide-[var(--color-border)]/30">{children}</div>
        ) : (
          <div className="px-3 py-2 text-[11px] text-[var(--color-fg-faint)] italic">
            {emptyText}
          </div>
        )}
      </div>
    </div>
  );
}

/* ─────────────── Action zone with sliding mark line ─────────────── */
function ActionZoneLevels({ levels, p }: { levels: Level[]; p: Position }) {
  // Sort already done, mark goes special highlight
  return (
    <div>
      {levels.map((lv) =>
        lv.kind === "mark" ? (
          <MarkRow key={lv.key} lv={lv} p={p} />
        ) : (
          <LevelRow key={lv.key} lv={lv} subtle={lv.kind !== "entry"} />
        ),
      )}
    </div>
  );
}

/* ─────────────── Single level row ─────────────── */
function LevelRow({ lv, subtle = false }: { lv: Level; subtle?: boolean }) {
  const color = colorFor(lv.kind);
  const dashed = isDashed(lv.kind);

  return (
    <div className="grid grid-cols-[20px_1fr_auto_72px] items-center gap-3 px-3 py-1.5 transition row-hover">
      <div className="flex items-center justify-center">
        {dashed ? (
          <span
            className="w-3 h-px"
            style={{ borderTop: `1px dashed ${color}`, opacity: 0.55 }}
          />
        ) : lv.kind === "entry" ? (
          <span
            className="w-2 h-2 rotate-45 rounded-sm"
            style={{ background: color }}
          />
        ) : (
          <span
            className="w-2 h-2 rounded-full"
            style={{
              background: color,
              boxShadow: lv.kind === "liq" || lv.kind === "tp" ? `0 0 5px ${color}` : "none",
            }}
          />
        )}
      </div>
      <span
        className={cn("num text-[11px]", subtle && "opacity-75")}
        style={{ color }}
      >
        {fmtPrice(lv.price)}
      </span>
      <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-muted)]">
        {lv.label}
        {lv.kind === "support" && (
          <span className="text-[var(--color-fg-faint)]"> · sup</span>
        )}
        {lv.kind === "resistance" && (
          <span className="text-[var(--color-fg-faint)]"> · res</span>
        )}
        {lv.kind === "pivot" && (
          <span className="text-[var(--color-fg-faint)]"> · piv</span>
        )}
      </span>
      <span
        className="text-right text-[10px] num"
        style={{
          color:
            lv.distance_pct > 0
              ? "var(--color-success)"
              : lv.distance_pct < 0
                ? "var(--color-danger)"
                : "var(--color-fg-muted)",
        }}
      >
        {fmtPct(lv.distance_pct)}
      </span>
    </div>
  );
}

/* ─────────────── Live Mark Row (highlighted, animated) ─────────────── */
function MarkRow({ lv, p }: { lv: Level; p: Position }) {
  return (
    <motion.div
      layout
      initial={false}
      animate={{ opacity: 1 }}
      className="relative grid grid-cols-[20px_1fr_auto_72px] items-center gap-3 px-3 py-2 bg-[var(--color-accent-soft)] ring-1 ring-inset ring-[var(--color-accent)]/30"
    >
      <div className="flex items-center justify-center">
        <span className="relative inline-block w-3 h-3 rounded-full bg-[var(--color-accent)] [animation:pulse-glow_1.4s_ease-in-out_infinite]">
          <span className="absolute inset-0 rounded-full [animation:ghost-ring_2s_ease-out_infinite] bg-[var(--color-accent)]/40" />
        </span>
      </div>
      <motion.span
        key={lv.price}
        initial={{ opacity: 0.5, y: -2 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="num text-[13px] font-bold text-[var(--color-fg)]"
      >
        {fmtPrice(lv.price)}
      </motion.span>
      <span className="text-[10px] uppercase tracking-wider font-bold text-[var(--color-accent)] flex items-center gap-1.5">
        Live
        <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] animate-pulse" />
      </span>
      <span className="text-right text-[11px] num font-semibold text-[var(--color-accent)]">
        {p.price > 0 && p.entry > 0
          ? fmtPct(((p.price - p.entry) / p.entry) * 100 * (p.side === "LONG" ? 1 : -1))
          : "—"}
      </span>
    </motion.div>
  );
}

/* ─────────────── Cross-margin shared liq pill ─────────────── */
function CrossSharedPill() {
  return (
    <div className="px-3 py-2 flex items-center gap-2 text-[10px] text-[var(--color-fg-subtle)]">
      <span className="inline-flex items-center px-2 py-0.5 rounded-[var(--radius-sm)] bg-[var(--color-warning-soft)] text-[var(--color-warning)] ring-1 ring-[var(--color-warning)]/30 font-medium tracking-wider">
        CROSS · SHARED
      </span>
      <span>Liq price ditentukan dari total equity, bukan margin posisi ini saja.</span>
    </div>
  );
}
