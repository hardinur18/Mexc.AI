import { motion, AnimatePresence } from "motion/react";
import { AlertTriangle, Info, ShieldAlert, Target } from "lucide-react";
import type { ActionHint, Position } from "@/types/position";
import { cn } from "@/lib/cn";

function clientHints(p: Position): ActionHint[] {
  const out: ActionHint[] = [];

  if (!p.sl_price) {
    const suggestPrice =
      p.side === "LONG" ? p.entry * 0.92 : p.entry * 1.08;
    out.push({
      level: "danger",
      title: "Stop loss belum diset",
      detail: `Saran: pasang SL di ~${suggestPrice.toFixed(suggestPrice >= 1 ? 2 : 4)} (≈ -8% dari entry) supaya max risk terkontrol.`,
    });
  }

  if (p.buffer_pct !== null && p.buffer_pct < 10) {
    out.push({
      level: "danger",
      title: "Buffer ke liquidation < 10%",
      detail: "DANGER — tambah margin atau close posisi sebelum kena liq.",
    });
  } else if (p.buffer_pct !== null && p.buffer_pct < 25) {
    out.push({
      level: "warning",
      title: "Buffer ke liquidation < 25%",
      detail: "Pertimbangkan turunin leverage atau set SL ketat.",
    });
  }

  if (p.tp_dist_pct !== null && p.tp_dist_pct < 2) {
    out.push({
      level: "success",
      title: "Mendekati TP terdekat",
      detail: `Mark dalam ${p.tp_dist_pct.toFixed(2)}% dari TP — siap-siap partial close.`,
    });
  }

  if (p.margin_ratio > 50) {
    out.push({
      level: "danger",
      title: `Margin ratio tinggi (${p.margin_ratio.toFixed(2)}%)`,
      detail: "Posisi rentan kena liquidation. Add margin urgent.",
    });
  } else if (p.margin_ratio > 20) {
    out.push({
      level: "warning",
      title: `Margin ratio ${p.margin_ratio.toFixed(2)}%`,
      detail: "Mulai naik. Monitor ketat.",
    });
  }

  return out;
}

function iconFor(level: ActionHint["level"]) {
  switch (level) {
    case "danger":
      return <ShieldAlert size={14} />;
    case "warning":
      return <AlertTriangle size={14} />;
    case "success":
      return <Target size={14} />;
    default:
      return <Info size={14} />;
  }
}

function toneFor(level: ActionHint["level"]) {
  switch (level) {
    case "danger":
      return "border-[var(--color-danger)]/40 bg-[var(--color-danger-soft)] text-[var(--color-danger)]";
    case "warning":
      return "border-[var(--color-warning)]/40 bg-[var(--color-warning-soft)] text-[var(--color-warning)]";
    case "success":
      return "border-[var(--color-success)]/40 bg-[var(--color-success-soft)] text-[var(--color-success)]";
    default:
      return "border-[var(--color-info)]/40 bg-[var(--color-info)]/10 text-[var(--color-info)]";
  }
}

interface ActionHintsProps {
  p: Position;
}

export function ActionHints({ p }: ActionHintsProps) {
  const hints = [...clientHints(p), ...(p.hints || [])];

  if (hints.length === 0) {
    return (
      <div className="text-xs text-[var(--color-fg-subtle)] px-3 py-2 rounded-[var(--radius-md)] inner-card">
        <Info size={12} className="inline mr-1" />
        Posisi dalam status normal — tidak ada hint aktif.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <AnimatePresence initial={false}>
        {hints.map((h, i) => (
          <motion.div
            key={h.title + i}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.25, delay: i * 0.04 }}
            className={cn(
              "rounded-[var(--radius-md)] border px-3 py-2 flex items-start gap-2.5",
              toneFor(h.level),
            )}
          >
            <span className="mt-0.5 shrink-0">{iconFor(h.level)}</span>
            <div className="leading-snug">
              <div className="text-xs font-semibold">{h.title}</div>
              {h.detail && (
                <div className="text-[11px] mt-0.5 opacity-90">{h.detail}</div>
              )}
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
