"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { format, parseISO } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { SegmentControl } from "@/components/ui/segment-control";
import { BreakdownSection } from "@/components/metrics/breakdown-section";
import { insightsApi } from "@/lib/api/insights";
import { queryKeys } from "@/lib/query-keys";
import { useAccountId } from "@/hooks/use-account";
import { useSyncActive } from "@/hooks/use-sync-jobs";
import { useDateRange } from "@/hooks/use-date-range";
import { useOverviewFilter } from "@/hooks/use-overview-filter";
import { usePlatformMetrics } from "@/hooks/use-platform-metrics";
import { metricLabel, metricType } from "@/lib/metrics";
import { CHART_COLORS, gridProps, axisProps, tooltipProps } from "@/lib/chart-theme";
import { formatMetric } from "@/lib/formatters";

// ─── Types ────────────────────────────────────────────────────────────────────

interface SeriesRow {
  date: string;
  [key: string]: number | string | null | undefined;
}

interface EntitySeries {
  entity: { id: string; name: string };
  series: SeriesRow[];
  previous_series?: SeriesRow[];
}

// ─── Constants ────────────────────────────────────────────────────────────────

const LEVELS = [
  { value: "account",  label: "Account" },
  { value: "campaign", label: "Campaign" },
  { value: "adgroup",  label: "Ad Group" },
  { value: "ad",       label: "Ad" },
];

const TIME_INCREMENTS = [
  { value: "day",   label: "Day" },
  { value: "week",  label: "Week" },
  { value: "month", label: "Month" },
];

function formatXDate(v: unknown): string {
  try { return format(parseISO(v as string), "MMM d"); }
  catch { return String(v); }
}

function SkeletonChart({ height }: { height: number }) {
  return <div className="animate-pulse rounded bg-muted" style={{ height }} />;
}

function Empty({ height = 280 }: { height?: number }) {
  return (
    <div
      className="flex items-center justify-center text-sm text-muted-foreground"
      style={{ height }}
    >
      No data for selected period
    </div>
  );
}

// ─── View ─────────────────────────────────────────────────────────────────────

export function PeriodicView() {
  const accountId     = useAccountId();
  const dateRange     = useDateRange();
  const filter        = useOverviewFilter();
  const { selectableMetrics, currency } = usePlatformMetrics();

  // Own param key (not the shared "level" used by the Table view) so the two can
  // co-exist on the composed Overview without corrupting each other's queries.
  const [level, setLevel]               = useQueryState("trend_level",    { defaultValue: "account" });
  const [metricsStr, setMetricsStr]     = useQueryState("metrics",        { defaultValue: "spend,clicks" });
  const [timeIncrement, setTimeIncrement] = useQueryState("time_increment", { defaultValue: "day" });
  // Read-only here — the compare toggle now lives globally in the top bar.
  const [compareStr]                    = useQueryState("compare");

  const [chartType, setChartType] = useState<"line" | "bar">("line");

  const metrics        = metricsStr.split(",").filter(Boolean).slice(0, 2);

  // Sanitize URL metrics when platform changes — drop keys not in the new selectable set
  const selectableKeyStr = selectableMetrics.map((m) => m.key).join(",");
  useEffect(() => {
    const validKeys = new Set(selectableKeyStr.split(",").filter(Boolean));
    const valid = metricsStr.split(",").filter((m) => m && validKeys.has(m));
    if (valid.length === 0) {
      setMetricsStr(selectableKeyStr.split(",").slice(0, 2).join(","));
    } else if (valid.join(",") !== metricsStr) {
      setMetricsStr(valid.join(","));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectableKeyStr]);
  const comparePrev    = compareStr === "true";
  const isAccountLevel = level === "account";
  const syncActive     = useSyncActive();

  // ── Timeseries ──
  const { data: tsRes, isLoading } = useQuery({
    queryKey: queryKeys.timeseries(accountId ?? "", dateRange, level, metrics, timeIncrement, comparePrev, filter),
    queryFn: () =>
      insightsApi.timeseries({
        account_id: accountId!,
        ...dateRange,
        level,
        metrics: metrics.join(","),
        time_increment: timeIncrement,
        compare_previous: comparePrev,
        ...filter,
      }),
    enabled: !!accountId,
    staleTime: 15 * 60 * 1000,
    // Poll while a sync is landing so the trend fills in without a manual refresh.
    refetchInterval: syncActive ? 5000 : false,
  });

  // ── Build chart data ──
  const tsData                           = tsRes?.data?.data;
  const flatSeries: SeriesRow[]          = tsData?.series ?? [];
  const prevSeries: SeriesRow[]          = tsData?.previous_series ?? [];
  const seriesByEntity: EntitySeries[]   = (tsData?.series_by_entity ?? []).slice(0, 10);

  let chartData: Record<string, unknown>[] = [];
  if (isAccountLevel) {
    chartData = flatSeries.map((row, idx) => {
      const entry: Record<string, unknown> = { date: row.date };
      metrics.forEach((m) => { entry[m] = row[m] ?? null; });
      if (comparePrev && prevSeries[idx]) {
        metrics.forEach((m) => { entry[`prev_${m}`] = prevSeries[idx][m] ?? null; });
      }
      return entry;
    });
  } else {
    const dateMap = new Map<string, Record<string, unknown>>();
    seriesByEntity.forEach(({ entity, series, previous_series }) => {
      series.forEach((row, idx) => {
        if (!dateMap.has(row.date)) dateMap.set(row.date, { date: row.date });
        const entry = dateMap.get(row.date)!;
        entry[entity.id] = row[metrics[0]] ?? null;
        if (comparePrev && previous_series?.[idx]) {
          entry[`prev_${entity.id}`] = previous_series[idx][metrics[0]] ?? null;
        }
      });
    });
    chartData = Array.from(dateMap.values()).sort(
      (a, b) => (a.date as string).localeCompare(b.date as string)
    );
  }

  function toggleMetric(m: string) {
    if (metrics.includes(m)) {
      if (metrics.length === 1) return;
      setMetricsStr(metrics.filter((x) => x !== m).join(","));
    } else {
      setMetricsStr((metrics.length >= 2 ? [metrics[0], m] : [...metrics, m]).join(","));
    }
  }

  if (!accountId) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        No account selected.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* ── Controls ── */}
      <div className="flex flex-wrap items-center gap-3">
        <Select items={LEVELS} value={level} onValueChange={(v) => setLevel(v)}>
          <SelectTrigger className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {LEVELS.map((l) => (
              <SelectItem key={l.value} value={l.value}>{l.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Popover>
          <PopoverTrigger className="flex h-8 items-center gap-1.5 rounded-lg border border-input bg-transparent px-2.5 text-sm whitespace-nowrap transition-colors hover:bg-accent">
            Metrics: {metrics.map((m) => metricLabel(m)).join(" + ")}
          </PopoverTrigger>
          <PopoverContent className="w-52 p-3">
            <p className="mb-2 text-xs text-muted-foreground">Select up to 2</p>
            <div className="space-y-1.5">
              {selectableMetrics.map((m) => (
                <label key={m.key} className="flex cursor-pointer items-center gap-2 text-sm">
                  <Checkbox
                    checked={metrics.includes(m.key)}
                    onCheckedChange={() => toggleMetric(m.key)}
                  />
                  {m.label}
                </label>
              ))}
            </div>
          </PopoverContent>
        </Popover>

        <SegmentControl
          items={TIME_INCREMENTS}
          value={timeIncrement}
          onValueChange={(v) => setTimeIncrement(v)}
          ariaLabel="Time increment"
        />
      </div>

      {/* ── Main Chart ── */}
      <Card className="shadow-[var(--shadow-soft)]">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium">
              {isAccountLevel
                ? metrics.map((m) => metricLabel(m)).join(" vs ")
                : `${metricLabel(metrics[0])} by ${LEVELS.find((l) => l.value === level)?.label ?? level}`}
            </CardTitle>
            <SegmentControl
              items={[{ value: "line", label: "Line" }, { value: "bar", label: "Bar" }]}
              value={chartType}
              onValueChange={setChartType}
              ariaLabel="Chart type"
            />
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <SkeletonChart height={360} />
          ) : chartData.length === 0 ? (
            <Empty height={360} />
          ) : (
            <ResponsiveContainer width="100%" height={360}>
              <ComposedChart data={chartData} margin={{ top: 4, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid {...gridProps} />
                <XAxis
                  dataKey="date"
                  tickFormatter={formatXDate}
                  {...axisProps}
                  interval="preserveStartEnd"
                />
                <YAxis
                  yAxisId="left"
                  tickFormatter={(v) => formatMetric(v, metricType(metrics[0]), currency)}
                  {...axisProps}
                  width={64}
                />
                {isAccountLevel && metrics[1] && (
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    tickFormatter={(v) => formatMetric(v, metricType(metrics[1]), currency)}
                    {...axisProps}
                    width={64}
                  />
                )}
                <Tooltip
                  formatter={(v, name) => {
                    const s = String(name);
                    const m = s.replace("prev_", "");
                    const label = s.startsWith("prev_")
                      ? `${metricLabel(m)} (prev)`
                      : metricLabel(m);
                    return [formatMetric(v as number, metricType(m), currency), label];
                  }}
                  labelFormatter={formatXDate}
                  {...tooltipProps}
                />
                <Legend
                  formatter={(name) => {
                    const s = String(name);
                    const m = s.replace("prev_", "");
                    return s.startsWith("prev_")
                      ? `${metricLabel(m)} (prev. period)`
                      : metricLabel(m);
                  }}
                />

                {isAccountLevel
                  ? metrics.map((m, i) =>
                      chartType === "bar" ? (
                        <Bar key={m} dataKey={m} yAxisId="left" fill={CHART_COLORS[i]} opacity={0.85} />
                      ) : (
                        <Line
                          key={m}
                          type="monotone"
                          dataKey={m}
                          yAxisId={i === 1 && metrics[1] ? "right" : "left"}
                          stroke={CHART_COLORS[i]}
                          strokeWidth={2}
                          dot={false}
                          activeDot={{ r: 4 }}
                        />
                      )
                    )
                  : seriesByEntity.map((e, i) =>
                      chartType === "bar" ? (
                        <Bar
                          key={e.entity.id}
                          dataKey={e.entity.id}
                          name={e.entity.name}
                          yAxisId="left"
                          fill={CHART_COLORS[i % CHART_COLORS.length]}
                          opacity={0.85}
                        />
                      ) : (
                        <Line
                          key={e.entity.id}
                          type="monotone"
                          dataKey={e.entity.id}
                          name={e.entity.name}
                          yAxisId="left"
                          stroke={CHART_COLORS[i % CHART_COLORS.length]}
                          strokeWidth={2}
                          dot={false}
                          activeDot={{ r: 4 }}
                        />
                      )
                    )}

                {isAccountLevel &&
                  comparePrev &&
                  metrics.map((m, i) => (
                    <Line
                      key={`prev_${m}`}
                      type="monotone"
                      dataKey={`prev_${m}`}
                      yAxisId={i === 1 && metrics[1] ? "right" : "left"}
                      stroke={CHART_COLORS[i]}
                      strokeWidth={1.5}
                      strokeDasharray="4 4"
                      dot={false}
                      opacity={0.5}
                    />
                  ))}

                {!isAccountLevel &&
                  comparePrev &&
                  seriesByEntity.map((e, i) => (
                    <Line
                      key={`prev_${e.entity.id}`}
                      type="monotone"
                      dataKey={`prev_${e.entity.id}`}
                      name={`${e.entity.name} (prev. period)`}
                      yAxisId="left"
                      stroke={CHART_COLORS[i % CHART_COLORS.length]}
                      strokeWidth={1.5}
                      strokeDasharray="4 4"
                      dot={false}
                      opacity={0.5}
                    />
                  ))}
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* ── Breakdown ── */}
      <BreakdownSection />
    </div>
  );
}
