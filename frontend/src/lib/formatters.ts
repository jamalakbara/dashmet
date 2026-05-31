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
