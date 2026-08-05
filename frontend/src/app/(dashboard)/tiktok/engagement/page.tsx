"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { motion } from "framer-motion";
import { Heart } from "lucide-react";
import { format, parseISO } from "date-fns";
import { DashCard } from "@/components/shared/dash-card";
import { SectionHeading } from "@/components/shared/section-heading";
import { MetricGroupCard, type SubMetric } from "@/components/metrics/metric-group-card";
import { insightsApi } from "@/lib/api/insights";
import { queryKeys } from "@/lib/query-keys";
import { useAccountId } from "@/hooks/use-account";
import { useDateRange } from "@/hooks/use-date-range";
import { staggerGrid } from "@/lib/motion";
import {
  seriesColor,
  gridProps,
  axisProps,
  tooltipProps,
  chartAnimation,
  gradientDef,
} from "@/lib/chart-theme";
import { formatNumber, formatPercent } from "@/lib/formatters";

interface EngagementSummary {
  likes: number | null;
  comments: number | null;
  shares: number | null;
  follows: number | null;
  profile_visits: number | null;
  total_engagements: number | null;
  impressions: number | null;
  engagement_rate: number | null;
}

interface EngagementPoint {
  date: string;
  engagements: number | null;
}

function formatXDate(dateStr: string) {
  try {
    return format(parseISO(dateStr), "MMM d");
  } catch {
    return dateStr;
  }
}

// Headline (total_engagements) + sub-metrics, in reference order.
const SUB_KPIS: { key: keyof EngagementSummary; label: string; kind: "number" | "percent" }[] = [
  { key: "likes",           label: "Likes",           kind: "number" },
  { key: "comments",        label: "Comments",        kind: "number" },
  { key: "shares",          label: "Shares",          kind: "number" },
  { key: "follows",         label: "Follows",         kind: "number" },
  { key: "profile_visits",  label: "Profile Visits",  kind: "number" },
  { key: "engagement_rate", label: "Engagement Rate", kind: "percent" },
  { key: "impressions",     label: "Impressions",     kind: "number" },
];

function fmt(value: number | null | undefined, kind: "number" | "percent") {
  return kind === "percent"
    ? formatPercent(value ?? undefined)
    : formatNumber(value ?? undefined);
}

export default function EngagementPage() {
  const accountId = useAccountId();
  const dateRange = useDateRange();

  const { data: res, isLoading } = useQuery({
    queryKey: queryKeys.engagement(accountId ?? "", dateRange),
    queryFn: () => insightsApi.engagement({ account_id: accountId!, ...dateRange }),
    enabled: !!accountId,
    staleTime: 15 * 60 * 1000,
  });

  const summary: EngagementSummary | undefined = res?.data?.data?.summary;
  const series: EngagementPoint[] = res?.data?.data?.series ?? [];

  if (!accountId) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        No TikTok account selected.
      </div>
    );
  }

  const subMetrics: SubMetric[] = SUB_KPIS.map(({ key, label, kind }) => ({
    key,
    label,
    value: fmt(summary?.[key], kind),
    raw: summary?.[key] ?? null,
  }));

  return (
    <motion.div {...staggerGrid} className="space-y-6">
      {/* Engagement metrics — one grouped card, matching the platform Overview. */}
      <section className="space-y-3">
        <SectionHeading
          title="Engagement"
          subtitle="Audience interaction for the selected period."
        />
        <MetricGroupCard
          title="Engagement"
          icon={Heart}
          accent="bg-rose-500"
          columns={4}
          headline={fmt(summary?.total_engagements, "number")}
          subMetrics={subMetrics}
          previewCount={subMetrics.length}
          loading={isLoading}
        />
      </section>

      {/* Engagement trend */}
      <section className="space-y-3">
        <SectionHeading
          title="Engagement trend"
          subtitle="Daily engagements over the selected period."
        />
        <DashCard bodyClassName="p-5">
          {isLoading ? (
            <div className="h-60 animate-pulse rounded bg-muted" />
          ) : series.length === 0 ? (
            <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
              No engagement data for selected period
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={series} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <defs>{gradientDef("engFill", seriesColor(4))}</defs>
                <CartesianGrid {...gridProps} />
                <XAxis
                  dataKey="date"
                  tickFormatter={formatXDate}
                  {...axisProps}
                  interval="preserveStartEnd"
                />
                <YAxis {...axisProps} width={48} />
                <Tooltip
                  formatter={(v) => [formatNumber(v as number), "Engagements"]}
                  labelFormatter={(l) => formatXDate(l as string)}
                  {...tooltipProps}
                />
                <Area
                  type="monotone"
                  dataKey="engagements"
                  stroke={seriesColor(4)}
                  strokeWidth={2}
                  fill="url(#engFill)"
                  dot={false}
                  activeDot={{ r: 4 }}
                  {...chartAnimation}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </DashCard>
      </section>
    </motion.div>
  );
}
