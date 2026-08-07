"use client";

import { useQuery } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import { motion } from "framer-motion";
import { Card, CardContent } from "@/components/ui/card";
import { SectionHeading } from "@/components/shared/section-heading";
import { DeltaPill } from "@/components/metrics/delta-pill";
import { PeriodicView } from "@/components/views/periodic-view";
import { TableView } from "@/components/views/table-view";
import { TikTokModeSwitch } from "@/components/layout/tiktok-mode-switch";
import { insightsApi } from "@/lib/api/insights";
import { useSelectedAccount } from "@/hooks/use-account";
import { useDateRange } from "@/hooks/use-date-range";
import { useSyncActive } from "@/hooks/use-sync-jobs";
import { metricType } from "@/lib/metrics";
import { formatMetric, formatRoas } from "@/lib/formatters";
import { staggerGrid } from "@/lib/motion";

/**
 * The raw TikTok platform objective that identifies GMV Max / shop-sales
 * campaigns. TikTok's Business API returns `PRODUCT_SALES` as the objective_type
 * for the Product GMV Max / Shop family (GMV Max is a campaign-automation type
 * under it). It's what scopes this whole view (KPIs + table) to those campaigns.
 */
const GMV_MAX_OBJECTIVE = "PRODUCT_SALES";

/**
 * The GMV Max KPI set — the mockup's "TikTok Ads — GMV Max" headline cards,
 * mapped to metrics dashmet actually has. "Net cost" and a separate "ROI" are
 * omitted: dashmet has no refund/adjustment feed to back them, and inventing
 * them would violate P-4 (refuse rather than answer wrong). ROAS (Shop) stands
 * in as the return metric.
 */
const GMV_MAX_KPIS: { key: string; label: string }[] = [
  { key: "spend", label: "Cost" },
  { key: "web_purchase_value", label: "Gross Revenue" },
  { key: "web_purchases", label: "Orders" },
  { key: "cost_per_web_purchase", label: "Cost per Order" },
  { key: "roas_shop", label: "ROAS (Shop)" },
];

function formatKpi(key: string, value: number | null, currency: string): string {
  const type = metricType(key);
  return type === "roas"
    ? formatRoas(Number(value ?? 0))
    : formatMetric(value, type, currency);
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
      {message}
    </div>
  );
}

/** One GMV Max KPI tile: label, headline value, and a cost-inverted delta pill
 *  (silent when there's no comparable previous value, P-2). */
function KpiTile({
  label,
  metricKey,
  current,
  previous,
  currency,
  compare,
  loading,
}: {
  label: string;
  metricKey: string;
  current: number | null;
  previous: number | null;
  currency: string;
  compare: boolean;
  loading: boolean;
}) {
  return (
    <Card className="shadow-[var(--shadow-soft)]">
      <CardContent className="space-y-2">
        <p className="text-xs font-medium text-muted-foreground">{label}</p>
        {loading ? (
          <div className="h-8 w-28 animate-pulse rounded bg-muted" />
        ) : (
          <p className="font-display text-2xl font-semibold tabular-nums">
            {formatKpi(metricKey, current, currency)}
          </p>
        )}
        {compare && !loading && (
          <DeltaPill
            current={current}
            previous={previous}
            metricKey={metricKey}
            variant="inline"
            currency={currency}
          />
        )}
      </CardContent>
    </Card>
  );
}

/**
 * TikTok "GMV Max" (Ads) mode — the one lens of the reference dashboard backed
 * by real data. Composes existing pieces (KPI tiles, the periodic trend chart,
 * and the campaign table) all scoped to `PRODUCT_SALES` campaigns, so the KPIs
 * and table show the same GMV Max numbers by construction (P-6/P-7).
 */
export function GmvMaxView() {
  const { accountId, currency } = useSelectedAccount();
  const dateRange = useDateRange();
  const syncActive = useSyncActive();
  const [compareStr] = useQueryState("compare");
  const compare = compareStr === "true";

  const { data: res, isLoading } = useQuery({
    queryKey: ["gmv-max-overview", accountId ?? "", dateRange, GMV_MAX_OBJECTIVE],
    queryFn: () =>
      insightsApi.overview({
        account_id: accountId!,
        ...dateRange,
        platform_objective: GMV_MAX_OBJECTIVE,
      }),
    enabled: !!accountId,
    staleTime: 15 * 60 * 1000,
    refetchInterval: syncActive ? 5000 : false,
  });

  const summary: Record<string, number | null> | undefined =
    res?.data?.data?.summary;
  const previous: Record<string, number | null> | undefined =
    res?.data?.data?.previous;

  if (!accountId) {
    return <EmptyState message="No account selected. Connect a TikTok account in Settings → Connections." />;
  }

  return (
    <motion.div {...staggerGrid} className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionHeading
          title="TikTok Ads — GMV Max"
          subtitle="Shop-optimized ad delivery and results for the selected period."
        />
        <TikTokModeSwitch value="ads" />
      </div>

      {/* KPI tiles — scoped to GMV Max (PRODUCT_SALES) campaigns. */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {GMV_MAX_KPIS.map((kpi) => (
          <KpiTile
            key={kpi.key}
            label={kpi.label}
            metricKey={kpi.key}
            current={summary?.[kpi.key] ?? null}
            previous={previous?.[kpi.key] ?? null}
            currency={currency}
            compare={compare}
            loading={isLoading}
          />
        ))}
      </div>

      {/* Trends — the periodic chart with metric tabs (Cost / Gross Revenue /
          Orders / Cost per Order / ROAS are all selectable TikTok metrics). */}
      <section className="space-y-3">
        <SectionHeading title="Trends" subtitle="Daily performance over the selected period." />
        <PeriodicView />
      </section>

      {/* GMV Max campaigns — the campaign table filtered to PRODUCT_SALES. */}
      <section className="space-y-3">
        <SectionHeading title="GMV Max campaigns" subtitle="Product GMV Max campaigns and their delivery." />
        <TableView platformObjective={GMV_MAX_OBJECTIVE} />
      </section>
    </motion.div>
  );
}
