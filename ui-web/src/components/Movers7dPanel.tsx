import { useState } from "react";
import { motion } from "motion/react";
import { Flame, RefreshCw, TrendingDown, TrendingUp } from "lucide-react";
import { useMovers7d } from "@/hooks/useSnapshot";
import type { MoverKind, MoverInterval } from "@/lib/api";
import { useUiStore } from "@/store/ui";
import { CoinIcon } from "@/components/ui/CoinIcon";
import { Sparkline } from "@/components/positions/Sparkline";
import { fmtPct, fmtPrice } from "@/lib/format";
import { cn } from "@/lib/cn";

interface MoverConfig {
  Icon: typeof Flame;
  iconClass: string;
  countLabel: (n: number) => string;
  changeHeader: string;
  empty: string;
  thresholds: { label: string; value: number }[];
}

const CONFIG: Record<MoverKind, MoverConfig> = {
  gainers: {
    Icon: Flame,
    iconClass: "text-[var(--color-warning)]",
    countLabel: (n) => `${n} koin naik`,
    changeHeader: "Naik",
    empty: "Tidak ada koin yang naik di atas ambang ini pada rentang ini.",
    thresholds: [
      { label: "Semua naik", value: 0 },
      { label: "≥5%", value: 5 },
      { label: "≥10%", value: 10 },
      { label: "≥25%", value: 25 },
    ],
  },
  losers: {
    Icon: TrendingDown,
    iconClass: "text-[var(--color-danger)]",
    countLabel: (n) => `${n} koin turun`,
    changeHeader: "Turun",
    empty: "Tidak ada koin yang turun di bawah ambang ini pada rentang ini.",
    thresholds: [
      { label: "Semua turun", value: 0 },
      { label: "≤-5%", value: -5 },
      { label: "≤-10%", value: -10 },
      { label: "≤-25%", value: -25 },
    ],
  },
};

const GRANULARITY: { value: MoverInterval; label: string }[] = [
  { value: "Day1", label: "Harian" },
  { value: "Month1", label: "Bulanan" },
];

const DAILY_PRESETS = [
  { label: "7 Hari", days: 7 },
  { label: "14 Hari", days: 14 },
  { label: "30 Hari", days: 30 },
];
const MONTHLY_PRESETS = [
  { label: "3 Bulan", months: 3 },
  { label: "6 Bulan", months: 6 },
  { label: "12 Bulan", months: 12 },
];

const MAX_DAILY = 31;
const MAX_MONTHLY = 12;
const MONTHS_ID = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];

/* ─── date helpers (browser-local) ─── */
function pad(n: number): string {
  return String(n).padStart(2, "0");
}
function toISODate(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
function toISOMonth(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
}
function addDays(d: Date, n: number): Date {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}
function addMonths(d: Date, n: number): Date {
  const r = new Date(d);
  r.setMonth(r.getMonth() + n);
  return r;
}
/** Uncapped number of daily columns from a start date to today (inclusive). */
function rawDailyPeriods(fromISO: string): number {
  const from = new Date(`${fromISO}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.max(2, Math.round((today.getTime() - from.getTime()) / 86_400_000) + 1);
}
/** Uncapped number of monthly columns from a start month to this month (inclusive). */
function rawMonthlyPeriods(fromISO: string): number {
  const [y, m] = fromISO.split("-").map(Number);
  const now = new Date();
  return Math.max(2, (now.getFullYear() - y) * 12 + (now.getMonth() - (m - 1)) + 1);
}

/* ─── value formatters ─── */
function fmtVol(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}
function changeTone(n: number): string {
  if (n > 0) return "text-[var(--color-success)]";
  if (n < 0) return "text-[var(--color-danger)]";
  return "text-[var(--color-fg-muted)]";
}
function fmtDayPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const dp = Math.abs(n) >= 100 ? 0 : 1;
  return (n > 0 ? "+" : "") + n.toFixed(dp) + "%";
}
function colSubLabel(ts: number, interval: MoverInterval): string {
  const d = new Date(ts);
  if (interval === "Month1") return `${MONTHS_ID[d.getMonth()]} '${pad(d.getFullYear() % 100)}`;
  return `${d.getDate()}/${d.getMonth() + 1}`;
}

type Bias = "long" | "short" | "neutral";
const BIAS_META: Record<Bias, { label: string; badge: string; color: string }> = {
  long: {
    label: "LONG",
    badge: "bg-[var(--color-success-soft)] text-[var(--color-success)]",
    color: "var(--color-success)",
  },
  short: {
    label: "SHORT",
    badge: "bg-[var(--color-danger-soft)] text-[var(--color-danger)]",
    color: "var(--color-danger)",
  },
  neutral: {
    label: "NETRAL",
    badge: "bg-[var(--color-bg-elev-2)] text-[var(--color-fg-muted)]",
    color: "var(--color-fg-muted)",
  },
};

/** Mini gauge: where the current price sits between range low (left) and high (right). */
function PositionGauge({ pos, bias }: { pos: number; bias: Bias }) {
  const color = BIAS_META[bias].color;
  return (
    <div className="flex items-center gap-1.5">
      <div className="relative h-1.5 w-16 overflow-hidden rounded-full bg-[var(--color-bg-elev-2)] ring-1 ring-[var(--color-border)]">
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: `${pos}%`, background: color, opacity: 0.45 }}
        />
        <div
          className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full"
          style={{ left: `${pos}%`, background: color, boxShadow: `0 0 4px ${color}` }}
        />
      </div>
      <span className="text-[10px] tabular-nums text-[var(--color-fg-faint)]">{Math.round(pos)}%</span>
    </div>
  );
}

export function Movers7dPanel({ kind }: { kind: MoverKind }) {
  const cfg = CONFIG[kind];
  const colorScheme = useUiStore((s) => s.theme);
  const [granularity, setGranularity] = useState<MoverInterval>("Day1");
  const [dailyFrom, setDailyFrom] = useState(() => toISODate(addDays(new Date(), -6)));
  const [monthlyFrom, setMonthlyFrom] = useState(() => toISOMonth(addMonths(new Date(), -11)));
  const [threshold, setThreshold] = useState(0);

  const monthly = granularity === "Month1";
  const cap = monthly ? MAX_MONTHLY : MAX_DAILY;
  const rawPeriods = monthly ? rawMonthlyPeriods(monthlyFrom) : rawDailyPeriods(dailyFrom);
  const periods = Math.min(rawPeriods, cap);
  const capped = rawPeriods > cap;

  const { data, isLoading, isError, isFetching, refetch } = useMovers7d(
    kind,
    granularity,
    periods,
    threshold,
  );
  const items = data?.items ?? [];
  // Columns share the same candle boundaries across symbols — use the first row for headers.
  const cols = items[0]?.periods ?? [];
  const colPrefix = monthly ? "B" : "H";
  const rangeLabel = monthly ? `${periods} bulan` : `${periods} hari`;

  return (
    <div className="px-3 pb-3 md:px-4 md:pb-4">
      {/* Toolbar: summary + refresh */}
      <div className="flex flex-wrap items-center justify-between gap-3 py-2.5">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.04em] text-[var(--color-fg-faint)]">
          <cfg.Icon size={13} className={cfg.iconClass} />
          <span>
            {cfg.countLabel(items.length)} · {rangeLabel} · scan {data?.scanned_count ?? 0}
            {data ? ` · ${data.latency_ms}ms` : ""}
          </span>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          title="Muat ulang"
          className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-bg-elev-2)] text-[var(--color-fg-subtle)] transition hover:text-[var(--color-fg)]"
        >
          <RefreshCw size={13} className={isFetching ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Controls: granularity + calendar range + presets */}
      <div className="mb-2 flex flex-wrap items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-elev)] p-1.5">
        {/* Granularity */}
        <div className="inline-flex rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-bg-elev-2)] p-0.5">
          {GRANULARITY.map((g) => (
            <button
              key={g.value}
              type="button"
              onClick={() => setGranularity(g.value)}
              className={cn(
                "h-7 rounded-[var(--radius-xs)] px-2.5 text-xs font-semibold transition",
                granularity === g.value
                  ? "bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                  : "text-[var(--color-fg-subtle)] hover:text-[var(--color-fg)]",
              )}
            >
              {g.label}
            </button>
          ))}
        </div>

        {/* Calendar "from" picker (range ends today) */}
        <label className="flex items-center gap-1.5 text-[11px] font-semibold text-[var(--color-fg-faint)]">
          Dari
          {monthly ? (
            <input
              type="month"
              value={monthlyFrom}
              max={toISOMonth(new Date())}
              onChange={(e) => setMonthlyFrom(e.target.value)}
              style={{ colorScheme }}
              className="h-8 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-bg-elev-2)] px-2 text-xs font-medium text-[var(--color-fg)]"
            />
          ) : (
            <input
              type="date"
              value={dailyFrom}
              max={toISODate(new Date())}
              onChange={(e) => setDailyFrom(e.target.value)}
              style={{ colorScheme }}
              className="h-8 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-bg-elev-2)] px-2 text-xs font-medium text-[var(--color-fg)]"
            />
          )}
          <span className="text-[var(--color-fg-faint)]">s/d hari ini</span>
        </label>

        {/* Range presets */}
        <div className="flex items-center gap-1">
          {monthly
            ? MONTHLY_PRESETS.map((p) => (
                <button
                  key={p.months}
                  type="button"
                  onClick={() => setMonthlyFrom(toISOMonth(addMonths(new Date(), -(p.months - 1))))}
                  className="h-7 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-bg-elev-2)] px-2 text-[11px] font-semibold text-[var(--color-fg-subtle)] transition hover:text-[var(--color-fg)]"
                >
                  {p.label}
                </button>
              ))
            : DAILY_PRESETS.map((p) => (
                <button
                  key={p.days}
                  type="button"
                  onClick={() => setDailyFrom(toISODate(addDays(new Date(), -(p.days - 1))))}
                  className="h-7 rounded-[var(--radius-sm)] border border-[var(--color-border)] bg-[var(--color-bg-elev-2)] px-2 text-[11px] font-semibold text-[var(--color-fg-subtle)] transition hover:text-[var(--color-fg)]"
                >
                  {p.label}
                </button>
              ))}
        </div>

        {/* Threshold filter */}
        <div className="ml-auto flex items-center gap-1">
          {cfg.thresholds.map((t) => (
            <button
              key={t.value}
              type="button"
              onClick={() => setThreshold(t.value)}
              className={cn(
                "h-7 rounded-[var(--radius-sm)] border px-2 text-[11px] font-semibold transition",
                threshold === t.value
                  ? "border-[var(--color-accent-ring)] bg-[var(--color-accent-soft)] text-[var(--color-accent)]"
                  : "border-[var(--color-border)] bg-[var(--color-bg-elev-2)] text-[var(--color-fg-subtle)] hover:text-[var(--color-fg)]",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {capped && (
        <div className="mb-2 text-[11px] text-[var(--color-warning)]">
          Rentang dibatasi {cap} kolom {monthly ? "(maks 12 bulan)" : "(maks 1 bulan harian)"} —
          {monthly ? " perpanjang lewat tahun lain." : " untuk lebih panjang, pakai mode Bulanan."}
        </div>
      )}

      {/* States */}
      {isLoading ? (
        <div className="space-y-1.5">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="h-12 animate-pulse rounded-[var(--radius-md)] bg-[var(--color-bg-elev-2)]"
            />
          ))}
        </div>
      ) : isError ? (
        <div className="glass rounded-xl p-10 text-center text-[13px] text-[var(--color-danger)]">
          Gagal memuat data dari /api/{kind}-7d
        </div>
      ) : items.length === 0 ? (
        <div className="glass rounded-xl p-10 text-center text-[13px] text-[var(--color-fg-faint)]">
          {cfg.empty}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1120px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-[10px] font-bold uppercase tracking-wider text-[var(--color-fg-faint)]">
                <th className="px-2 py-2 font-bold">#</th>
                <th className="px-2 py-2 font-bold">Koin</th>
                <th className="px-2 py-2 text-right font-bold">{cfg.changeHeader}</th>
                <th
                  className="px-2 py-2 font-bold"
                  title="Posisi harga sekarang dalam rentang low–high periode ini. Dekat dasar (0%) → bias LONG (murah), dekat puncak (100%) → bias SHORT (mahal). Mean-reversion, bukan saran finansial."
                >
                  Posisi
                </th>
                {cols.map((d, i) => (
                  <th
                    key={d.ts}
                    className="px-1.5 py-2 text-right font-bold"
                    title={`${colPrefix}${i + 1} — ${colSubLabel(d.ts, granularity)}${i === cols.length - 1 ? (monthly ? " (bulan ini)" : " (hari ini)") : ""}`}
                  >
                    <div className="leading-tight">{colPrefix}{i + 1}</div>
                    <div className="text-[9px] font-medium normal-case text-[var(--color-fg-faint)]">
                      {colSubLabel(d.ts, granularity)}
                    </div>
                  </th>
                ))}
                <th className="px-2 py-2 text-right font-bold">24 Jam</th>
                <th className="px-2 py-2 text-right font-bold">Harga</th>
                <th className="px-2 py-2 text-right font-bold">Vol 24H</th>
                <th className="px-2 py-2 text-right font-bold">Tren</th>
              </tr>
            </thead>
            <tbody>
              {items.map((g, i) => (
                <motion.tr
                  key={g.symbol}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2, delay: Math.min(i * 0.012, 0.3) }}
                  className="border-b border-[var(--color-border)]/50 transition hover:bg-[var(--color-bg-elev-2)]/60"
                >
                  <td className="px-2 py-2 text-xs font-semibold tabular-nums text-[var(--color-fg-faint)]">
                    {g.rank}
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex items-center gap-2.5">
                      <CoinIcon coin={g.coin} iconUrl={g.icon_url} size={26} />
                      <div className="min-w-0">
                        <div className="truncate text-[13px] font-semibold text-[var(--color-fg)]">
                          {g.coin}
                        </div>
                        <div className="truncate text-[10px] text-[var(--color-fg-faint)]">
                          {g.symbol}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-2 py-2 text-right">
                    <span
                      className={cn(
                        "inline-flex items-center gap-1 rounded-[var(--radius-sm)] px-2 py-0.5 text-[13px] font-bold tabular-nums",
                        g.change_pct > 0
                          ? "bg-[var(--color-success-soft)] text-[var(--color-success)]"
                          : g.change_pct < 0
                            ? "bg-[var(--color-danger-soft)] text-[var(--color-danger)]"
                            : "text-[var(--color-fg-muted)]",
                      )}
                    >
                      {g.change_pct > 0 ? (
                        <TrendingUp size={11} />
                      ) : g.change_pct < 0 ? (
                        <TrendingDown size={11} />
                      ) : null}
                      {fmtPct(g.change_pct)}
                    </span>
                  </td>
                  <td className="px-2 py-2">
                    <div
                      className="flex flex-col items-start gap-1"
                      title={`Normal ~${fmtPrice(g.normal_price)} · Rentang ${fmtPrice(g.range_low)}–${fmtPrice(g.range_high)} · posisi ${g.range_pos_pct}%`}
                    >
                      <span
                        className={cn(
                          "rounded-[var(--radius-sm)] px-1.5 py-0.5 text-[10px] font-bold",
                          BIAS_META[g.bias].badge,
                        )}
                      >
                        {BIAS_META[g.bias].label}
                      </span>
                      <PositionGauge pos={g.range_pos_pct} bias={g.bias} />
                    </div>
                  </td>
                  {g.periods.map((d, idx) => (
                    <td
                      key={d.ts ?? idx}
                      className={cn(
                        "px-1.5 py-2 text-right text-[11px] font-semibold tabular-nums",
                        changeTone(d.change_pct ?? 0),
                      )}
                    >
                      {fmtDayPct(d.change_pct)}
                    </td>
                  ))}
                  <td
                    className={cn(
                      "px-2 py-2 text-right text-xs font-semibold tabular-nums",
                      changeTone(g.change_24h_pct ?? 0),
                    )}
                  >
                    {fmtPct(g.change_24h_pct)}
                  </td>
                  <td className="px-2 py-2 text-right">
                    <div className="text-xs font-medium tabular-nums text-[var(--color-fg)]">
                      {fmtPrice(g.price)}
                    </div>
                    <div
                      className="text-[10px] tabular-nums text-[var(--color-fg-faint)]"
                      title="Harga rata-rata (normal) pada rentang ini"
                    >
                      ~{fmtPrice(g.normal_price)}
                    </div>
                  </td>
                  <td className="px-2 py-2 text-right text-xs tabular-nums text-[var(--color-fg-muted)]">
                    {fmtVol(g.volume_24h_usdt)}
                  </td>
                  <td className="px-2 py-2">
                    <div className="flex justify-end">
                      <Sparkline data={g.sparkline} width={88} height={26} />
                    </div>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
