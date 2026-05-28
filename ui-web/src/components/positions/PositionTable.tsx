import { useMemo, Fragment } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { PositionRow } from "./PositionRow";
import { ExpandedDetail } from "./ExpandedDetail";
import { useUiStore, type SortKey } from "@/store/ui";
import type { Position } from "@/types/position";
import { cn } from "@/lib/cn";

const ACC_COLOR_TO_OKLCH: Record<string, string> = {
  violet: "oklch(72% 0.18 280)",
  emerald: "oklch(78% 0.17 165)",
  sky: "oklch(75% 0.13 220)",
  amber: "oklch(80% 0.17 75)",
  rose: "oklch(70% 0.22 25)",
  cyan: "oklch(80% 0.13 210)",
  fuchsia: "oklch(72% 0.22 320)",
  lime: "oklch(85% 0.18 130)",
};

function secColor(c: string): string {
  return ACC_COLOR_TO_OKLCH[c] ?? ACC_COLOR_TO_OKLCH.violet;
}

interface PositionTableProps {
  positions: Position[];
}

const COLUMNS: Array<{ key: SortKey; label: string; sub?: string; align?: "left" | "right" }> = [
  { key: "no", label: "#", align: "left" },
  { key: "symbol", label: "Account", sub: "category", align: "left" },
  { key: "coin", label: "Aset", align: "left" },
  { key: "side", label: "Side · Lev", align: "left" },
  { key: "price", label: "Mark Price", sub: "entry · Δ%", align: "right" },
  { key: "pnl_pct_lev", label: "PnL", sub: "USDT · % lev", align: "right" },
  { key: "margin", label: "Margin", sub: "notional", align: "right" },
  { key: "tp_price", label: "TP", sub: "Δ% · legs", align: "right" },
  { key: "sl_price", label: "SL", sub: "Δ%", align: "right" },
  { key: "margin_ratio", label: "Mgn Ratio", sub: "liq price", align: "right" },
  { key: "buffer_pct", label: "Buffer→Liq", sub: "% to liquidation", align: "right" },
];

export function PositionTable({ positions }: PositionTableProps) {
  const sortKey = useUiStore((s) => s.sortKey);
  const sortDir = useUiStore((s) => s.sortDir);
  const setSort = useUiStore((s) => s.setSort);
  const expanded = useUiStore((s) => s.expanded);
  const toggleExpand = useUiStore((s) => s.toggleExpand);
  const groupByAccount = useUiStore((s) => s.groupByAccount);

  const sorted = useMemo(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    const arr = [...positions].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "string" && typeof bv === "string") return av.localeCompare(bv) * dir;
      return ((av as number) - (bv as number)) * dir;
    });
    if (groupByAccount) {
      // Stable secondary sort by account_name
      arr.sort((a, b) => a.account_name.localeCompare(b.account_name));
    }
    return arr;
  }, [positions, sortKey, sortDir, groupByAccount]);

  // Group sections (kalau groupByAccount true)
  const sections = useMemo(() => {
    if (!groupByAccount) return null;
    const groups = new Map<
      string,
      { account_id: string; account_name: string; account_color: string; items: Position[] }
    >();
    for (const p of sorted) {
      const key = p.account_id;
      if (!groups.has(key)) {
        groups.set(key, {
          account_id: p.account_id,
          account_name: p.account_name,
          account_color: p.account_color,
          items: [],
        });
      }
      groups.get(key)!.items.push(p);
    }
    return Array.from(groups.values());
  }, [sorted, groupByAccount]);

  if (positions.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.34, 1.4, 0.4, 1] }}
      className="page-panel p-12 text-center"
      >
        <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-[var(--color-accent-soft)] ring-1 ring-[var(--color-accent)]/30 flex items-center justify-center">
          <motion.div
            animate={{ scale: [1, 1.15, 1], opacity: [0.5, 1, 0.5] }}
            transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }}
            className="w-2 h-2 rounded-full bg-[var(--color-accent)]"
          />
        </div>
        <div className="text-sm font-medium text-[var(--color-fg)] mb-1">
          No active positions
        </div>
        <p className="text-[11px] text-[var(--color-fg-subtle)] max-w-xs mx-auto">
          Open a position di MEXC, akan muncul otomatis di sini dalam beberapa detik.
        </p>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.34, 1.4, 0.4, 1], delay: 0.2 }}
      className="page-panel overflow-hidden"
    >
      <div className="data-table-scroll">
      <table className="data-table w-full text-sm">
        <thead className="bg-[var(--color-bg-elev-2)] text-[var(--color-fg-subtle)] text-[11px] uppercase tracking-wider font-medium">
          <tr>
            {COLUMNS.map((c) => {
              const isActive = sortKey === c.key;
              return (
                <th
                  key={c.key}
                  className={cn(
                    "px-3 py-3 cursor-pointer select-none transition hover:text-[var(--color-fg)]",
                    c.align === "right" ? "text-right" : "text-left",
                    isActive && "text-[var(--color-accent)]",
                  )}
                  onClick={() => setSort(c.key)}
                >
                  <div
                    className={cn(
                      "flex items-center gap-1",
                      c.align === "right" && "justify-end",
                    )}
                  >
                    <span>{c.label}</span>
                    {isActive &&
                      (sortDir === "desc" ? (
                        <ArrowDown size={9} className="text-[var(--color-accent)]" />
                      ) : (
                        <ArrowUp size={9} className="text-[var(--color-accent)]" />
                      ))}
                  </div>
                  {c.sub && (
                    <div className="text-[var(--color-fg-faint)] normal-case font-normal">
                      {c.sub}
                    </div>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          <AnimatePresence initial={false} mode="popLayout">
            {groupByAccount && sections
              ? sections.flatMap((sec, secIdx) => {
                  const sectionRows: React.ReactNode[] = [
                    <tr key={`hdr-${sec.account_id}`} className="bg-[var(--color-bg-elev-2)]/50">
                      <td
                        colSpan={COLUMNS.length}
                        className="px-3 py-2 border-t border-[var(--color-border)]"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2.5">
                            <span
                              className="w-2 h-2 rounded-full"
                              style={{ background: secColor(sec.account_color) }}
                            />
                            <span className="text-[11px] font-semibold tracking-wide">
                              {sec.account_name}
                            </span>
                            <span className="text-[10px] text-[var(--color-fg-faint)] font-mono">
                              {sec.account_id}
                            </span>
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-[var(--color-surface)] text-[var(--color-fg-muted)] uppercase tracking-wider font-semibold ring-1 ring-[var(--color-border)]">
                              {sec.items.length} pos
                            </span>
                          </div>
                          <span className="text-[10px] text-[var(--color-fg-faint)] num">
                            net {sec.items.reduce((s, p) => s + p.pnl_usdt, 0) >= 0 ? "+" : ""}
                            {sec.items.reduce((s, p) => s + p.pnl_usdt, 0).toFixed(4)} USDT
                          </span>
                        </div>
                      </td>
                    </tr>,
                  ];
                  sec.items.forEach((p, idx) => {
                    const globalIdx = secIdx * 1000 + idx;
                    const isExpanded = expanded.has(p.position_id);
                    sectionRows.push(
                      <Fragment key={p.position_id}>
                        <PositionRow
                          p={p}
                          index={globalIdx}
                          expanded={isExpanded}
                          onToggle={() => toggleExpand(p.position_id)}
                        />
                        <AnimatePresence initial={false}>
                          {isExpanded && (
                            <motion.tr
                              key="exp"
                              initial={{ opacity: 0 }}
                              animate={{ opacity: 1 }}
                              exit={{ opacity: 0 }}
                              transition={{ duration: 0.28 }}
                            >
                              <td
                                colSpan={COLUMNS.length}
                                className="p-0 border-t border-[var(--color-border)]"
                              >
                                <motion.div
                                  initial={{ height: 0, opacity: 0 }}
                                  animate={{ height: "auto", opacity: 1 }}
                                  exit={{ height: 0, opacity: 0 }}
                                  transition={{
                                    height: { type: "spring", stiffness: 220, damping: 28, mass: 0.7 },
                                    opacity: { duration: 0.25 },
                                  }}
                                  className="overflow-hidden"
                                >
                                  <ExpandedDetail p={p} />
                                </motion.div>
                              </td>
                            </motion.tr>
                          )}
                        </AnimatePresence>
                      </Fragment>,
                    );
                  });
                  return sectionRows;
                })
              : sorted.map((p, idx) => {
                  const isExpanded = expanded.has(p.position_id);
                  return (
                    <Fragment key={p.position_id}>
                      <PositionRow
                        p={p}
                        index={idx}
                        expanded={isExpanded}
                        onToggle={() => toggleExpand(p.position_id)}
                      />
                      <AnimatePresence initial={false}>
                        {isExpanded && (
                          <motion.tr
                            key="exp"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            transition={{ duration: 0.28 }}
                          >
                            <td
                              colSpan={COLUMNS.length}
                              className="p-0 border-t border-[var(--color-border)]"
                            >
                              <motion.div
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: "auto", opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                transition={{
                                  height: { type: "spring", stiffness: 220, damping: 28, mass: 0.7 },
                                  opacity: { duration: 0.25 },
                                }}
                                className="overflow-hidden"
                              >
                                <ExpandedDetail p={p} />
                              </motion.div>
                            </td>
                          </motion.tr>
                        )}
                      </AnimatePresence>
                    </Fragment>
                  );
                })}
          </AnimatePresence>
        </tbody>
      </table>
      </div>
    </motion.div>
  );
}
