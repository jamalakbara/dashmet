"use client";

import { useQuery } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { AlertTriangle } from "lucide-react";
import { format, parseISO } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { MetricCard } from "@/components/metrics/metric-card";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { insightsApi } from "@/lib/api/insights";
import { queryKeys } from "@/lib/query-keys";
import { useAccountsList } from "@/hooks/use-account";
import { useDateRange } from "@/hooks/use-date-range";
import { getCombinableMetrics } from "@/lib/metrics";
import { CHART_COLORS } from "@/lib/constants";
import { formatMetric, formatCurrency } from "@/lib/formatters";

interface MetricBag {
  [key: string]: number | null | undefined;
}

interface PerAccount {
  account_id: string;
  name: string;
  platform: string | null;
  currency: string | null;
  summary: MetricBag;
}

interface CombinedOverview {
  combined: boolean;
  currency_mismatch: boolean;
  currency: string | null;
  currencies: string[];
  summary: MetricBag;
  vs_previous: Record<string, number | null>;
  per_account: PerAccount[];
  account_count: number;
}

interface TrendPoint {
  date: string;
  spend?: number | null;
  clicks?: number | null;
  [key: string]: number | string | null | undefined;
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
    <div className="flex h-40 items-center justify-center text-center text-sm text-muted-foreground">
      {message}
    </div>
  );
}

export default function CombinedDashboardPage() {
  const accounts = useAccountsList();
  const [accountsParam] = useQueryState("accounts");
  const dateRange = useDateRange();

  const allIds = accounts.map((a) => a.id);
  const selectedIds =
    accountsParam == null
      ? allIds
      : accountsParam
          .split(",")
          .filter(Boolean)
          .filter((id) => allIds.includes(id));
  const idsKey = selectedIds.join(",");

  // The cross-platform-safe metric set (see getCombinableMetrics).
  const combinableKpis = getCombinableMetrics().filter((m) => m.showInKpi);

  const { data: ovRes, isLoading: ovLoading } = useQuery({
    queryKey: queryKeys.combined(selectedIds, dateRange),
    queryFn: () => insightsApi.combined({ account_ids: idsKey, ...dateRange }),
    enabled: selectedIds.length > 0,
    staleTime: 15 * 60 * 1000,
  });

  const ov: CombinedOverview | undefined = ovRes?.data?.data;
  const isCombined = ov?.combined === true;
  const currency = ov?.currency ?? "USD";

  const { data: tsRes, isLoading: tsLoading } = useQuery({
    queryKey: queryKeys.combinedTimeseries(selectedIds, dateRange, "day"),
    queryFn: () =>
      insightsApi.combinedTimeseries({
        account_ids: idsKey,
        ...dateRange,
        time_increment: "day",
      }),
    enabled: selectedIds.length > 0 && isCombined,
    staleTime: 15 * 60 * 1000,
  });

  const series: TrendPoint[] = tsRes?.data?.data?.series ?? [];

  if (accounts.length === 0) {
    return (
      <EmptyState message="Connect an account in Settings → Connections to see combined insights." />
    );
  }

  if (selectedIds.length === 0) {
    return (
      <EmptyState message="No accounts selected. Pick accounts to combine from the account picker above." />
    );
  }

  // ── Mixed currencies → degrade to per-platform (no combined totals) ──
  if (ov && ov.currency_mismatch) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300">
          <AlertTriangle className="size-4 shrink-0" />
          Mixed currencies ({ov.currencies.join(", ")}) — totals can&apos;t be combined. Showing each account separately.
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {ov.per_account.map((acc) => (
            <Card key={acc.account_id}>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm font-medium">
                  {acc.platform && <PlatformBadge platform={acc.platform} size="sm" />}
                  <span className="truncate">{acc.name}</span>
                  <span className="ml-auto text-xs font-normal text-muted-foreground">
                    {acc.currency}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
                  {combinableKpis.map((m) => (
                    <div key={m.key}>
                      <p className="text-xs text-muted-foreground">{m.label}</p>
                      <p className="tabular-nums font-medium">
                        {formatMetric(acc.summary?.[m.key], m.type, acc.currency ?? "USD")}
                      </p>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  // ── Single currency → combined aggregate ──
  const summary = ov?.summary ?? {};
  const vsPrev = ov?.vs_previous ?? {};

  return (
    <div className="space-y-6">
      {/* Combined KPI cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        {combinableKpis.map((metric) => (
          <MetricCard
            key={metric.key}
            label={metric.label}
            value={formatMetric(summary[metric.key], metric.type, currency)}
            change={vsPrev[metric.key] ?? null}
            sparkline={series.map((s) => (s[metric.key] as number) ?? 0)}
            loading={ovLoading}
          />
        ))}
      </div>

      {/* Trend charts */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Combined spend trend</CardTitle>
          </CardHeader>
          <CardContent>
            {tsLoading ? (
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

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Combined clicks trend</CardTitle>
          </CardHeader>
          <CardContent>
            {tsLoading ? (
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
                    formatter={(v) => [(v as number)?.toLocaleString?.() ?? v, "Clicks"]}
                    labelFormatter={(l) => formatXDate(l as string)}
                    contentStyle={{ fontSize: 12 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="clicks"
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

      {/* Per-account contribution */}
      {ov && ov.per_account.length > 1 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">By account</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {ov.per_account.map((acc) => (
                <div
                  key={acc.account_id}
                  className="flex items-center gap-3 rounded-md border px-3 py-2 text-sm"
                >
                  {acc.platform && <PlatformBadge platform={acc.platform} size="sm" />}
                  <span className="truncate font-medium">{acc.name}</span>
                  <span className="ml-auto tabular-nums text-muted-foreground">
                    {formatCurrency(acc.summary?.spend ?? 0, currency)}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
