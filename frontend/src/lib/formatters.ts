export function formatCurrency(value: number | null | undefined, currency = "USD"): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatNumber(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toLocaleString("en-US");
}

export function formatPercent(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${value.toFixed(2)}%`;
}

export function formatRoas(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${value.toFixed(2)}x`;
}

export type MetricType = "currency" | "percent" | "number" | "roas";

export function formatMetric(
  value: number | null | undefined,
  type: MetricType,
  currency = "USD"
): string {
  switch (type) {
    case "currency": return formatCurrency(value, currency);
    case "percent":  return formatPercent(value);
    case "roas":     return formatRoas(value);
    default:         return formatNumber(value);
  }
}

export function formatChange(pct: number | null | undefined): {
  label: string;
  direction: "up" | "down" | "neutral";
} {
  if (pct == null) return { label: "—", direction: "neutral" };
  const sign = pct > 0 ? "+" : "";
  return {
    label: `${sign}${pct.toFixed(1)}%`,
    direction: pct > 0 ? "up" : pct < 0 ? "down" : "neutral",
  };
}

/**
 * Cost/efficiency metrics where a DECREASE is the good outcome, so the
 * delta pill's semantic color is inverted (a drop → green/"up").
 */
export const COST_METRICS = new Set(["cpa", "cpc", "cpm", "cpp", "frequency"]);

function isCostMetric(metricKey: string): boolean {
  return COST_METRICS.has(metricKey) || metricKey.startsWith("cost_per_");
}

/**
 * Period-over-period delta for a single metric, with semantic direction.
 *
 * `direction` encodes GOOD/BAD, not raw sign:
 *  - normal metric: increase → "up" (green), decrease → "down" (red)
 *  - cost metric (COST_METRICS or `cost_per_*`): the direction is inverted so
 *    a decrease reads as "up" (good/green) and an increase as "down" (bad/red).
 *
 * Returns a neutral "—" when there's no usable comparison (missing current/
 * previous, or a zero baseline that would divide by zero).
 */
export function metricDelta(
  current: number | null | undefined,
  previous: number | null | undefined,
  metricKey: string,
): { label: string; direction: "up" | "down" | "neutral" } {
  if (current == null || previous == null || previous === 0) {
    return { label: "—", direction: "neutral" };
  }
  const pct = ((current - previous) / previous) * 100;
  const sign = pct > 0 ? "+" : "";
  const label = `${sign}${pct.toFixed(1)}%`;

  if (pct === 0) return { label, direction: "neutral" };

  // Raw sign of the change, then invert for cost metrics so "good" is "up".
  const rawUp = pct > 0;
  const good = isCostMetric(metricKey) ? !rawUp : rawUp;
  return { label, direction: good ? "up" : "down" };
}
