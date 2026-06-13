import { Crosshair, Shield, ShieldAlert } from "lucide-react";
import type { SupportResistanceConfluence, SupportResistanceLevel } from "@/types/position";
import { fmtPrice, fmtPct } from "@/lib/format";
import { cn } from "@/lib/cn";

interface Props {
  data: SupportResistanceConfluence | null | undefined;
  direction?: "LONG" | "SHORT" | "NONE";
}

export function SupportResistanceCard({ data, direction = "NONE" }: Props) {
  if (!data || !data.levels?.length) return null;

  const tone =
    data.score >= 75
      ? "var(--color-success)"
      : data.score >= 60
        ? "var(--color-accent)"
        : data.score >= 40
          ? "var(--color-warning)"
          : "var(--color-danger)";
  const targetLabel = direction === "LONG" ? "support" : direction === "SHORT" ? "resistance" : "level";

  return (
    <div className="inner-card overflow-hidden">
      <div className="ui-panel-header px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <span className="ui-icon-chip" style={{ color: tone }}>
            <Crosshair size={13} />
          </span>
          <span className="ui-section-title">S/R Confluence</span>
        </div>
        <span className="text-[11px] font-semibold uppercase tracking-[0.04em]" style={{ color: tone }}>
          {data.verdict} {data.score}/100
        </span>
      </div>

      <div className="px-4 py-4 space-y-3">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <NearestBox label="Nearest support" level={data.nearest_support} side="support" />
          <NearestBox label="Nearest resistance" level={data.nearest_resistance} side="resistance" />
        </div>

        {data.warnings && data.warnings.length > 0 && (
          <div className="flex items-start gap-2 rounded-[var(--radius-sm)] px-2.5 py-2 text-[10px] ring-1"
            style={{
              color: "var(--color-warning)",
              background: "color-mix(in oklch, var(--color-warning) 10%, transparent)",
              borderColor: "color-mix(in oklch, var(--color-warning) 30%, transparent)",
            }}
          >
            <ShieldAlert size={12} className="mt-0.5 shrink-0" />
            <span>{data.warnings.slice(0, 2).join(" · ")}</span>
          </div>
        )}

        <div>
          <div className="mb-1.5 flex items-center justify-between text-[10px] font-bold uppercase tracking-[0.04em] text-[var(--color-fg-faint)]">
            <span>Nearby levels</span>
            <span>{targetLabel} window {data.near_window_pct?.toFixed(1) ?? "-"}%</span>
          </div>
          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {data.levels.slice(0, 8).map((level, i) => (
              <LevelRow key={`${level.label}-${level.price}-${i}`} level={level} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function NearestBox({
  label,
  level,
  side,
}: {
  label: string;
  level?: SupportResistanceLevel | null;
  side: "support" | "resistance";
}) {
  const tone = side === "support" ? "var(--color-success)" : "var(--color-danger)";
  return (
    <div
      className="rounded-[var(--radius-sm)] px-2.5 py-2 ring-1"
      style={{
        background: `color-mix(in oklch, ${tone} 8%, transparent)`,
        borderColor: `color-mix(in oklch, ${tone} 25%, transparent)`,
      }}
    >
      <div className="mb-1 flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-[0.04em]" style={{ color: tone }}>
        <Shield size={10} />
        {label}
      </div>
      {level ? (
        <>
          <div className="num text-[12px] font-bold text-[var(--color-fg)]">{fmtPrice(level.price)}</div>
          <div className="text-[9px] text-[var(--color-fg-faint)]">
            {level.label} {level.timeframe ? `· ${level.timeframe}` : ""} · {fmtPct(level.distance_pct)}
          </div>
        </>
      ) : (
        <div className="text-[10px] text-[var(--color-fg-faint)]">no nearby level</div>
      )}
    </div>
  );
}

function LevelRow({ level }: { level: SupportResistanceLevel }) {
  const tone =
    level.side === "support"
      ? "var(--color-success)"
      : level.side === "resistance"
        ? "var(--color-danger)"
        : "var(--color-accent)";
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded-[var(--radius-sm)] px-2.5 py-1.5 text-[10px] ring-1",
        level.in_zone && "outline outline-1 outline-[var(--color-warning)]/40",
      )}
      style={{
        background: `color-mix(in oklch, ${tone} ${level.in_zone ? 14 : 7}%, transparent)`,
        borderColor: `color-mix(in oklch, ${tone} 24%, transparent)`,
      }}
    >
      <span className="w-16 shrink-0 truncate font-bold uppercase tracking-[0.04em]" style={{ color: tone }}>
        {level.label}
      </span>
      <span className="num min-w-0 flex-1 truncate font-semibold text-[var(--color-fg)]">
        {level.in_zone && level.zone_low != null && level.zone_high != null
          ? `${fmtPrice(level.zone_low)}-${fmtPrice(level.zone_high)}`
          : fmtPrice(level.price)}
      </span>
      <span className="num shrink-0 font-bold" style={{ color: Math.abs(level.distance_pct) <= 1 ? "var(--color-warning)" : "var(--color-fg-muted)" }}>
        {fmtPct(level.distance_pct)}
      </span>
    </div>
  );
}
