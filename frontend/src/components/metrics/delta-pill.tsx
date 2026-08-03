"use client";

import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import { cn } from "@/lib/utils";
import { metricDelta, formatMetric, type MetricType } from "@/lib/formatters";
import { metricType } from "@/lib/metrics";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";

type Direction = "up" | "down" | "neutral";

/**
 * Shared visual for a semantic delta badge — the exact rounded pill that used
 * to live inline in `metric-tile.tsx`. `direction` is GOOD/BAD (already
 * cost-inverted by `metricDelta`), so "up" is always green regardless of the
 * raw arithmetic sign.
 */
function DeltaBadge({
  label,
  direction,
  className,
}: {
  label: string;
  direction: Direction;
  className?: string;
}) {
  const TrendIcon =
    direction === "up" ? TrendingUp : direction === "down" ? TrendingDown : Minus;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 font-mono text-[10px] font-semibold",
        direction === "up" && "bg-emerald-500/15 text-emerald-400",
        direction === "down" && "bg-red-500/15 text-red-400",
        direction === "neutral" && "bg-muted text-muted-foreground",
        className,
      )}
    >
      <TrendIcon className="size-3" />
      {label}
    </span>
  );
}

interface DeltaPillProps {
  current?: number | null;
  previous?: number | null;
  metricKey: string;
  className?: string;
  /**
   * `"inline"` (KPI cards, funnel) appends a muted `vs <prev>` next to the pill.
   * `"tooltip"` (table cells, ad cards/rows) shows `prev <prev>` on hover.
   * Default `"tooltip"` — the compact form suited to dense contexts.
   */
  variant?: "inline" | "tooltip";
  /** Currency for formatting the previous value when it's a currency metric. */
  currency?: string;
  /**
   * Override the value type used to format the previous value. When omitted it's
   * derived from `metricKey` via the shared `metricType` mapper.
   */
  valueType?: MetricType;
}

/**
 * Period-over-period delta pill. Computes the semantic delta via `metricDelta`
 * (cost metrics inverted) and renders nothing when there's no usable previous
 * value — so it stays silent when a comparison can't be made (P-2).
 *
 * When comparing, it can also surface the PREVIOUS absolute value (formatted per
 * metric type): inline as `vs <prev>` for KPI cards/funnel, or on hover as
 * `prev <prev>` for dense table/ad contexts.
 */
export function DeltaPill({
  current,
  previous,
  metricKey,
  className,
  variant = "tooltip",
  currency = "USD",
  valueType,
}: DeltaPillProps) {
  const { label, direction } = metricDelta(current, previous, metricKey);
  if (direction === "neutral") return null;

  const badge = <DeltaBadge label={label} direction={direction} className={className} />;

  // `metricDelta` already guaranteed `previous` is a usable, non-null number.
  const type = valueType ?? metricType(metricKey);
  const prevFormatted = formatMetric(previous, type, currency);

  if (variant === "inline") {
    return (
      <span className="inline-flex items-center gap-1.5">
        {badge}
        <span className="text-[11px] text-muted-foreground tabular-nums">
          vs {prevFormatted}
        </span>
      </span>
    );
  }

  return (
    <Tooltip>
      <TooltipTrigger
        render={<span className="inline-flex cursor-default items-center" />}
      >
        {badge}
      </TooltipTrigger>
      <TooltipContent>
        prev <span className="font-medium tabular-nums">{prevFormatted}</span>
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * Low-level export for callers that already have a formatted label + direction
 * (e.g. `metric-tile.tsx`, which drives its pill from a raw `change` percent).
 */
export { DeltaBadge };
