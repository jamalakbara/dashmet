"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Wallet, PieChart } from "lucide-react";
import { MetricGroupCard, type SubMetric } from "@/components/metrics/metric-group-card";
import { PeriodicView } from "@/components/views/periodic-view";
import { FunnelView } from "@/components/views/funnel-view";
import { TableView } from "@/components/views/table-view";
import { AdsView } from "@/components/views/ads-view";
import { insightsApi } from "@/lib/api/insights";
import { queryKeys } from "@/lib/query-keys";
import { useSelectedAccount } from "@/hooks/use-account";
import { useSyncActive } from "@/hooks/use-sync-jobs";
import { useDateRange } from "@/hooks/use-date-range";
import { usePlatform } from "@/hooks/use-platform";
import { useOverviewFilter } from "@/hooks/use-overview-filter";
import { useSharedFilterQuery } from "@/hooks/use-shared-query";
import { staggerGrid } from "@/lib/motion";
import { metricLabel, metricType } from "@/lib/metrics";
import { formatMetric, formatCurrency, formatRoas } from "@/lib/formatters";

interface OverviewSummary {
  [key: string]: number;
}

// Delivery/reach metrics that live under the "Spend" family card.
const DELIVERY_KEYS = [
  "reach", "impressions", "frequency", "ctr", "cpm", "cpc",
  "clicks", "inline_link_clicks", "video_thruplays",
];
// Result/conversion metrics under the second family card.
const RESULT_KEYS = [
  "conversions", "conversion_value", "cpa", "conversion_rate",
  "purchase", "cost_per_purchase", "add_to_cart", "cost_per_add_to_cart",
  "landing_page_views", "leads", "outbound_clicks", "outbound_clicks_ctr",
  "web_purchases", "web_purchase_value", "web_add_to_cart", "result",
  "cost_per_result", "likes", "comments", "shares", "engagement_rate",
];
// First present of these becomes the second card's headline.
const RESULT_HEADLINE = [
  "roas", "conversions", "web_purchases", "result", "engagement_rate", "outbound_clicks",
];

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
      {message}
    </div>
  );
}

function SectionHeading({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div>
      <h2 className="text-lg font-bold tracking-tight">{title}</h2>
      {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
    </div>
  );
}

/** Build the sub-metric rows for a card from the keys present in the summary. */
function buildSubMetrics(
  keys: string[],
  summary: OverviewSummary | undefined,
  currency: string,
  skip?: string,
): SubMetric[] {
  if (!summary) return [];
  return keys
    .filter((k) => k !== skip && summary[k] != null)
    .map((k) => ({
      key: k,
      label: metricLabel(k),
      value: formatMetric(summary[k], metricType(k), currency),
    }));
}

export function OverviewView() {
  const { accountId, currency } = useSelectedAccount();
  const platform = usePlatform() ?? "meta";
  const withQuery = useSharedFilterQuery();
  const dateRange = useDateRange();
  const filter = useOverviewFilter();

  // Poll every section's query while a sync is actually landing (derived from
  // real sync_jobs state), then stop once it's done — replaces a blind 5-min
  // timer, and is shared by every section so they all fill in together.
  const syncActive = useSyncActive();

  const { data: overviewRes, isLoading } = useQuery({
    queryKey: queryKeys.overview(accountId ?? "", dateRange, filter),
    queryFn: () => insightsApi.overview({ account_id: accountId!, ...dateRange, ...filter }),
    enabled: !!accountId,
    staleTime: 15 * 60 * 1000,
    refetchInterval: syncActive ? 5000 : false,
  });

  const summary: OverviewSummary | undefined = overviewRes?.data?.data?.summary;

  if (!accountId) {
    return (
      <EmptyState message="No account selected. Connect an account in Settings → Account Binding." />
    );
  }

  // ── Card 1: Spend family ──
  const spendSub = buildSubMetrics(DELIVERY_KEYS, summary, currency);

  // ── Card 2: Results family (headline is the first present result metric) ──
  const resultHeadlineKey =
    RESULT_HEADLINE.find((k) => summary?.[k] != null) ?? "conversions";
  const resultTitle = metricLabel(resultHeadlineKey);
  const resultHeadline =
    resultHeadlineKey === "roas"
      ? formatRoas(summary?.roas ?? 0)
      : formatMetric(summary?.[resultHeadlineKey], metricType(resultHeadlineKey), currency);
  const resultSub = buildSubMetrics(RESULT_KEYS, summary, currency, resultHeadlineKey);

  return (
    <motion.div {...staggerGrid} className="space-y-6">
      {/* Section heading */}
      <SectionHeading title="Overview" subtitle="Delivery and results for the selected period." />

      {/* Grouped metric cards — items-start so expanding one doesn't stretch the other */}
      <div className="grid items-start gap-4 lg:grid-cols-2">
        <MetricGroupCard
          title="Spend"
          icon={Wallet}
          accent="bg-orange-500"
          headline={formatCurrency(summary?.spend ?? 0, currency)}
          subMetrics={spendSub}
          detailHref={withQuery(`/${platform}/table`)}
          loading={isLoading}
        />
        <MetricGroupCard
          title={resultTitle}
          icon={PieChart}
          accent="bg-emerald-500"
          headline={resultHeadline}
          subMetrics={resultSub}
          detailHref={withQuery(`/${platform}/table`)}
          loading={isLoading}
        />
      </div>

      {/* Trends (periodic charts with metric tabs) */}
      <section className="space-y-3">
        <SectionHeading title="Trends" subtitle="Daily performance over the selected period." />
        <PeriodicView />
      </section>

      {/* Funnel */}
      <section className="space-y-3">
        <SectionHeading title="Funnel" subtitle="Conversion path and step drop-off." />
        <FunnelView />
      </section>

      {/* Table preview → full Table tab */}
      <section className="space-y-3">
        <TableView preview />
      </section>

      {/* Ads preview → full Ads tab */}
      <section className="space-y-3">
        <AdsView preview />
      </section>
    </motion.div>
  );
}
