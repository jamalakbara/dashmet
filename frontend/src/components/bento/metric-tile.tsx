"use client";

import { AreaChart, Area, ResponsiveContainer } from "recharts";
import { type LucideIcon } from "lucide-react";
import { BentoTile } from "./bento-tile";
import { AnimatedNumber } from "@/components/shared/animated-number";
import { DeltaBadge } from "@/components/metrics/delta-pill";
import { formatChange } from "@/lib/formatters";
import { chartAnimation, irisColor } from "@/lib/chart-theme";

interface MetricTileProps {
  label: string;
  icon?: LucideIcon;
  value: string;
  numericValue?: number | null;
  format?: (n: number) => string;
  change?: number | null;
  sparkline?: number[];
  /** Which iris hue codes this tile (dot, sparkline). */
  accentIndex?: number;
  className?: string;
  loading?: boolean;
}

/** Bento KPI cell: mono label · delta pill · big count-up numeral · hue sparkline. */
export function MetricTile({
  label,
  icon,
  value,
  numericValue,
  format,
  change,
  sparkline,
  accentIndex = 0,
  className,
  loading,
}: MetricTileProps) {
  const accent = irisColor(accentIndex);
  const { label: changeLabel, direction } = formatChange(change);
  const sparkData = (sparkline ?? []).map((v) => ({ v }));
  const doAnimate = numericValue != null && format != null;
  const gid = `bento-spark-${label.replace(/\W+/g, "")}-${accentIndex}`;

  const deltaPill =
    !loading && change != null ? (
      <DeltaBadge label={changeLabel} direction={direction} />
    ) : null;

  return (
    <BentoTile
      label={label}
      icon={icon}
      action={deltaPill}
      className={className}
      bodyClassName="justify-between"
    >
      <div className="px-4 pt-2">
        {loading ? (
          <div className="h-9 w-28 animate-pulse rounded bg-muted" />
        ) : (
          <div className="font-display text-3xl font-semibold tabular-nums leading-none">
            {doAnimate ? (
              <AnimatedNumber value={numericValue!} format={format!} />
            ) : (
              value
            )}
          </div>
        )}
      </div>

      <div className="mt-3 h-12">
        {sparkData.length > 1 && !loading ? (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={sparkData} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={accent} stopOpacity={0.5} />
                  <stop offset="100%" stopColor={accent} stopOpacity={0} />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="v"
                stroke={accent}
                strokeWidth={2}
                fill={`url(#${gid})`}
                dot={false}
                {...chartAnimation}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : null}
      </div>
    </BentoTile>
  );
}
