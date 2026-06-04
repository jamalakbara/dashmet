"use client";

import { useQuery } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { format, parseISO } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MetricCard } from "@/components/metrics/metric-card";
import { insightsApi } from "@/lib/api/insights";
import { queryKeys } from "@/lib/query-keys";
import { useAccountId } from "@/hooks/use-account";
import { useDateRange } from "@/hooks/use-date-range";
import { CHART_COLORS } from "@/lib/constants";
import { formatNumber, formatPercent } from "@/lib/formatters";

interface EngagementSummary {
  likes: number | null;
  comments: number | null;
  shares: number | null;
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
    <div className="space-y-6">
      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {KPIS.map(({ key, label, kind }) => (
          <MetricCard
            key={key}
            label={label}
            value={
              kind === "percent"
                ? formatPercent(summary?.[key] ?? undefined)
                : formatNumber(summary?.[key] ?? undefined)
            }
            sparkline={series.map((s) => s.engagements ?? 0)}
            loading={isLoading}
          />
        ))}
      </div>

      {/* Engagement trend */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Engagement trend</CardTitle>
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
              <LineChart data={series} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis
                  dataKey="date"
                  tickFormatter={formatXDate}
                  tick={{ fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tick={{ fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  width={48}
                />
                <Tooltip
                  formatter={(v) => [formatNumber(v as number), "Engagements"]}
                  labelFormatter={(l) => formatXDate(l as string)}
                  contentStyle={{ fontSize: 12 }}
                />
                <Line
                  type="monotone"
                  dataKey="engagements"
                  stroke={CHART_COLORS[4]}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
