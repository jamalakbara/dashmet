"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import { formatDistanceToNow } from "date-fns";
import { motion } from "framer-motion";
import {
  Wallet,
  PieChart,
  Clapperboard,
  Sparkles,
  AlertTriangle,
  RotateCw,
  type LucideIcon,
} from "lucide-react";
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
import { useIsOwner } from "@/hooks/use-role";
import { useOverviewFilter } from "@/hooks/use-overview-filter";
import { useSharedFilterQuery } from "@/hooks/use-shared-query";
import { staggerGrid } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { metricLabel, metricType } from "@/lib/metrics";
import { formatMetric, formatRoas } from "@/lib/formatters";
import type { AccountType } from "@/types/enums";

interface OverviewMetrics {
  [key: string]: number;
}

/**
 * One grouped overview card. `headlineKey` omitted → a title-only card (the grid
 * with no big number, e.g. Post & Media). `keys` are the sub-metrics, filtered
 * at render to those actually present in the summary (P-1/P-2). `headlineKey`,
 * when present, is excluded from `keys` so it isn't duplicated in the grid.
 */
interface CardSpec {
  title: string;
  icon: LucideIcon;
  accent: string;
  headlineKey?: string;
  keys: string[];
  /** Outer grid column span on `lg` (default 1). `2` makes the card full-width. */
  span?: 1 | 2;
  /** Inner sub-metric grid column count (default 2). `4` lays 8 metrics as 2×4. */
  cols?: 2 | 4;
}

/**
 * Account-type-scoped card definitions. STRICTLY separated: a standard account
 * renders zero `*_shared` metrics, a cpas account renders none of the standard
 * ROAS / Post & Media metrics. Driven off `accountType` from the selected
 * account — never mixed. Keys absent from the summary are dropped silently.
 */
const OVERVIEW_CARDS: Record<AccountType, CardSpec[]> = {
  standard: [
    {
      title: "Spend",
      icon: Wallet,
      accent: "bg-orange-500",
      headlineKey: "spend",
      keys: [
        "reach", "impressions", "frequency", "ctr", "cpm",
        "inline_link_clicks", "clicks", "cpc",
        "landing_page_views", "cost_per_landing_page_view",
      ],
    },
    {
      title: "ROAS",
      icon: PieChart,
      accent: "bg-emerald-500",
      headlineKey: "roas",
      keys: [
        "purchase", "conversion_value", "cost_per_purchase",
        "add_to_cart", "add_to_cart_value", "cost_per_add_to_cart",
        "conversion_rate", "avg_basket_price",
      ],
    },
    {
      title: "Post & Media",
      icon: Clapperboard,
      accent: "bg-violet-500",
      // Full-width bottom row: 8 metrics laid out as two rows of 4 so the card
      // fills the space left by an odd (3-card) count in a 2-col grid.
      span: 2,
      cols: 4,
      keys: [
        "inline_post_engagement", "post_saves", "post_reactions", "comments",
        "video_thruplays", "video_views", "video_p100", "video_avg_time",
      ],
    },
  ],
  cpas: [
    {
      title: "Spend",
      icon: Wallet,
      accent: "bg-orange-500",
      headlineKey: "spend",
      keys: [
        "reach", "impressions", "ctr", "cpm",
        "inline_link_clicks", "clicks", "cpc",
      ],
    },
    {
      title: "ROAS Shared Item",
      icon: PieChart,
      accent: "bg-emerald-500",
      headlineKey: "roas_shared",
      keys: [
        "purchase_shared", "purchase_value_shared", "cost_per_purchase_shared",
        "add_to_cart_shared", "add_to_cart_value_shared", "cost_per_add_to_cart_shared",
        "content_view_shared", "cost_per_content_view_shared",
      ],
    },
  ],
};

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

/** Format a card's headline value by its metric type (roas has its own formatter). */
function formatHeadline(
  key: string,
  summary: OverviewMetrics | undefined,
  currency: string,
): string {
  const type = metricType(key);
  const value = summary?.[key] ?? null;
  return type === "roas"
    ? formatRoas(Number(value ?? 0))
    : formatMetric(value, type, currency);
}

export function OverviewView() {
  const { accountId, currency, accountType } = useSelectedAccount();
  const isOwner = useIsOwner();
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
      <EmptyState
        message={
          isOwner
            ? "No account selected. Connect an account in Settings → Connections."
            : "No accounts assigned to you yet. Ask your organization owner to grant access."
        }
      />
    );
  }

  // Account-type-scoped card set. Standard → 3 cards (Spend / ROAS / Post &
  // Media); cpas → 2 cards (Spend / ROAS Shared Item). Falls back to standard
  // when the account type isn't yet resolved. Strict separation is guaranteed
  // by keying the config on accountType — no card ever mixes the two sets.
  const cards = OVERVIEW_CARDS[accountType ?? "standard"];

  return (
    <motion.div {...staggerGrid} className="space-y-6">
      {/* Section heading */}
      <SectionHeading title="Overview" subtitle="Delivery and results for the selected period." />

      {/* Grouped metric cards — items-start so expanding one doesn't stretch the
          others. Rendered from the account-type-scoped config so standard and
          cpas never share a card set. */}
      <div className="grid items-start gap-4 lg:grid-cols-2">
        {cards.map((card) => {
          const hasHeadline = card.headlineKey != null;
          const subMetrics = buildSubMetrics(
            card.keys,
            summary,
            currency,
            card.headlineKey,
          );
          const columns = card.cols ?? 2;
          return (
            <MetricGroupCard
              key={card.title}
              className={cn(card.span === 2 && "lg:col-span-2")}
              title={card.title}
              icon={card.icon}
              accent={card.accent}
              columns={columns}
              // A wide 4-col card previews a full row (columns) rather than the
              // default 4, so both of its two rows stay visible without "See More".
              previewCount={columns === 4 ? subMetrics.length : undefined}
              headline={
                hasHeadline
                  ? formatHeadline(card.headlineKey!, summary, currency)
                  : undefined
              }
              headlineKey={card.headlineKey}
              headlineValue={hasHeadline ? summary?.[card.headlineKey!] ?? null : null}
              subMetrics={subMetrics}
              detailHref={withQuery(`/${platform}/table`)}
              loading={isLoading}
              compare={compare}
              previous={previous}
              currency={currency}
            />
          );
        })}
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
