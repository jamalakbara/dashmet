"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import { formatDistanceToNow } from "date-fns";
import { motion } from "framer-motion";
import { Wallet, PieChart, Sparkles, AlertTriangle, RotateCw } from "lucide-react";
import { MetricGroupCard, type SubMetric } from "@/components/metrics/metric-group-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
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

interface OverviewMetrics {
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
  summary: OverviewMetrics | undefined,
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
      raw: summary[k],
    }));
}

/**
 * On-demand AI narrative summary of the overview. On mount we PEEK the cache
 * (a safe, token-free GET) so an existing diagnosis shows instantly; generation
 * stays opt-in (a click) so token spend is always intentional (P-5). The
 * narrative is anchored to the same period/model returned by the endpoint so it
 * reads against the numbers shown on screen (P-1). On failure we surface the
 * backend's `detail` verbatim with a retry — never a silent/empty card or a
 * fabricated summary (P-4).
 */
function AiSummaryCard({
  accountId,
  dateRange,
  filter,
}: {
  accountId: string;
  dateRange: ReturnType<typeof useDateRange>;
  filter: ReturnType<typeof useOverviewFilter>;
}) {
  const queryClient = useQueryClient();

  // Cache-only peek — never spends tokens, so it's safe to auto-run on mount.
  const peekKey = ["overview-summary-peek", accountId, dateRange, filter] as const;
  const peek = useQuery({
    queryKey: peekKey,
    queryFn: () =>
      insightsApi.peekSummary({ account_id: accountId, ...dateRange, ...filter }),
    staleTime: 15 * 60 * 1000,
  });

  const summary = useMutation({
    mutationFn: (force: boolean) =>
      insightsApi.generateSummary({
        account_id: accountId,
        ...dateRange,
        ...filter,
        force,
      }),
    // Keep the peek cache in lockstep with what we just generated so the shown
    // summary and any remount stay consistent (a remount re-runs peek → hit).
    onSuccess: (data) => queryClient.setQueryData(peekKey, data),
  });

  // Display precedence: freshest first. A just-generated mutation result wins
  // over the cached peek; both fall back to idle when neither has a summary.
  const data = summary.data ?? peek.data ?? null;

  const errorDetail =
    (summary.error as { response?: { data?: { detail?: string } } })?.response?.data
      ?.detail ?? "Couldn't generate the AI summary. Try again.";

  const asOf = data?.data_as_of
    ? formatDistanceToNow(new Date(data.data_as_of), { addSuffix: true })
    : null;

  const showSkeleton = summary.isPending || (peek.isLoading && !summary.data);

  return (
    <section className="space-y-3">
      <SectionHeading
        title="AI Summary"
        subtitle="A grounded narrative of what changed this period."
      />
      <Card>
        <CardContent className="space-y-4">
          {showSkeleton ? (
            <div className="space-y-4" aria-busy>
              <div className="h-5 w-3/4 animate-pulse rounded bg-muted" />
              {[0, 1, 2].map((i) => (
                <div key={i} className="space-y-2">
                  <div className="h-3 w-24 animate-pulse rounded bg-muted" />
                  <div className="h-4 w-11/12 animate-pulse rounded bg-muted" />
                </div>
              ))}
            </div>
          ) : summary.isError ? (
            <Alert variant="destructive">
              <AlertTriangle />
              <AlertTitle>AI summary failed</AlertTitle>
              <AlertDescription>
                <p>{errorDetail}</p>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => summary.mutate(true)}
                  className="mt-2 gap-2"
                >
                  <RotateCw className="size-4" />
                  Retry
                </Button>
              </AlertDescription>
            </Alert>
          ) : data ? (
            <div className="space-y-4">
              {/* Headline reads as the lead — larger and heavier than the rest. */}
              <p className="text-base font-semibold leading-snug text-foreground">
                {data.headline}
              </p>
              <div className="space-y-3">
                {(
                  [
                    { label: "Likely driver", text: data.driver },
                    { label: "Watch", text: data.watch },
                    { label: "Next", text: data.next_step },
                  ] as const
                ).map((section) => (
                  <div key={section.label} className="space-y-1">
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {section.label}
                    </p>
                    <p className="text-sm leading-relaxed whitespace-pre-line text-foreground">
                      {section.text}
                    </p>
                  </div>
                ))}
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
                <p className="text-xs text-muted-foreground">
                  {data.period.date_start} – {data.period.date_stop}
                  {" · "}
                  {data.model}
                  {asOf && (
                    <>
                      {" · "}
                      Data as of {asOf}
                    </>
                  )}
                </p>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => summary.mutate(true)}
                  className="gap-2"
                >
                  <RotateCw className="size-4" />
                  Regenerate
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-start gap-2">
              <Button onClick={() => summary.mutate(false)} className="gap-2">
                <Sparkles className="size-4" />
                Generate AI summary
              </Button>
              <p className="text-xs text-muted-foreground">
                Uses AI · counts toward token usage
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

export function OverviewView() {
  const { accountId, currency } = useSelectedAccount();
  const platform = usePlatform() ?? "meta";
  const withQuery = useSharedFilterQuery();
  const dateRange = useDateRange();
  const filter = useOverviewFilter();
  const [compareStr] = useQueryState("compare");
  const compare = compareStr === "true";

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

  const summary: OverviewMetrics | undefined = overviewRes?.data?.data?.summary;
  const previous: Record<string, number | null> | undefined =
    overviewRes?.data?.data?.previous;

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
          headlineKey="spend"
          headlineValue={summary?.spend ?? null}
          subMetrics={spendSub}
          detailHref={withQuery(`/${platform}/table`)}
          loading={isLoading}
          compare={compare}
          previous={previous}
          currency={currency}
        />
        <MetricGroupCard
          title={resultTitle}
          icon={PieChart}
          accent="bg-emerald-500"
          headline={resultHeadline}
          headlineKey={resultHeadlineKey}
          headlineValue={summary?.[resultHeadlineKey] ?? null}
          subMetrics={resultSub}
          detailHref={withQuery(`/${platform}/table`)}
          loading={isLoading}
          compare={compare}
          previous={previous}
          currency={currency}
        />
      </div>

      {/* AI narrative summary (on-demand, grounded in the same overview numbers).
          Keyed on account + period + filter so a context change remounts the
          card back to its idle state — a summary is only ever shown against the
          numbers it was generated for (P-1), never left stale after the period
          changes. Regeneration stays an explicit click (no auto token spend). */}
      <AiSummaryCard
        key={`${accountId}:${JSON.stringify(dateRange)}:${JSON.stringify(filter)}`}
        accountId={accountId}
        dateRange={dateRange}
        filter={filter}
      />

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
