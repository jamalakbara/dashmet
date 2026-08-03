"use client";

import { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ChevronDown, ArrowUpRight, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { fadeInUp } from "@/lib/motion";

export interface SubMetric {
  key: string;
  label: string;
  value: string;
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
}: MetricGroupCardProps) {
  const [expanded, setExpanded] = useState(false);
  const hasMore = subMetrics.length > previewCount;
  const shown = expanded ? subMetrics : subMetrics.slice(0, previewCount);

  return (
    <motion.div
      variants={fadeInUp}
      className="flex flex-col overflow-hidden rounded-xl border border-border bg-card shadow-[var(--shadow-soft)]"
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
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm font-medium text-primary transition-colors hover:bg-accent"
          >
            <ArrowUpRight className="size-4" />
            See Detail
          </Link>
        )}
      </div>

      {/* Headline */}
      <div className="px-5 pb-4 pt-2">
        {loading ? (
          <div className="h-8 w-40 animate-pulse rounded bg-muted" />
        ) : (
          <p className="text-2xl font-bold tracking-tight tabular-nums">{headline}</p>
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
          <ChevronDown
            className={cn("size-4 transition-transform", expanded && "rotate-180")}
          />
        </button>
      )}
    </motion.div>
  );
}
