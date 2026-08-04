"use client";

import { useQuery } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
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
import { AlertTriangle, Activity, Layers } from "lucide-react";
import { format, parseISO } from "date-fns";
import { AnimatedIcon } from "@/components/shared/animated-icon";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BentoTile } from "@/components/bento/bento-tile";
import { MetricTile } from "@/components/bento/metric-tile";
import { GreetingTile } from "@/components/bento/greeting-tile";
import { GeoTile } from "@/components/bento/geo-tile";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { insightsApi } from "@/lib/api/insights";
import { queryKeys } from "@/lib/query-keys";
import { useAccountsCount } from "@/hooks/use-account";
import { useDateRange } from "@/hooks/use-date-range";
import { getCombinableMetrics } from "@/lib/metrics";
import { staggerGrid } from "@/lib/motion";
import {
  irisColor,
  gridProps,
  axisProps,
  tooltipProps,
  chartAnimation,
} from "@/lib/chart-theme";
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
  const accountCount = useAccountsCount();
  const [accountsParam] = useQueryState("accounts");
  const dateRange = useDateRange();

  // null param = all org accounts (backend resolves); "" = explicitly none;
  // "id,id" = an explicit subset. An empty account_ids sent to the backend
  // means "combine everything".
  const selection = accountsParam == null ? "all" : accountsParam;
  const noneSelected = selection === "";
  const accountIdsParam = selection === "all" ? "" : selection;
  const idsKey = selection === "all" ? ["all"] : selection.split(",").filter(Boolean);
  const queryEnabled = !noneSelected && (accountCount ?? 0) > 0;

  // The cross-platform-safe metric set (see getCombinableMetrics).
  const combinableKpis = getCombinableMetrics().filter((m) => m.showInKpi);

  const { data: ovRes, isLoading: ovLoading } = useQuery({
    queryKey: queryKeys.combined(idsKey, dateRange),
    queryFn: () => insightsApi.combined({ account_ids: accountIdsParam, ...dateRange }),
    enabled: queryEnabled,
    staleTime: 15 * 60 * 1000,
  });

  const ov: CombinedOverview | undefined = ovRes?.data?.data;
  const isCombined = ov?.combined === true;
  const currency = ov?.currency ?? "USD";

  const { data: tsRes, isLoading: tsLoading } = useQuery({
    queryKey: queryKeys.combinedTimeseries(idsKey, dateRange, "day"),
    queryFn: () =>
      insightsApi.combinedTimeseries({
        account_ids: accountIdsParam,
        ...dateRange,
        time_increment: "day",
      }),
    enabled: queryEnabled && isCombined,
    staleTime: 15 * 60 * 1000,
  });

  const series: TrendPoint[] = tsRes?.data?.data?.series ?? [];

  if (accountCount === 0) {
    return (
      <EmptyState message="Connect an account in Settings → Connections to see combined insights." />
    );
  }

  if (noneSelected) {
    return (
      <EmptyState message="No accounts selected. Pick accounts to combine from the account picker above." />
    );
  }

  // ── Mixed currencies → degrade to per-platform (no combined totals) ──
  if (ov && ov.currency_mismatch) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300">
          <AnimatedIcon
            icon={AlertTriangle}
            motionPreset="pop"
            trigger="state"
            appear
            activeVariant="show"
            className="shrink-0"
            iconClassName="size-4"
          />
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
    <motion.div {...staggerGrid} className="grid grid-cols-12 gap-3">
      {/* ── Row 1: greeting · hero combined spend ── */}
      <GreetingTile className="col-span-12 min-h-[210px] md:col-span-4" />

      <BentoTile
        label={`Combined spend · ${ov?.account_count ?? 0} accounts`}
        icon={Activity}
        className="col-span-12 min-h-[210px] md:col-span-8"
        bodyClassName="justify-end px-1 pb-1"
      >
        {tsLoading ? (
          <div className="m-3 h-40 animate-pulse rounded-xl bg-muted/40" />
        ) : series.length === 0 ? (
          <EmptyState message="No data for selected period" />
        ) : (
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={series} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="dashHeroStroke" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor={irisColor(3)} />
                  <stop offset="50%" stopColor={irisColor(4)} />
                  <stop offset="100%" stopColor={irisColor(5)} />
                </linearGradient>
                <linearGradient id="dashHeroFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={irisColor(4)} stopOpacity={0.3} />
                  <stop offset="100%" stopColor={irisColor(4)} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="date" tickFormatter={formatXDate} {...axisProps} interval="preserveStartEnd" />
              <YAxis tickFormatter={(v) => formatCurrency(v, currency)} {...axisProps} width={56} />
              <Tooltip
                formatter={(v) => [formatCurrency(v as number, currency), "Spend"]}
                labelFormatter={(l) => formatXDate(l as string)}
                {...tooltipProps}
              />
              <Area
                type="monotone"
                dataKey="spend"
                stroke="url(#dashHeroStroke)"
                strokeWidth={2.5}
                fill="url(#dashHeroFill)"
                dot={false}
                activeDot={{ r: 4 }}
                {...chartAnimation}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </BentoTile>

      {/* ── KPI band ── */}
      {combinableKpis.map((metric, i) => (
        <MetricTile
          key={metric.key}
          className="col-span-6 min-h-[150px] sm:col-span-4 lg:col-span-3"
          label={metric.label}
          value={formatMetric(summary[metric.key], metric.type, currency)}
          numericValue={(summary[metric.key] as number) ?? null}
          format={(n) => formatMetric(n, metric.type, currency)}
          change={vsPrev[metric.key] ?? null}
          sparkline={series.map((s) => (s[metric.key] as number) ?? 0)}
          accentIndex={i}
          loading={ovLoading}
        />
      ))}

      {/* ── Row 3: global reach · by account ── */}
      <GeoTile
        className="col-span-12 min-h-[300px] lg:col-span-7"
        dateRange={dateRange}
        caption="Global reach"
      />

      <BentoTile
        label="By account"
        icon={Layers}
        className="col-span-12 min-h-[300px] lg:col-span-5"
        bodyClassName="gap-2 p-3"
      >
        {ov && ov.per_account.length > 0 ? (
          ov.per_account.map((acc) => (
            <div
              key={acc.account_id}
              className="flex items-center gap-3 rounded-lg bg-muted/40 px-3 py-2 text-sm"
            >
              {acc.platform && <PlatformBadge platform={acc.platform} size="sm" />}
              <span className="truncate font-medium">{acc.name}</span>
              <span className="ml-auto text-xs tabular-nums font-medium text-muted-foreground">
                {formatCurrency(acc.summary?.spend ?? 0, currency)}
              </span>
            </div>
          ))
        ) : (
          <EmptyState message="No accounts in this selection" />
        )}
      </BentoTile>
    </motion.div>
  );
}
