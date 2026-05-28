import { motion } from "motion/react";
import { Crosshair, Zap, ArrowUpRight, ArrowDownRight } from "lucide-react";
import type { SDZonesData, WyckoffSpringUpthrust } from "@/types/position";
import { fmtPrice } from "@/lib/format";

interface Props {
  zones: SDZonesData | null | undefined;
  springUpthrust: WyckoffSpringUpthrust | null | undefined;
  currentPrice?: number | null;
}

export function LiquidityZonesCard({ zones, springUpthrust, currentPrice }: Props) {
  const demand = zones?.demand_zones ?? [];
  const supply = zones?.supply_zones ?? [];
  const hasSpring = !!springUpthrust?.spring;
  const hasUpthrust = !!springUpthrust?.upthrust;

  if (demand.length === 0 && supply.length === 0 && !hasSpring && !hasUpthrust) {
    return null;
  }

  return (
    <div className="lift rounded-[var(--radius-md)] inner-card overflow-hidden">
      <div className="px-3 py-2 flex items-center gap-2 border-b border-[var(--color-border)]/50">
        <Crosshair size={11} className="text-[var(--color-warning)]" />
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-semibold">
          Liquidity Zones (4h)
        </span>
        <span className="text-[9px] text-[var(--color-fg-faint)] ml-auto">
          drop-base-rally · spring/upthrust
        </span>
      </div>

      <div className="p-4 space-y-3">
        {/* Wyckoff spring/upthrust */}
        {(hasSpring || hasUpthrust) && (
          <div className="space-y-1.5">
            {hasSpring && (
              <SpringUpthrustChip
                tone="var(--color-success)"
                icon={<Zap size={11} />}
                title="Wyckoff Spring detected"
                detail={`False break BELOW ${fmtPrice(springUpthrust!.broken_support!)} → close balik di atas. Stop hunt + whale buy.`}
                price={springUpthrust?.spring_low}
                priceLabel="dip ke"
              />
            )}
            {hasUpthrust && (
              <SpringUpthrustChip
                tone="var(--color-danger)"
                icon={<Zap size={11} />}
                title="Wyckoff Upthrust detected"
                detail={`False break ABOVE ${fmtPrice(springUpthrust!.broken_resistance!)} → close gagal. Stop hunt + whale sell.`}
                price={springUpthrust?.upthrust_high}
                priceLabel="puncak"
              />
            )}
          </div>
        )}

        {/* Demand zones */}
        {demand.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1.5">
              <ArrowUpRight size={9} className="text-[var(--color-success)]" />
              Demand Zone (support institusional)
            </div>
            <div className="space-y-1">
              {demand.slice(0, 3).map((z, i) => (
                <ZoneRow
                  key={`d-${i}`}
                  z={z}
                  tone="var(--color-success)"
                  currentPrice={currentPrice}
                />
              ))}
            </div>
          </div>
        )}

        {/* Supply zones */}
        {supply.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-[var(--color-fg-faint)] mb-1.5">
              <ArrowDownRight size={9} className="text-[var(--color-danger)]" />
              Supply Zone (resistance institusional)
            </div>
            <div className="space-y-1">
              {supply.slice(0, 3).map((z, i) => (
                <ZoneRow
                  key={`s-${i}`}
                  z={z}
                  tone="var(--color-danger)"
                  currentPrice={currentPrice}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function SpringUpthrustChip({
  tone,
  icon,
  title,
  detail,
  price,
  priceLabel,
}: {
  tone: string;
  icon: React.ReactNode;
  title: string;
  detail: string;
  price?: number | null;
  priceLabel?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -3 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex items-start gap-2 px-2.5 py-2 rounded-[var(--radius-sm)] ring-1"
      style={{
        background: `color-mix(in oklch, ${tone} 10%, transparent)`,
        borderColor: `color-mix(in oklch, ${tone} 30%, transparent)`,
      }}
    >
      <span style={{ color: tone }} className="shrink-0 mt-0.5">
        {icon}
      </span>
      <div className="leading-tight min-w-0 flex-1">
        <div className="text-[10px] font-bold" style={{ color: tone }}>
          {title}
        </div>
        <div className="text-[9px] text-[var(--color-fg-muted)] mt-0.5">{detail}</div>
        {price != null && (
          <div className="text-[9px] text-[var(--color-fg-faint)] mt-0.5">
            {priceLabel} <span className="num text-[var(--color-fg-muted)]">{fmtPrice(price)}</span>
          </div>
        )}
      </div>
    </motion.div>
  );
}

function ZoneRow({
  z,
  tone,
  currentPrice,
}: {
  z: import("@/types/position").SDZone;
  tone: string;
  currentPrice?: number | null;
}) {
  const dist =
    currentPrice && currentPrice > 0
      ? ((z.mid - currentPrice) / currentPrice) * 100
      : null;
  return (
    <div
      className="flex items-center gap-2 px-2.5 py-1.5 rounded-[var(--radius-sm)] ring-1"
      style={{
        background: z.fresh
          ? `color-mix(in oklch, ${tone} 12%, transparent)`
          : `color-mix(in oklch, ${tone} 4%, transparent)`,
        borderColor: `color-mix(in oklch, ${tone} ${z.fresh ? 35 : 20}%, transparent)`,
      }}
    >
      <span
        className="text-[8px] uppercase tracking-wider font-bold px-1.5 py-0.5 rounded shrink-0"
        style={{
          color: z.fresh ? tone : "var(--color-fg-faint)",
          background: z.fresh
            ? `color-mix(in oklch, ${tone} 18%, transparent)`
            : "transparent",
        }}
      >
        {z.fresh ? "FRESH" : "tested"}
      </span>
      <div className="flex-1 leading-tight min-w-0">
        <div className="text-[10px] num font-semibold">
          {fmtPrice(z.low)}{" "}
          <span className="text-[var(--color-fg-faint)]">→</span>{" "}
          {fmtPrice(z.high)}
        </div>
        <div className="text-[8px] text-[var(--color-fg-faint)]">
          impulse {z.impulse_strength.toFixed(1)}× · bar -{z.bar_index_from_now}
        </div>
      </div>
      {dist != null && (
        <div
          className="text-[9px] num font-semibold shrink-0"
          style={{
            color:
              Math.abs(dist) < 2
                ? "var(--color-warning)"
                : "var(--color-fg-muted)",
          }}
        >
          {dist > 0 ? "+" : ""}
          {dist.toFixed(1)}%
        </div>
      )}
    </div>
  );
}
