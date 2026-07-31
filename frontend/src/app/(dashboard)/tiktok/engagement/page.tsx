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
import { format, parseISO } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MetricCard, tintByIndex } from "@/components/metrics/metric-card";
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

const KPIS: { key: keyof EngagementSummary; label: string; kind: "number" | "percent" }[] = [
  { key: "likes",             label: "Likes",            kind: "number" },
  { key: "comments",          label: "Comments",         kind: "number" },
  { key: "shares",            label: "Shares",           kind: "number" },
  { key: "follows",           label: "Follows",          kind: "number" },
  { key: "profile_visits",    label: "Profile Visits",   kind: "number" },
  { key: "total_engagements", label: "Total Engagements", kind: "number" },
  { key: "engagement_rate",   label: "Engagement Rate",  kind: "percent" },
  { key: "impressions",       label: "Impressions",      kind: "number" },
];

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

  return (
    <div className="space-y-8">
      {/* ── Engagement metrics ── */}
      <section className="space-y-3">
        <h2 className="font-display text-base font-semibold leading-tight">
          Engagement metrics
        </h2>
        <motion.div
          className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6"
          {...staggerGrid}
        >
        {KPIS.map(({ key, label, kind }, i) => (
          <MetricCard
            key={key}
            label={label}
            value={
              kind === "percent"
                ? formatPercent(summary?.[key] ?? undefined)
                : formatNumber(summary?.[key] ?? undefined)
            }
            numericValue={summary?.[key] ?? null}
            format={(n) => (kind === "percent" ? formatPercent(n) : formatNumber(n))}
            sparkline={series.map((s) => s.engagements ?? 0)}
            tint={tintByIndex(i)}
            loading={isLoading}
          />
        ))}
        </motion.div>
      </section>

      {/* Engagement trend */}
      <Card className="shadow-[var(--shadow-soft)]">
        <CardHeader className="pb-2">
          <CardTitle className="font-display text-sm font-semibold">Engagement trend</CardTitle>
        </CardHeader>
        <CardContent>
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
        </CardContent>
      </Card>
    </div>
  );
}
