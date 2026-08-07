"use client";

import { type LucideIcon } from "lucide-react";
import { DashCard } from "@/components/shared/dash-card";
import { DeltaBadge } from "@/components/metrics/delta-pill";
import { formatChange, formatMetric } from "@/lib/formatters";
import type { MetricType } from "@/lib/formatters";

export interface KpiSpec {
  key: string;
  label: string;
  type: MetricType;
}

interface CombinedKpiCardProps {
  title: string;
  icon: LucideIcon;
  /** Tailwind bg color for the round icon chip (e.g. "bg-orange-500"). */
  accent: string;
  /** Ordered KPI specs. The first is rendered as the big headline number. */
  metrics: KpiSpec[];
  summary: Record<string, number | null | undefined>;
  /** Period-over-period percent changes, keyed by metric key. */
  vsPrev: Record<string, number | null>;
  currency: string;
  /** When true, render the period-over-period delta badges (compare toggle). */
  compare?: boolean;
  loading?: boolean;
}

/**
 * Combined KPI group card — the same visual language as the platform overview
 * `MetricGroupCard` (icon chip + title + big headline number, then a sub-metric
 * grid), but driven by the cross-platform combined summary and its precomputed
 * percent deltas. Delta badges stay silent unless `compare` is on (P-2), matching
 * the platform pages' compare behavior.
 */
export function CombinedKpiCard({
  title,
  icon: Icon,
  accent,
  metrics,
  summary,
  vsPrev,
  currency,
  compare,
  loading,
}: CombinedKpiCardProps) {
  const [headMetric, ...restMetrics] = metrics;

  function DeltaFor({ metricKey }: { metricKey: string }) {
    if (!compare || loading) return null;
    const change = vsPrev[metricKey];
    if (change == null) return null;
    const { label, direction } = formatChange(change);
    if (direction === "neutral") return null;
    return <DeltaBadge label={label} direction={direction} />;
  }

  return (
    <DashCard title={title} icon={Icon} accent={accent}>
      {/* Headline (first metric) */}
      {headMetric && (
        <div className="px-5 pb-4 pt-2">
          {loading ? (
            <div className="h-8 w-40 animate-pulse rounded bg-muted" />
          ) : (
            <div className="flex items-center gap-2">
              <p className="text-2xl font-bold tracking-tight tabular-nums">
                {formatMetric(summary[headMetric.key], headMetric.type, currency)}
              </p>
              <DeltaFor metricKey={headMetric.key} />
            </div>
          )}
        </div>
      )}

      {/* Sub-metric grid */}
      <div className="border-t border-border px-5 py-5">
        {loading ? (
          <div className="grid grid-cols-2 gap-x-6 gap-y-6 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="space-y-2">
                <div className="h-3 w-20 animate-pulse rounded bg-muted" />
                <div className="h-4 w-24 animate-pulse rounded bg-muted" />
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-x-6 gap-y-6 lg:grid-cols-4">
            {restMetrics.map((m) => (
              <div key={m.key} className="min-w-0">
                <p className="truncate text-sm text-muted-foreground">{m.label}</p>
                <p className="mt-0.5 font-semibold tabular-nums">
                  {formatMetric(summary[m.key], m.type, currency)}
                </p>
                <div className="mt-0.5">
                  <DeltaFor metricKey={m.key} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </DashCard>
  );
}
