import { memo, useMemo } from "react";
import { motion } from "motion/react";

interface SparklineProps {
  data: number[][]; // [[time_ms, close], ...]
  /** Width in px. */
  width?: number;
  /** Height in px. */
  height?: number;
  /** Color of the line. If null, auto: green/red based on first→last delta. */
  color?: string | null;
  /** Show area fill below the line. */
  fill?: boolean;
  /** Optional reference price to overlay as horizontal line (entry). */
  refPrice?: number | null;
  /** Optional second reference (mark / current). */
  markPrice?: number | null;
}

function SparklineInner({
  data,
  width = 100,
  height = 28,
  color = null,
  fill = true,
  refPrice = null,
  markPrice = null,
}: SparklineProps) {
  const { path, areaPath, lineColor, lastX, lastY, refY, markY } = useMemo(() => {
    if (!data || data.length < 2) {
      return {
        path: "",
        areaPath: "",
        lineColor: "var(--color-fg-muted)",
        lastX: 0,
        lastY: 0,
        refY: null as number | null,
        markY: null as number | null,
      };
    }
    const closes = data.map((d) => d[1]);
    const min = Math.min(...closes, ...(refPrice ? [refPrice] : []), ...(markPrice ? [markPrice] : []));
    const max = Math.max(...closes, ...(refPrice ? [refPrice] : []), ...(markPrice ? [markPrice] : []));
    const range = max - min || max * 0.05;
    const padTop = 2;
    const padBot = 2;
    const usableH = height - padTop - padBot;

    const xStep = data.length > 1 ? width / (data.length - 1) : width;
    const points = data.map((d, i) => {
      const x = i * xStep;
      const y = padTop + usableH * (1 - (d[1] - min) / range);
      return [x, y] as [number, number];
    });

    const path = points
      .map((pt, i) => (i === 0 ? `M${pt[0]},${pt[1]}` : `L${pt[0]},${pt[1]}`))
      .join(" ");
    const areaPath = `${path} L${points[points.length - 1][0]},${height} L0,${height} Z`;

    const firstClose = closes[0];
    const lastClose = closes[closes.length - 1];
    const auto =
      lastClose > firstClose ? "var(--color-success)" : lastClose < firstClose ? "var(--color-danger)" : "var(--color-fg-muted)";
    const lineColor = color ?? auto;

    const refY = refPrice != null ? padTop + usableH * (1 - (refPrice - min) / range) : null;
    const markY = markPrice != null ? padTop + usableH * (1 - (markPrice - min) / range) : null;

    return {
      path,
      areaPath,
      lineColor,
      lastX: points[points.length - 1][0],
      lastY: points[points.length - 1][1],
      refY,
      markY,
    };
  }, [data, width, height, color, refPrice, markPrice]);

  if (!data || data.length < 2) {
    return (
      <div
        className="text-[9px] text-[var(--color-fg-faint)] italic flex items-center justify-center"
        style={{ width, height }}
      >
        no data
      </div>
    );
  }

  const gradId = `spark-grad-${lineColor.replace(/\W/g, "")}`;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="block">
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={lineColor} stopOpacity="0.35" />
          <stop offset="100%" stopColor={lineColor} stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Entry reference line (subtle dashed) */}
      {refY !== null && (
        <line
          x1="0"
          y1={refY}
          x2={width}
          y2={refY}
          stroke="var(--color-fg-faint)"
          strokeWidth="1"
          strokeDasharray="2 2"
          opacity="0.6"
        />
      )}

      {fill && <path d={areaPath} fill={`url(#${gradId})`} />}

      <motion.path
        d={path}
        fill="none"
        stroke={lineColor}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.7, ease: [0.25, 1, 0.5, 1] }}
      />

      {/* Last point pulse */}
      <circle
        cx={lastX}
        cy={lastY}
        r="2"
        fill={lineColor}
        style={{ filter: `drop-shadow(0 0 3px ${lineColor})` }}
      />
      <circle
        cx={lastX}
        cy={lastY}
        r="2"
        fill={lineColor}
        opacity="0.35"
        className="[animation:pulse-glow_1.6s_ease-in-out_infinite]"
      />

      {/* Mark price reference (optional, hidden if same as last) */}
      {markY !== null && Math.abs(markY - lastY) > 1 && (
        <line
          x1="0"
          y1={markY}
          x2={width}
          y2={markY}
          stroke={lineColor}
          strokeWidth="1"
          strokeDasharray="1 2"
          opacity="0.3"
        />
      )}
    </svg>
  );
}


/* Memoized export — re-renders only when props change deeply by ref */
export const Sparkline = memo(SparklineInner, (prev, next) => {
  return (
    prev.data === next.data &&
    prev.width === next.width &&
    prev.height === next.height &&
    prev.color === next.color &&
    prev.fill === next.fill &&
    prev.refPrice === next.refPrice &&
    prev.markPrice === next.markPrice
  );
});
