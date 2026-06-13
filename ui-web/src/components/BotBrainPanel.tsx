import {
  Brain,
  Layers,
  Gauge,
  Compass,
  Target,
  ShieldCheck,
  Rocket,
  Activity,
  TrendingUp,
  TrendingDown,
  Minus,
  CheckCircle2,
  Clock,
} from "lucide-react";
import { useScalpScanner } from "@/hooks/useSnapshot";
import { CoinIcon } from "@/components/ui/CoinIcon";
import { cn } from "@/lib/cn";
import type { ScalpEval } from "@/types/position";

interface Rule {
  icon: typeof Brain;
  title: string;
  desc: string;
}
const RULES: Rule[] = [
  { icon: Layers, title: "Confluence Multi-Indikator", desc: "Gabungan RSI multi-TF, DMI, divergence, SMC, support/resistance & orderflow jadi satu skor." },
  { icon: Gauge, title: "Skor Konviksi Tinggi", desc: "Cuma entry kalau confluence score lewat ambang — sinyal kuat & matang, bukan tebakan." },
  { icon: Compass, title: "Arah Multi-Timeframe", desc: "Arah LONG/SHORT dikonfirmasi lintas timeframe (15m–1d), bukan dari 1 candle." },
  { icon: Target, title: "TP/SL ATR 4h (R:R ~1.6)", desc: "Target & stop disesuaikan volatilitas koin; risk per entry tetap dibatasi 3%." },
  { icon: ShieldCheck, title: "Trailing / Breakeven SL", desc: "Profit dikunci begitu harga jalan ≥35% menuju TP (exit TRAIL+)." },
  { icon: Rocket, title: "Auto Take-Profit ROI", desc: "Bank profit otomatis saat cuan ≥ target % dari modal." },
];

function DirIcon({ d }: { d: ScalpEval["direction"] }) {
  if (d === "LONG") return <TrendingUp size={13} className="text-[var(--color-success)]" />;
  if (d === "SHORT") return <TrendingDown size={13} className="text-[var(--color-danger)]" />;
  return <Minus size={13} className="text-[var(--color-fg-faint)]" />;
}

function VerdictBadge({ e }: { e: ScalpEval }) {
  if (e.bias === "long")
    return (
      <span className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] bg-[var(--color-success-soft)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--color-success)]">
        <CheckCircle2 size={11} /> LONG
      </span>
    );
  if (e.bias === "short")
    return (
      <span className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] bg-[var(--color-danger-soft)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--color-danger)]">
        <CheckCircle2 size={11} /> SHORT
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-[var(--radius-sm)] bg-[var(--color-bg-elev-2)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--color-fg-muted)]">
      <Clock size={11} /> NUNGGU
    </span>
  );
}

function ScoreBar({ score, threshold }: { score: number; threshold: number }) {
  const pct = Math.max(0, Math.min(100, score));
  const color = score >= threshold ? "var(--color-success)" : score >= threshold * 0.7 ? "var(--color-warning)" : "var(--color-fg-muted)";
  return (
    <div className="flex items-center justify-end gap-1.5">
      <div className="relative h-1.5 w-12 overflow-hidden rounded-full bg-[var(--color-bg-elev-2)] ring-1 ring-[var(--color-border)]">
        <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="w-7 text-right text-xs font-bold tabular-nums" style={{ color }}>
        {Math.round(score)}
      </span>
    </div>
  );
}

export function BotBrainPanel() {
  const { data, isLoading } = useScalpScanner();
  const items = data?.items ?? [];

  return (
    <div className="space-y-4">
      {/* Strategy rules */}
      <div className="page-panel p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Brain size={16} className="text-[var(--color-accent)]" />
          <h3 className="text-sm font-bold text-[var(--color-fg)]">Otak Bot — Cara Entry</h3>
          <span className="text-[11px] text-[var(--color-fg-faint)]">
            entry matang berbasis confluence (riset multi-indikator)
          </span>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {RULES.map((r) => (
            <div
              key={r.title}
              className="flex gap-2.5 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-elev)] p-2.5"
            >
              <r.icon size={15} className="mt-0.5 shrink-0 text-[var(--color-accent)]" />
              <div className="min-w-0">
                <div className="text-[12px] font-semibold text-[var(--color-fg)]">{r.title}</div>
                <div className="text-[11px] leading-snug text-[var(--color-fg-faint)]">{r.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Live confluence scanner */}
      <div className="page-panel p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Activity size={15} className="text-[var(--color-accent)]" />
          <h3 className="text-sm font-bold text-[var(--color-fg)]">Scanner Confluence Live</h3>
          <span className="text-[11px] text-[var(--color-fg-faint)]">
            {data ? `${data.scanned} koin dipindai · ${data.ready} layak entry (skor ≥ ${data.min_score})` : "memindai…"}
          </span>
        </div>

        {isLoading && !data ? (
          <div className="space-y-1.5">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-9 animate-pulse rounded-[var(--radius-md)] bg-[var(--color-bg-elev-2)]" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="py-6 text-center text-[12px] text-[var(--color-fg-faint)]">
            Belum ada data scanner (analitik sedang dihitung).
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-left text-[10px] font-bold uppercase tracking-wider text-[var(--color-fg-faint)]">
                  <th className="px-2 py-2">Koin</th>
                  <th className="px-2 py-2 text-center" title="Arah sinyal lintas timeframe">Arah</th>
                  <th className="px-2 py-2 text-right" title="Confluence score 0–100 (≥68 = layak entry)">Skor</th>
                  <th className="px-2 py-2 text-right" title="Skor sisi LONG / SHORT">L / S</th>
                  <th className="px-2 py-2 text-right" title="Volatilitas ATR 4h">ATR%</th>
                  <th className="px-2 py-2 text-center">Verdict</th>
                  <th className="px-2 py-2">Alasan (faktor confluence)</th>
                </tr>
              </thead>
              <tbody>
                {items.map((e) => (
                  <tr
                    key={e.symbol}
                    className={cn(
                      "border-b border-[var(--color-border)]/50",
                      e.bias ? "bg-[var(--color-accent-soft)]/30" : "",
                    )}
                  >
                    <td className="px-2 py-1.5">
                      <div className="flex items-center gap-2">
                        <CoinIcon coin={e.coin} iconUrl={e.icon_url} size={20} />
                        <span className="text-[12px] font-semibold text-[var(--color-fg)]">{e.coin}</span>
                      </div>
                    </td>
                    <td className="px-2 py-1.5">
                      <div className="flex justify-center">
                        <DirIcon d={e.direction} />
                      </div>
                    </td>
                    <td className="px-2 py-1.5">
                      <ScoreBar score={e.confluence_score} threshold={data?.min_score ?? 55} />
                    </td>
                    <td className="px-2 py-1.5 text-right text-[11px] tabular-nums">
                      <span className="text-[var(--color-success)]">{Math.round(e.score_long)}</span>
                      <span className="text-[var(--color-fg-faint)]"> / </span>
                      <span className="text-[var(--color-danger)]">{Math.round(e.score_short)}</span>
                    </td>
                    <td className="px-2 py-1.5 text-right text-xs tabular-nums text-[var(--color-fg-subtle)]">
                      {e.atr_pct}%
                    </td>
                    <td className="px-2 py-1.5 text-center">
                      <VerdictBadge e={e} />
                    </td>
                    <td className="px-2 py-1.5 text-[11px] text-[var(--color-fg-faint)]">{e.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
