"use client";

import { useQuery } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { insightsApi } from "@/lib/api/insights";
import { queryKeys } from "@/lib/query-keys";
import { useAccountId } from "@/hooks/use-account";
import { useDateRange } from "@/hooks/use-date-range";
import { usePlatformMetrics } from "@/hooks/use-platform-metrics";
import { CHART_COLORS } from "@/lib/constants";
import { formatCurrency } from "@/lib/formatters";

interface BreakdownRow {
  breakdown_value: string;
  dimensions: Record<string, string>;
  metrics: Record<string, number>;
}

const GENDER_COLORS: Record<string, string> = {
  female: CHART_COLORS[3],
  male: CHART_COLORS[0],
  unknown: CHART_COLORS[5],
};

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

export function AgeGenderChart({ rows, loading, currency }: { rows: BreakdownRow[]; loading: boolean; currency: string }) {
  if (loading) return <SkeletonChart height={280} />;
  if (!rows.length) return <Empty />;

  const ages = [...new Set(rows.map((r) => r.dimensions.age))].sort();
  const genders = [...new Set(rows.map((r) => r.dimensions.gender))];

  const data = ages.map((age) => {
    const entry: Record<string, unknown> = { age };
    genders.forEach((g) => {
      const row = rows.find((r) => r.dimensions.age === age && r.dimensions.gender === g);
      entry[g] = row?.metrics.spend ?? 0;
    });
    return entry;
  });

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" horizontal={false} />
        <XAxis type="number" tickFormatter={(v) => formatCurrency(v, currency)} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey="age" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={48} />
        <Tooltip formatter={(v) => formatCurrency(v as number, currency)} contentStyle={{ fontSize: 12 }} />
        <Legend />
        {genders.map((g) => (
          <Bar key={g} dataKey={g} name={g.charAt(0).toUpperCase() + g.slice(1)} fill={GENDER_COLORS[g] ?? CHART_COLORS[2]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function CountryChart({ rows, loading, currency }: { rows: BreakdownRow[]; loading: boolean; currency: string }) {
  if (loading) return <SkeletonChart height={280} />;
  if (!rows.length) return <Empty />;

  const data = [...rows]
    .sort((a, b) => (b.metrics.spend ?? 0) - (a.metrics.spend ?? 0))
    .slice(0, 10)
    .map((r) => ({
      country: r.dimensions.country ?? r.breakdown_value,
      spend: r.metrics.spend ?? 0,
    }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" horizontal={false} />
        <XAxis type="number" tickFormatter={(v) => formatCurrency(v, currency)} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey="country" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={32} />
        <Tooltip formatter={(v) => [formatCurrency(v as number, currency), "Spend"]} contentStyle={{ fontSize: 12 }} />
        <Bar dataKey="spend" fill={CHART_COLORS[0]} radius={2} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function PlatformChart({ rows, loading, currency }: { rows: BreakdownRow[]; loading: boolean; currency: string }) {
  if (loading) return <SkeletonChart height={280} />;
  if (!rows.length) return <Empty />;

  const platforms = [...new Set(rows.map((r) => r.dimensions.publisher_platform))];
  const positions = [...new Set(rows.map((r) => r.dimensions.platform_position))];

  const data = platforms.map((platform) => {
    const entry: Record<string, unknown> = { platform };
    rows
      .filter((r) => r.dimensions.publisher_platform === platform)
      .forEach((r) => { entry[r.dimensions.platform_position] = r.metrics.spend ?? 0; });
    return entry;
  });

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" horizontal={false} />
        <XAxis type="number" tickFormatter={(v) => formatCurrency(v, currency)} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey="platform" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={72} />
        <Tooltip formatter={(v) => [formatCurrency(v as number, currency), "Spend"]} contentStyle={{ fontSize: 12 }} />
        <Legend />
        {positions.map((pos, i) => (
          <Bar key={`${pos ?? "unknown"}-${i}`} dataKey={pos} stackId="a" fill={CHART_COLORS[i % CHART_COLORS.length]} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function DeviceChart({ rows, loading }: { rows: BreakdownRow[]; loading: boolean }) {
  if (loading) return <SkeletonChart height={280} />;
  if (!rows.length) return <Empty />;

  const data = rows.map((r) => ({
    name: r.dimensions.device ?? r.breakdown_value,
    value: r.metrics.impressions ?? 0,
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          cx="50%"
          cy="50%"
          innerRadius={70}
          outerRadius={110}
          paddingAngle={2}
          label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
          labelLine={false}
        >
          {data.map((_, i) => (
            <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
          ))}
        </Pie>
        <Tooltip formatter={(v) => [Number(v).toLocaleString(), "Impressions"]} contentStyle={{ fontSize: 12 }} />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );
}

/**
 * Self-contained breakdown card: tabbed age-gender / country / platform / device
 * charts, fetched from /insights/breakdown for the active account. Shared by the
 * Periodic view and the Meta Breakdowns page.
 */
export function BreakdownSection() {
  const accountId = useAccountId();
  const dateRange = useDateRange();
  const { currency } = usePlatformMetrics();
  const [activeBreakdown, setActiveBreakdown] = useQueryState("breakdown", {
    defaultValue: "age_gender",
  });

  const { data: bdRes, isLoading: bdLoading } = useQuery({
    queryKey: queryKeys.breakdown(accountId ?? "", dateRange, activeBreakdown ?? ""),
    queryFn: () =>
      insightsApi.breakdown({
        account_id: accountId!,
        ...dateRange,
        breakdown_type: activeBreakdown!,
        level: "account",
      }),
    enabled: !!accountId && !!activeBreakdown,
    staleTime: 30 * 60 * 1000,
  });

  const bdRows: BreakdownRow[] = bdRes?.data?.data?.rows ?? [];

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">Breakdown</CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs value={activeBreakdown ?? "age_gender"} onValueChange={(v) => setActiveBreakdown(v)}>
          <TabsList>
            <TabsTrigger value="age_gender">Age & Gender</TabsTrigger>
            <TabsTrigger value="country">Country</TabsTrigger>
            <TabsTrigger value="platform_position">Platform</TabsTrigger>
            <TabsTrigger value="device">Device</TabsTrigger>
          </TabsList>

          <TabsContent value="age_gender" className="mt-4">
            <AgeGenderChart rows={bdRows} loading={bdLoading} currency={currency} />
          </TabsContent>
          <TabsContent value="country" className="mt-4">
            <CountryChart rows={bdRows} loading={bdLoading} currency={currency} />
          </TabsContent>
          <TabsContent value="platform_position" className="mt-4">
            <PlatformChart rows={bdRows} loading={bdLoading} currency={currency} />
          </TabsContent>
          <TabsContent value="device" className="mt-4">
            <DeviceChart rows={bdRows} loading={bdLoading} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
