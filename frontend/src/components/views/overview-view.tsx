"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
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
import { ArrowRight, Activity, Trophy, Gauge as GaugeIcon } from "lucide-react";
import { format, parseISO } from "date-fns";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { BentoTile } from "@/components/bento/bento-tile";
import { MetricTile } from "@/components/bento/metric-tile";
import { GaugeTile } from "@/components/bento/gauge-tile";
import { GeoTile } from "@/components/bento/geo-tile";
import { GreetingTile } from "@/components/bento/greeting-tile";
import { StatusBadge } from "@/components/shared/status-badge";
import { insightsApi } from "@/lib/api/insights";
import { queryKeys } from "@/lib/query-keys";
import { useSelectedAccount } from "@/hooks/use-account";
import { useDateRange } from "@/hooks/use-date-range";
import { usePlatform } from "@/hooks/use-platform";
import { usePlatformMetrics } from "@/hooks/use-platform-metrics";
import { useSharedFilterQuery } from "@/hooks/use-shared-query";
import { staggerGrid } from "@/lib/motion";
import { irisColor, gridProps, axisProps, tooltipProps, chartAnimation } from "@/lib/chart-theme";
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

export function OverviewView() {
  const { accountId, currency } = useSelectedAccount();
  const platform = usePlatform() ?? "meta";
  const withQuery = useSharedFilterQuery();
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
      "day",
      false
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

  // Headline gauge: ROAS toward a 4× target (falls back to CTR toward 5%).
  const roas = summary?.roas;
  const hasRoas = !isCpas && roas != null && roas > 0;
  const gauge = hasRoas
    ? {
        label: "ROAS",
        value: roas!,
        format: (n: number) => formatRoas(n),
        fraction: Math.min(roas! / 4, 1),
        footerLeft: "0×",
        footerRight: "4×+",
      }
    : {
        label: "CTR",
        value: summary?.ctr ?? 0,
        format: (n: number) => formatPercent(n),
        fraction: Math.min((summary?.ctr ?? 0) / 5, 1),
        footerLeft: "0%",
        footerRight: "5%+",
      };

  return (
    <motion.div {...staggerGrid} className="grid grid-cols-12 gap-3">
      {/* ── Row 1: greeting · headline gauge · hero spend ── */}
      <GreetingTile className="col-span-12 min-h-[210px] md:col-span-4" />

      <GaugeTile
        className="col-span-6 min-h-[210px] md:col-span-3"
        label={gauge.label}
        icon={GaugeIcon}
        fraction={gauge.fraction}
        value={gauge.value}
        format={gauge.format}
        unit={gauge.label}
        footerLeft={gauge.footerLeft}
        footerRight={gauge.footerRight}
        loading={isLoading}
      />

      <BentoTile
        label="Spend · daily"
        icon={Activity}
        className="col-span-6 min-h-[210px] md:col-span-5"
        bodyClassName="justify-end px-1 pb-1"
        action={
          <Link
            href={withQuery(`/${platform}/periodic`)}
            className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-primary hover:underline"
          >
            Periodic <ArrowRight className="size-3" />
          </Link>
        }
      >
        {isLoading ? (
          <div className="m-3 h-40 animate-pulse rounded-xl bg-muted/40" />
        ) : series.length === 0 ? (
          <EmptyState message="No data for selected period" />
        ) : (
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={series} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="ovHeroStroke" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor={irisColor(3)} />
                  <stop offset="50%" stopColor={irisColor(4)} />
                  <stop offset="100%" stopColor={irisColor(5)} />
                </linearGradient>
                <linearGradient id="ovHeroFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={irisColor(4)} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={irisColor(4)} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="date" tickFormatter={formatXDate} {...axisProps} interval="preserveStartEnd" />
              <YAxis tickFormatter={(v) => formatCurrency(v, currency)} {...axisProps} width={54} />
              <Tooltip
                formatter={(v) => [formatCurrency(v as number, currency), "Spend"]}
                labelFormatter={(l) => formatXDate(l as string)}
                {...tooltipProps}
              />
              <Area
                type="monotone"
                dataKey="spend"
                stroke="url(#ovHeroStroke)"
                strokeWidth={2.5}
                fill="url(#ovHeroFill)"
                dot={false}
                activeDot={{ r: 4 }}
                {...chartAnimation}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </BentoTile>

      {/* ── KPI band ── */}
      {kpiMetrics.map((metric, i) => (
        <MetricTile
          key={metric.key}
          className="col-span-6 min-h-[150px] sm:col-span-4 lg:col-span-3"
          label={metric.label}
          value={formatMetric(summary?.[metric.key], metric.type, currency)}
          numericValue={summary?.[metric.key] ?? null}
          format={(n) => formatMetric(n, metric.type, currency)}
          change={vsPrev[metric.key] ?? null}
          sparkline={series.map((s) => (s[metric.key] as number) ?? 0)}
          accentIndex={i}
          loading={isLoading}
        />
      ))}

      {/* ── Row 3: geo · top campaigns ── */}
      <GeoTile
        className="col-span-12 min-h-[300px] lg:col-span-7"
        accountId={accountId ?? undefined}
        dateRange={dateRange}
        caption="Geo · spend"
      />

      <BentoTile
        label="Top campaigns"
        icon={Trophy}
        className="col-span-12 min-h-[300px] lg:col-span-5"
        bodyClassName="p-0"
        action={
          <Link
            href={withQuery(`/${platform}/table?level=campaign`)}
            className="flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide text-primary hover:underline"
          >
            All <ArrowRight className="size-3" />
          </Link>
        }
      >
        {isLoading ? (
          <div className="space-y-px p-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-9 animate-pulse rounded bg-muted/40" />
            ))}
          </div>
        ) : topCampaigns.length === 0 ? (
          <EmptyState message="No campaigns in this period" />
        ) : (
          <div className="mt-2 overflow-x-auto">
            {isCpas && (
              <div className="mx-3 mb-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                Conversion data (ROAS, purchases, revenue) is managed by the retailer and may not appear here.
              </div>
            )}
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Campaign</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Spend</TableHead>
                  {isCpas ? (
                    <TableHead className="text-right">Outbound</TableHead>
                  ) : (
                    <TableHead className="text-right">ROAS</TableHead>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {topCampaigns.slice(0, 6).map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="max-w-40 truncate font-medium">{c.name}</TableCell>
                    <TableCell>
                      {c.status ? (
                        <StatusBadge status={c.status} />
                      ) : (
                        <span className="text-sm text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatCurrency(c.spend, currency)}
                    </TableCell>
                    {isCpas ? (
                      <TableCell className="text-right tabular-nums">
                        {c.outbound_clicks != null
                          ? c.outbound_clicks.toLocaleString()
                          : "—"}
                      </TableCell>
                    ) : (
                      <TableCell className="text-right tabular-nums">
                        {formatRoas(c.roas)}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </BentoTile>
    </motion.div>
  );
}
