"use client";

import { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ChevronDown, ArrowUpRight, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { fadeInUp } from "@/lib/motion";
import { AnimatedIcon } from "@/components/shared/animated-icon";
import { DeltaPill } from "@/components/metrics/delta-pill";

export interface SubMetric {
  key: string;
  label: string;
  /** Formatted value shown to the user. */
  value: string;
  /** Raw numeric backing `value`, for period-over-period delta pills. */
  raw?: number | null;
}

interface MetricGroupCardProps {
  title: string;
  /** Big formatted headline number under the title. */
  headline: string;
  icon: LucideIcon;
  /** Tailwind bg color for the round icon chip (e.g. "bg-orange-500"). */
  accent: string;
  subMetrics: SubMetric[];
  /** How many sub-metrics show before "See More" (rest collapse). */
  previewCount?: number;
  detailHref?: string;
  loading?: boolean;
  /** When true (and `previous` present), render period-over-period delta pills. */
  compare?: boolean;
  /** Previous-period raw numeric values, keyed by metric key. */
  previous?: Record<string, number | null>;
  /** Metric key + raw numeric backing the headline, for its delta pill. */
  headlineKey?: string;
  headlineValue?: number | null;
  /** Account currency, threaded to delta pills so `vs <prev>` formats correctly. */
  currency?: string;
}

/**
 * Grouped metric card (Base Data style): a colored icon chip + title + headline
 * number, a "See Detail" affordance, then a two-column grid of sub-metrics with
 * a "See More" expander for the overflow. One card per metric family.
 */
export function MetricGroupCard({
  title,
  headline,
  icon: Icon,
  accent,
  subMetrics,
  previewCount = 4,
  detailHref,
  loading,
  compare,
  previous,
  headlineKey,
  headlineValue,
  currency = "USD",
}: MetricGroupCardProps) {
  const [expanded, setExpanded] = useState(false);
  const hasMore = subMetrics.length > previewCount;
  const shown = expanded ? subMetrics : subMetrics.slice(0, previewCount);
  const showDelta = !!compare && !!previous;

  return (
    <motion.div
      variants={fadeInUp}
      className="flex flex-col overflow-hidden rounded-xl bg-card ring-1 ring-foreground/10 shadow-[var(--shadow-soft)]"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 px-5 pt-5">
        <div className="flex items-center gap-2.5">
          <span
            className={cn(
              "flex size-8 items-center justify-center rounded-full text-white",
              accent
            )}
          >
            <Icon className="size-[18px]" />
          </span>
          <span className="text-base font-semibold">{title}</span>
        </div>
        {detailHref && (
          <Link
            href={detailHref}
            className="group inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm font-medium text-primary transition-colors hover:bg-accent"
          >
            <AnimatedIcon
              icon={ArrowUpRight}
              motionPreset="draw"
              iconClassName="size-4"
            />
            See Detail
          </Link>
        )}
      </div>

      {/* Headline */}
      <div className="px-5 pb-4 pt-2">
        {loading ? (
          <div className="h-8 w-40 animate-pulse rounded bg-muted" />
        ) : (
          <div className="flex items-center gap-2">
            <p className="text-2xl font-bold tracking-tight tabular-nums">{headline}</p>
            {showDelta && headlineKey && (
              <DeltaPill
                current={headlineValue}
                previous={previous?.[headlineKey]}
                metricKey={headlineKey}
                variant="inline"
                currency={currency}
              />
            )}
          </div>
        )}
      </div>

      {/* Sub-metric grid */}
      <div className="border-t border-border px-5 py-5">
        {loading ? (
          <div className="grid grid-cols-2 gap-x-6 gap-y-6">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="space-y-2">
                <div className="h-3 w-20 animate-pulse rounded bg-muted" />
                <div className="h-4 w-24 animate-pulse rounded bg-muted" />
              </div>
            ))}
          </div>
        ) : shown.length === 0 ? (
          <p className="text-sm text-muted-foreground">No data for this period.</p>
        ) : (
          <div className="grid grid-cols-2 gap-x-6 gap-y-6">
            {shown.map((m) => (
              <div key={m.key} className="min-w-0">
                <p className="truncate text-sm text-muted-foreground">{m.label}</p>
                <p className="mt-0.5 font-semibold tabular-nums">{m.value}</p>
                {showDelta && (
                  <div className="mt-0.5">
                    <DeltaPill
                      current={m.raw}
                      previous={previous?.[m.key]}
                      metricKey={m.key}
                      variant="inline"
                      currency={currency}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* See More */}
      {hasMore && !loading && (
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          className="flex items-center justify-center gap-1.5 border-t border-border py-3 text-sm font-medium text-primary transition-colors hover:bg-accent/50"
        >
          {expanded ? "See Less" : "See More"}
          <AnimatedIcon
            icon={ChevronDown}
            motionPreset="flip"
            trigger="state"
            active={expanded}
            iconClassName="size-4"
          />
        </button>
      )}
    </motion.div>
  );
}
