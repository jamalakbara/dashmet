/**
 * Single source of truth for Recharts styling across every chart (overview,
 * periodic, table, funnel, breakdowns, metric sparkline). Import these instead
 * of re-declaring axis/grid/tooltip props inline. All colors reference the
 * design tokens in globals.css so charts follow light/dark automatically.
 */
import { CHART_COLORS } from "@/lib/constants";

export { CHART_COLORS };

/** Semantic colors — kept separate from the series palette for readability. */
export const POSITIVE_COLOR = "var(--color-tint-mint-fg)";
export const NEGATIVE_COLOR = "var(--destructive)";
export const ACCENT_COLOR = "var(--primary)";

/** Pick a series color by index (wraps). */
export const seriesColor = (i: number) => CHART_COLORS[i % CHART_COLORS.length];

/** Iridescent signature spectrum (matches --iris-* / --gradient-iris tokens). */
export const IRIS = [
  "#f6d365",
  "#4fb477",
  "#22b8cf",
  "#5b8def",
  "#9b6dff",
  "#e8619d",
  "#f26a4b",
] as const;

/** One iris hue by index (wraps) — used to color each bento tile. */
export const irisColor = (i: number) => IRIS[i % IRIS.length];

/** Full-spectrum iridescent gradient def (horizontal by default). Reference via
 *  stroke/fill `url(#id)`. */
export function irisGradientDef(id: string, vertical = false) {
  return (
    <linearGradient
      id={id}
      x1="0"
      y1="0"
      x2={vertical ? "0" : "1"}
      y2={vertical ? "1" : "0"}
    >
      {IRIS.map((c, i) => (
        <stop key={i} offset={`${(i / (IRIS.length - 1)) * 100}%`} stopColor={c} />
      ))}
    </linearGradient>
  );
}

/** <CartesianGrid {...gridProps} /> — token-driven (fixes the old broken
 *  `hsl(var(--border))`, which never parsed since tokens are OKLCH). */
export const gridProps = {
  strokeDasharray: "3 3",
  stroke: "var(--border)",
  vertical: false,
} as const;

/** Shared XAxis/YAxis styling. Spread then override dataKey/tickFormatter/width. */
export const axisProps = {
  tick: { fontSize: 11, fill: "var(--muted-foreground)" },
  tickLine: false,
  axisLine: false,
} as const;

/** Recharts <Tooltip contentStyle> — rounded, soft shadow, token colors. */
export const tooltipContentStyle = {
  fontSize: 12,
  borderRadius: 12,
  border: "1px solid var(--border)",
  background: "var(--popover)",
  color: "var(--popover-foreground)",
  boxShadow: "var(--shadow-lift)",
} as const;

export const tooltipLabelStyle = {
  color: "var(--muted-foreground)",
  fontWeight: 500,
  marginBottom: 2,
} as const;

/** Convenience bundle for <Tooltip {...tooltipProps} />. */
export const tooltipProps = {
  contentStyle: tooltipContentStyle,
  labelStyle: tooltipLabelStyle,
  cursor: { fill: "var(--accent)", opacity: 0.4 },
} as const;

/** Rounded bar tops. */
export const barRadius: [number, number, number, number] = [6, 6, 0, 0];

/** Chart draw-in animation (Rich motion). Spread onto Line/Bar/Area/Pie. */
export const chartAnimation = {
  isAnimationActive: true,
  animationDuration: 800,
  animationEasing: "ease-out",
} as const;

/**
 * Emits an SVG linear gradient <defs> for area/line fills. Render inside the
 * chart once, then reference the fill via `url(#<id>)`.
 * Usage:
 *   <defs>{gradientDef("spendFill", seriesColor(0))}</defs>
 *   <Area fill="url(#spendFill)" stroke={seriesColor(0)} />
 */
export function gradientDef(id: string, color: string) {
  return (
    <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stopColor={color} stopOpacity={0.28} />
      <stop offset="100%" stopColor={color} stopOpacity={0} />
    </linearGradient>
  );
}
