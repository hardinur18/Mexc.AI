import { useMemo } from "react";
import { motion } from "motion/react";
import type { Position, SymbolAnalytics } from "@/types/position";
import { fmtPct, fmtPrice } from "@/lib/format";
import { ChevronUp, ChevronDown } from "lucide-react";

interface PriceChartProps {
  p: Position;
  height?: number;
  /** Compact mode — strips volume pane, only shows Entry + nearest TP + live mark, labels in bottom strip */
  compact?: boolean;
  /** Optional analytics to overlay tier prices, SL, POC, VAH/VAL, S/D zones */
  analytics?: SymbolAnalytics | null;
}

// Max chart range as % of current price. Levels beyond this become off-chart arrow markers.
const COMPACT_MAX_RANGE_PCT = 0.12; // ±12% from price

/**
 * Price chart with optional volume pane + analytics overlay.
 */
export function PriceChart({ p, height = 240, compact = false, analytics }: PriceChartProps) {
  const data = p.sparkline ?? [];

  const computed = useMemo(() => {
    const w = 100;
    const PRICE_H_RATIO = compact ? 1 : 0.78;
    const VOL_H_RATIO = compact ? 0 : 0.22;
    const priceH = height * PRICE_H_RATIO - (compact ? 4 : 10);
    const volH = height * VOL_H_RATIO;
    const volStartY = height * PRICE_H_RATIO;

    if (!data || data.length < 2) return null;

    const closes = data.map((d) => d[1]);
    const vols = data.map((d) => (typeof d[2] === "number" ? d[2] : 0));
    const maxVol = Math.max(...vols, 1);

    const nearestTp =
      p.tp_all && p.tp_all.length > 0
        ? p.tp_all.reduce(
            (best, tp) =>
              Math.abs(tp - p.price) < Math.abs(best - p.price) ? tp : best,
            p.tp_all[0],
          )
        : null;

    // Range computation strategy depends on mode
    let lo: number;
    let hi: number;
    if (compact) {
      // Base range from sparkline + entry + mark only (no TP/SL stretching)
      const baseCandidates = [...closes, p.entry, p.price];
      let baseLo = Math.min(...baseCandidates);
      let baseHi = Math.max(...baseCandidates);
      // Ensure entry/mark are within view with min 3% padding
      const ctr = p.price;
      const maxAbsDist = COMPACT_MAX_RANGE_PCT * ctr;
      baseLo = Math.max(baseLo, ctr - maxAbsDist);
      baseHi = Math.min(baseHi, ctr + maxAbsDist);
      // If nearestTp within max range, include it
      if (nearestTp != null && Math.abs(nearestTp - ctr) <= maxAbsDist) {
        baseLo = Math.min(baseLo, nearestTp);
        baseHi = Math.max(baseHi, nearestTp);
      }
      const range = baseHi - baseLo || ctr * 0.02;
      const pad = range * 0.08;
      lo = baseLo - pad;
      hi = baseHi + pad;
    } else {
      const candidates = [...closes, p.entry, p.price];
      if (p.tp_all) candidates.push(...p.tp_all);
      if (p.sl_all) candidates.push(...p.sl_all);
      const min = Math.min(...candidates);
      const max = Math.max(...candidates);
      const range = max - min || max * 0.05;
      const pad = range * 0.05;
      lo = min - pad;
      hi = max + pad;
    }

    const usableH = priceH - (compact ? 6 : 14);
    const topPad = compact ? 3 : 7;

    const xStep = w / (data.length - 1);
    const pts = data.map((d, i) => {
      const x = i * xStep;
      const y = topPad + usableH * (1 - (d[1] - lo) / (hi - lo));
      return [x, y] as [number, number];
    });

    // MA20 (skip in compact)
    let maPath = "";
    if (!compact) {
      const period = 20;
      const maPts: [number, number][] = [];
      for (let i = period - 1; i < closes.length; i++) {
        const slice = closes.slice(i - period + 1, i + 1);
        const ma = slice.reduce((s, v) => s + v, 0) / period;
        const x = i * xStep;
        const y = topPad + usableH * (1 - (ma - lo) / (hi - lo));
        maPts.push([x, y]);
      }
      maPath =
        maPts.length > 0
          ? maPts
              .map((pt, i) => (i === 0 ? `M${pt[0]},${pt[1]}` : `L${pt[0]},${pt[1]}`))
              .join(" ")
          : "";
    }

    const pricePath = pts
      .map((pt, i) => (i === 0 ? `M${pt[0]},${pt[1]}` : `L${pt[0]},${pt[1]}`))
      .join(" ");
    const areaPath = `${pricePath} L${pts[pts.length - 1][0]},${priceH} L0,${priceH} Z`;

    const inRange = (price: number) => price >= lo && price <= hi;
    const yFor = (price: number) => topPad + usableH * (1 - (price - lo) / (hi - lo));

    const levels: Array<{
      price: number;
      y: number;
      label: string;
      color: string;
      dash: boolean;
      offChart?: "above" | "below";
    }> = [];

    if (compact) {
      // Entry (dashed white)
      levels.push({
        price: p.entry,
        y: yFor(p.entry),
        label: "Entry",
        color: "rgba(255,255,255,0.55)",
        dash: true,
        offChart: inRange(p.entry) ? undefined : p.entry > hi ? "above" : "below",
      });

      // Nearest TP (if in range, draw line; else off-chart marker)
      if (nearestTp != null) {
        const tpIdx = (p.tp_all || []).indexOf(nearestTp);
        levels.push({
          price: nearestTp,
          y: inRange(nearestTp) ? yFor(nearestTp) : nearestTp > hi ? topPad : topPad + usableH,
          label: tpIdx >= 0 ? `TP${tpIdx + 1}` : "TP",
          color: "var(--color-success)",
          dash: false,
          offChart: inRange(nearestTp) ? undefined : nearestTp > hi ? "above" : "below",
        });
      }

      // ─── Analytics overlay (Phase 5 alignment) ───
      if (analytics) {
        const plan = analytics.entry_plan;
        // Entry plan tiers
        if (plan?.tiers) {
          plan.tiers.forEach((t, i) => {
            if (i === 0 || t.price == null) return; // skip radar (= entry already)
            if (!inRange(t.price)) return;
            const tone =
              t.role === "main_1" ? "oklch(72% 0.18 280)" :
              t.role === "main_2" ? "oklch(72% 0.18 280)" :
              t.role === "booster" ? "var(--color-warning)" :
              "var(--color-fg-muted)";
            levels.push({
              price: t.price,
              y: yFor(t.price),
              label: t.name,
              color: tone,
              dash: true,
            });
          });
        }
        // SL invalidation
        const sl = plan?.sl_invalidation;
        if (sl?.price && inRange(sl.price)) {
          levels.push({
            price: sl.price,
            y: yFor(sl.price),
            label: "SL",
            color: "var(--color-danger)",
            dash: true,
          });
        }
        // POC
        const poc = analytics.volume_profile_4h?.poc;
        if (poc && inRange(poc)) {
          levels.push({
            price: poc,
            y: yFor(poc),
            label: "POC",
            color: "var(--color-warning)",
            dash: true,
          });
        }
        // Anchored VWAP
        const av =
          analytics.anchored_vwap_swing_low ?? analytics.anchored_vwap_swing_high;
        if (av && inRange(av)) {
          levels.push({
            price: av,
            y: yFor(av),
            label: "VWAP",
            color: "oklch(75% 0.13 220)",
            dash: true,
          });
        }
      }
    } else {
      (p.tp_all || []).forEach((tp, i) =>
        levels.push({
          price: tp,
          y: yFor(tp),
          label: `TP${i + 1}`,
          color: "var(--color-success)",
          dash: false,
        }),
      );
      (p.sl_all || []).forEach((sl, i) =>
        levels.push({
          price: sl,
          y: yFor(sl),
          label: p.sl_count > 1 ? `SL${i + 1}` : "SL",
          color: "var(--color-danger)",
          dash: false,
        }),
      );
      levels.push({
        price: p.entry,
        y: yFor(p.entry),
        label: "Entry",
        color: "rgba(255,255,255,0.5)",
        dash: true,
      });
      if (p.liq_price) {
        levels.push({
          price: p.liq_price,
          y: yFor(p.liq_price),
          label: "Liq",
          color: "var(--color-danger)",
          dash: true,
        });
      }
    }

    // ─── S/D zone bands (compact only, only if in range) ───
    const sdBands: Array<{ y1: number; y2: number; color: string; fresh: boolean }> = [];
    if (compact && analytics?.sd_zones_4h) {
      const dz = analytics.sd_zones_4h.demand_zones ?? [];
      const sz = analytics.sd_zones_4h.supply_zones ?? [];
      dz.slice(0, 2).forEach((z) => {
        if (inRange(z.high) || inRange(z.low)) {
          sdBands.push({
            y1: yFor(Math.min(z.high, hi)),
            y2: yFor(Math.max(z.low, lo)),
            color: "var(--color-success)",
            fresh: z.fresh,
          });
        }
      });
      sz.slice(0, 2).forEach((z) => {
        if (inRange(z.high) || inRange(z.low)) {
          sdBands.push({
            y1: yFor(Math.min(z.high, hi)),
            y2: yFor(Math.max(z.low, lo)),
            color: "var(--color-danger)",
            fresh: z.fresh,
          });
        }
      });
    }

    // Volume bars (skip in compact)
    const volBars = compact
      ? []
      : vols.map((v, i) => {
          const x = i * xStep;
          const barH = (v / maxVol) * volH * 0.9;
          const barW = xStep * 0.6;
          const isRed = i > 0 && closes[i] < closes[i - 1];
          return {
            x: x - barW / 2,
            y: volStartY + (volH - barH),
            w: barW,
            h: barH,
            color: isRed ? "var(--color-danger)" : "var(--color-success)",
          };
        });

    const firstClose = closes[0];
    const lastClose = closes[closes.length - 1];
    const trendUp = lastClose > firstClose;
    const trendColor = trendUp ? "var(--color-success)" : "var(--color-danger)";
    const change24h = ((lastClose - firstClose) / firstClose) * 100;

    return {
      pts,
      pricePath,
      areaPath,
      maPath,
      levels,
      volBars,
      sdBands,
      trendUp,
      trendColor,
      change24h,
      lo,
      hi,
      lastX: pts[pts.length - 1][0],
      lastY: pts[pts.length - 1][1],
      volStartY,
      width: w,
      nearestTp,
    };
  }, [data, height, p, compact, analytics]);

  if (!computed) {
    return (
      <div
        className="rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] px-3 py-6 text-center text-[11px] text-[var(--color-fg-faint)]"
        style={{ height }}
      >
        Data 24 jam belum tersedia
      </div>
    );
  }

  const {
    pricePath,
    areaPath,
    maPath,
    levels,
    volBars,
    sdBands,
    trendColor,
    change24h,
    lo,
    hi,
    lastX,
    lastY,
    volStartY,
    width,
    nearestTp,
  } = computed;

  // ─── COMPACT MODE ───
  if (compact) {
    return (
      <div className="rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] overflow-hidden">
        <div className="px-3 py-1.5 flex items-center justify-between border-b border-[var(--color-border)]/50">
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
              24h · 15m
            </span>
            <span className="text-[9px] text-[var(--color-fg-faint)] num">
              {fmtPrice(lo)} - {fmtPrice(hi)}
            </span>
          </div>
          <span style={{ color: trendColor }} className="text-[10px] num font-semibold">
            {change24h > 0 ? "+" : ""}
            {change24h.toFixed(2)}%
          </span>
        </div>

        <div className="relative" style={{ height }}>
          <svg
            width="100%"
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            preserveAspectRatio="none"
            className="block"
          >
            <defs>
              <linearGradient id={`grad-c-${p.position_id}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={trendColor} stopOpacity="0.25" />
                <stop offset="100%" stopColor={trendColor} stopOpacity="0" />
              </linearGradient>
            </defs>

            {/* S/D zone bands behind everything */}
            {sdBands.map((b, i) => (
              <rect
                key={`band-${i}`}
                x="0"
                y={Math.min(b.y1, b.y2)}
                width={width}
                height={Math.abs(b.y2 - b.y1)}
                fill={b.color}
                opacity={b.fresh ? 0.10 : 0.05}
              />
            ))}

            {/* Reference horizontal lines */}
            {levels
              .filter((lv) => !lv.offChart)
              .map((lv, i) => (
                <line
                  key={i}
                  x1="0"
                  y1={lv.y}
                  x2={width}
                  y2={lv.y}
                  stroke={lv.color}
                  strokeWidth="0.4"
                  strokeDasharray={lv.dash ? "1.5 1.5" : "0"}
                  opacity={lv.dash ? 0.55 : 0.75}
                  vectorEffect="non-scaling-stroke"
                />
              ))}

            {/* Area fill */}
            <path d={areaPath} fill={`url(#grad-c-${p.position_id})`} />

            {/* Price line */}
            <motion.path
              d={pricePath}
              fill="none"
              stroke={trendColor}
              strokeWidth="1.1"
              strokeLinecap="round"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5 }}
            />

            {/* Live dot */}
            <circle cx={lastX} cy={lastY} r="1.2" fill={trendColor} vectorEffect="non-scaling-stroke">
              <animate
                attributeName="r"
                values="1.2;2.0;1.2"
                dur="1.5s"
                repeatCount="indefinite"
              />
            </circle>
          </svg>

          {/* Inline level labels on right edge */}
          <div className="absolute inset-y-0 right-1.5 pointer-events-none">
            {levels
              .filter((lv) => !lv.offChart)
              .map((lv, i) => (
                <div
                  key={i}
                  className="absolute -translate-y-1/2 text-[8px] num font-medium px-1 py-0.5 rounded bg-black/70 whitespace-nowrap"
                  style={{ top: lv.y, color: lv.color }}
                >
                  {lv.label}
                </div>
              ))}
          </div>

          {/* Off-chart markers (arrow indicating level is above/below visible range) */}
          {levels
            .filter((lv) => lv.offChart)
            .map((lv, i) => (
              <div
                key={`off-${i}`}
                className="absolute right-1.5 text-[8px] num font-bold px-1 py-0.5 rounded ring-1 flex items-center gap-0.5"
                style={{
                  [lv.offChart === "above" ? "top" : "bottom"]: 2,
                  color: lv.color,
                  background: `color-mix(in oklch, ${lv.color} 12%, transparent)`,
                  borderColor: `color-mix(in oklch, ${lv.color} 30%, transparent)`,
                }}
              >
                {lv.offChart === "above" ? <ChevronUp size={9} /> : <ChevronDown size={9} />}
                {lv.label} {fmtPrice(lv.price)}
              </div>
            ))}
        </div>

        {/* Bottom label strip — Entry · Mark · nearest TP */}
        <div className="px-3 py-1.5 flex items-center justify-between gap-2 border-t border-[var(--color-border)]/50 text-[10px]">
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-white/50" />
            <span className="text-[var(--color-fg-faint)] uppercase tracking-wider">Entry</span>
            <span className="num text-[var(--color-fg-muted)]">{fmtPrice(p.entry)}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: "var(--color-accent)", boxShadow: "0 0 6px var(--color-accent)" }}
            />
            <span className="text-[var(--color-fg-faint)] uppercase tracking-wider">Mark</span>
            <span className="num font-bold" style={{ color: "var(--color-accent)" }}>
              {fmtPrice(p.price)}
            </span>
            <span
              className="num text-[9px]"
              style={{
                color:
                  p.price_delta_pct > 0
                    ? "var(--color-success)"
                    : p.price_delta_pct < 0
                      ? "var(--color-danger)"
                      : "var(--color-fg-muted)",
              }}
            >
              {fmtPct(p.price_delta_pct)}
            </span>
          </div>
          {nearestTp != null && (
            <div className="flex items-center gap-1.5">
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: "var(--color-success)" }}
              />
              <span className="text-[var(--color-fg-faint)] uppercase tracking-wider">
                {(() => {
                  const idx = (p.tp_all || []).indexOf(nearestTp);
                  return idx >= 0 ? `TP${idx + 1}` : "TP";
                })()}
              </span>
              <span className="num text-[var(--color-success)] font-semibold">
                {fmtPrice(nearestTp)}
              </span>
            </div>
          )}
        </div>
      </div>
    );
  }

  // ─── FULL MODE (unchanged) ───
  return (
    <div className="rounded-[var(--radius-md)] bg-black/25 ring-1 ring-[var(--color-border)] overflow-hidden">
      <div className="px-3 py-2 flex items-center justify-between border-b border-[var(--color-border)]">
        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
            24h · 15m candles
          </span>
          <span className="text-[10px] text-[var(--color-fg-faint)]">
            with MA20 + volume
          </span>
        </div>
        <div className="flex items-center gap-3 text-[10px] num">
          <span className="text-[var(--color-fg-faint)]">
            range {fmtPrice(lo)} – {fmtPrice(hi)}
          </span>
          <span style={{ color: trendColor }} className="font-semibold">
            {change24h > 0 ? "+" : ""}
            {change24h.toFixed(2)}%
          </span>
        </div>
      </div>

      <div className="relative" style={{ height }}>
        <svg
          width="100%"
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          className="block"
        >
          <defs>
            <linearGradient id={`grad-${p.position_id}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={trendColor} stopOpacity="0.25" />
              <stop offset="100%" stopColor={trendColor} stopOpacity="0" />
            </linearGradient>
          </defs>

          <line
            x1="0"
            y1={volStartY}
            x2={width}
            y2={volStartY}
            stroke="var(--color-border)"
            strokeWidth="0.2"
            opacity="0.5"
            vectorEffect="non-scaling-stroke"
          />

          {volBars.map((b, i) => (
            <rect
              key={i}
              x={b.x}
              y={b.y}
              width={b.w}
              height={b.h}
              fill={b.color}
              opacity="0.35"
            />
          ))}

          {levels.map((lv, i) => (
            <line
              key={i}
              x1="0"
              y1={lv.y}
              x2={width}
              y2={lv.y}
              stroke={lv.color}
              strokeWidth="0.3"
              strokeDasharray={lv.dash ? "1.5 1.5" : "0"}
              opacity={lv.dash ? 0.5 : 0.7}
              vectorEffect="non-scaling-stroke"
            />
          ))}

          <path d={areaPath} fill={`url(#grad-${p.position_id})`} />

          {maPath && (
            <motion.path
              d={maPath}
              fill="none"
              stroke="oklch(80% 0.13 210)"
              strokeWidth="0.4"
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeDasharray="1.2 1"
              vectorEffect="non-scaling-stroke"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 0.8, delay: 0.2, ease: [0.25, 1, 0.5, 1] }}
            />
          )}

          <motion.path
            d={pricePath}
            fill="none"
            stroke={trendColor}
            strokeWidth="0.6"
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 0.8, ease: [0.25, 1, 0.5, 1] }}
          />

          <circle
            cx={lastX}
            cy={lastY}
            r="0.8"
            fill={trendColor}
            vectorEffect="non-scaling-stroke"
          >
            <animate
              attributeName="r"
              values="0.8;1.5;0.8"
              dur="1.5s"
              repeatCount="indefinite"
            />
          </circle>
        </svg>

        <div className="absolute inset-y-0 right-0 pointer-events-none">
          {levels.map((lv, i) => (
            <div
              key={i}
              className="absolute right-1.5 -translate-y-1/2 text-[9px] num font-medium px-1.5 py-0.5 rounded bg-black/60 ring-1 whitespace-nowrap"
              style={{
                top: lv.y,
                color: lv.color,
                borderColor: `${lv.color}40`,
              }}
            >
              {lv.label} {fmtPrice(lv.price)}
            </div>
          ))}
          <div
            className="absolute right-1.5 -translate-y-1/2 text-[10px] num font-bold px-1.5 py-0.5 rounded ring-1 whitespace-nowrap z-10"
            style={{
              top: lastY,
              color: "var(--color-accent)",
              background: "var(--color-accent-soft)",
              borderColor: "color-mix(in oklch, var(--color-accent) 40%, transparent)",
              boxShadow: "0 0 8px var(--color-accent-ring)",
            }}
          >
            LIVE {fmtPrice(p.price)} · {fmtPct(p.price_delta_pct)}
          </div>
          <div
            className="absolute right-1.5 text-[9px] font-medium px-1.5 py-0.5 rounded uppercase tracking-wider"
            style={{
              top: 4,
              color: "oklch(80% 0.13 210)",
              background: "color-mix(in oklch, oklch(80% 0.13 210) 12%, transparent)",
            }}
          >
            MA20
          </div>
          <div
            className="absolute left-1.5 text-[9px] uppercase tracking-wider text-[var(--color-fg-faint)] font-semibold"
            style={{ top: volStartY + 4 }}
          >
            Volume
          </div>
        </div>
      </div>
    </div>
  );
}
