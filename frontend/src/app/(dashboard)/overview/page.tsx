"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
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
import { ArrowRight } from "lucide-react";
import { format, parseISO } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { MetricCard } from "@/components/metrics/metric-card";
import { StatusBadge } from "@/components/shared/status-badge";
import { insightsApi } from "@/lib/api/insights";
import { queryKeys } from "@/lib/query-keys";
import { useSelectedAccount } from "@/hooks/use-account";
import { useDateRange } from "@/hooks/use-date-range";
import { usePlatformMetrics } from "@/hooks/use-platform-metrics";
import { CHART_COLORS } from "@/lib/constants";
import {
  formatMetric,
  formatCurrency,
  formatPercent,
  formatRoas,
} from "@/lib/formatters";
import type { EntityStatus } from "@/types/enums";

interface OverviewSummary {
  spend: number;
  impressions: number;
  reach: number;
  frequency: number;
  clicks: number;
  ctr: number;
  cpm: number;
  cpc: number;
  conversions: number;
  conversion_value: number;
  roas: number;
  cpa: number;
  [key: string]: number;
}

interface TopCampaign {
  id: string;
  name: string;
  spend: number;
  impressions: number;
  ctr: number;
  conversions: number;
  roas: number;
  outbound_clicks?: number;
  status?: EntityStatus;
}

interface SeriesRow {
  date: string;
  spend?: number;
  conversions?: number;
  [key: string]: number | string | undefined;
}

function formatXDate(dateStr: string) {
  try {
    return format(parseISO(dateStr), "MMM d");
  } catch {
    return dateStr;
  }
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
      {message}
    </div>
  );
}

export default function OverviewPage() {
  const { accountId, currency } = useSelectedAccount();
  const dateRange = useDateRange();
  const { kpiMetrics, accountType } = usePlatformMetrics();
  const isCpas = accountType === "cpas";
  const kpiKeys = kpiMetrics.map((m) => m.key);
  const trendMetric2 = kpiMetrics.find((m) => m.key === "conversions") ? "conversions" : "clicks";
  const trendMetric2Label = kpiMetrics.find((m) => m.key === trendMetric2)?.label ?? trendMetric2;

  const [polling, setPolling] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevAccountId = useRef<string | null>(null);

  useEffect(() => {
    if (!accountId || accountId === prevAccountId.current) return;
    prevAccountId.current = accountId;
    setPolling(true);
    if (pollTimer.current) clearTimeout(pollTimer.current);
    pollTimer.current = setTimeout(() => setPolling(false), 5 * 60 * 1000);
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [accountId]);

  const { data: overviewRes, isLoading: overviewLoading } = useQuery({
    queryKey: queryKeys.overview(accountId ?? "", dateRange),
    queryFn: () =>
      insightsApi.overview({ account_id: accountId!, ...dateRange }),
    enabled: !!accountId,
    staleTime: 15 * 60 * 1000,
    refetchInterval: polling ? 5000 : false,
  });

  const { data: timeseriesRes, isLoading: timeseriesLoading } = useQuery({
    queryKey: queryKeys.timeseries(
      accountId ?? "",
      dateRange,
      "account",
      kpiKeys,
      "day"
    ),
    queryFn: () =>
      insightsApi.timeseries({
        account_id: accountId!,
        ...dateRange,
        level: "account",
        metrics: kpiKeys.join(","),
        time_increment: "day",
      }),
    enabled: !!accountId,
    staleTime: 15 * 60 * 1000,
    refetchInterval: polling ? 5000 : false,
  });

  const isLoading = overviewLoading || timeseriesLoading;

  const overview = overviewRes?.data?.data;
  const summary: OverviewSummary | undefined = overview?.summary;

  useEffect(() => {
    if (polling && (summary?.spend !== null && summary?.spend !== undefined)) {
      setPolling(false);
      if (pollTimer.current) clearTimeout(pollTimer.current);
    }
  }, [polling, summary?.spend]);

  const vsPrev: Record<string, number | null> = overview?.vs_previous ?? {};
  const topCampaigns: TopCampaign[] = overview?.top_campaigns ?? [];
  const series: SeriesRow[] = timeseriesRes?.data?.data?.series ?? [];

  if (!accountId) {
    return (
      <EmptyState message="No account selected. Connect an account in Settings → Connections." />
    );
  }

  return (
    <div className="space-y-6">
      {/* KPI Cards — 2 rows × 4 */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {kpiMetrics.map((metric) => (
          <MetricCard
            key={metric.key}
            label={metric.label}
            value={formatMetric(summary?.[metric.key], metric.type, currency)}
            change={vsPrev[metric.key] ?? null}
            sparkline={series.map((s) => (s[metric.key] as number) ?? 0)}
            loading={isLoading}
          />
        ))}
      </div>

      {/* Trend Charts */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Spend Trend */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Spend trend</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-60 animate-pulse rounded bg-muted" />
            ) : series.length === 0 ? (
              <EmptyState message="No data for selected period" />
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
                    tickFormatter={(v) => formatCurrency(v, currency)}
                    tick={{ fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    width={60}
                  />
                  <Tooltip
                    formatter={(v) => [formatCurrency(v as number, currency), "Spend"]}
                    labelFormatter={(l) => formatXDate(l as string)}
                    contentStyle={{ fontSize: 12 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="spend"
                    stroke={CHART_COLORS[0]}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Trend chart 2: conversions (Meta) or clicks (TikTok fallback) */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">{trendMetric2Label} trend</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-60 animate-pulse rounded bg-muted" />
            ) : series.length === 0 ? (
              <EmptyState message="No data for selected period" />
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
                    width={40}
                  />
                  <Tooltip
                    formatter={(v) => [v as number, trendMetric2Label]}
                    labelFormatter={(l) => formatXDate(l as string)}
                    contentStyle={{ fontSize: 12 }}
                  />
                  <Line
                    type="monotone"
                    dataKey={trendMetric2}
                    stroke={CHART_COLORS[1]}
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

      {/* Top Campaigns */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium">Top campaigns</CardTitle>
          <Link
            href={`/table?level=campaign${accountId ? `&account_id=${accountId}` : ""}`}
            className="flex items-center gap-1 text-xs text-primary hover:underline"
          >
            View all <ArrowRight className="size-3" />
          </Link>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-px">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-10 animate-pulse bg-muted mx-4 my-1 rounded" />
              ))}
            </div>
          ) : topCampaigns.length === 0 ? (
            <EmptyState message="No campaigns in this period" />
          ) : (
            <>
            {isCpas && (
              <div className="mx-4 mb-3 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-700 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-300">
                Conversion data (ROAS, purchases, revenue) for this account is managed by the retailer and may not be available here.
              </div>
            )}
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Campaign</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Spend</TableHead>
                  <TableHead className="text-right">Impressions</TableHead>
                  <TableHead className="text-right">CTR</TableHead>
                  {isCpas ? (
                    <TableHead className="text-right">Outbound Clicks</TableHead>
                  ) : (
                    <>
                      <TableHead className="text-right">Conv.</TableHead>
                      <TableHead className="text-right">ROAS</TableHead>
                    </>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {topCampaigns.slice(0, 5).map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="font-medium max-w-48 truncate">
                      {c.name}
                    </TableCell>
                    <TableCell>
                      {c.status ? (
                        <StatusBadge status={c.status} />
                      ) : (
                        <span className="text-muted-foreground text-sm">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatCurrency(c.spend, currency)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {c.impressions?.toLocaleString() ?? "—"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatPercent(c.ctr)}
                    </TableCell>
                    {isCpas ? (
                      <TableCell className="text-right tabular-nums">
                        {c.outbound_clicks != null
                          ? c.outbound_clicks.toLocaleString()
                          : "—"}
                      </TableCell>
                    ) : (
                      <>
                        <TableCell className="text-right tabular-nums">
                          {c.conversions?.toLocaleString() ?? "—"}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatRoas(c.roas)}
                        </TableCell>
                      </>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
