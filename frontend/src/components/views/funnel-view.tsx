"use client";

import { useQuery } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DeltaPill } from "@/components/metrics/delta-pill";
import { insightsApi } from "@/lib/api/insights";
import { queryKeys } from "@/lib/query-keys";
import { useSelectedAccount } from "@/hooks/use-account";
import { useDateRange } from "@/hooks/use-date-range";
import { usePlatform } from "@/hooks/use-platform";
import { useOverviewFilter } from "@/hooks/use-overview-filter";
import { FUNNEL_STEPS, CHART_COLORS } from "@/lib/constants";
import { formatMetric, formatPercent } from "@/lib/formatters";

// Step key → the cost-per-step metric key (when one exists in the overview summary).
const COST_KEY: Record<string, string> = {
  impressions: "cpm",
  clicks: "cpc",
  view_content: "cost_per_view_content",
  add_to_cart: "cost_per_add_to_cart",
  initiate_checkout: "cost_per_initiate_checkout",
  purchase: "cost_per_purchase",
  web_add_to_cart: "cost_per_web_add_to_cart",
  web_purchases: "cost_per_web_purchase",
  conversions: "cpa",
};

type Summary = Record<string, number | null | undefined>;

export function FunnelView() {
  const { accountId, currency } = useSelectedAccount();
  const platform = usePlatform() ?? "meta";
  const dateRange = useDateRange();
  const filter = useOverviewFilter();
  const [compareStr] = useQueryState("compare");
  const compare = compareStr === "true";

  const { data: res, isLoading } = useQuery({
    queryKey: queryKeys.overview(accountId ?? "", dateRange, filter),
    queryFn: () => insightsApi.overview({ account_id: accountId!, ...dateRange, ...filter }),
    enabled: !!accountId,
    staleTime: 15 * 60 * 1000,
  });

  if (!accountId) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        No account selected.
      </div>
    );
  }

  const summary: Summary = res?.data?.data?.summary ?? {};
  const previous: Summary = res?.data?.data?.previous ?? {};
  const allSteps = FUNNEL_STEPS[platform] ?? FUNNEL_STEPS.meta;

  // Keep only steps that actually have data (so no-Pixel accounts collapse cleanly).
  const steps = allSteps
    .map((s) => ({ ...s, value: Number(summary[s.key] ?? 0) }))
    .filter((s) => s.value > 0);

  const topValue = steps.length ? steps[0].value : 0;

  return (
    <div className="space-y-6">
      <Card className="shadow-[var(--shadow-soft)]">
        <CardHeader className="pb-2">
          <CardTitle className="font-display text-sm font-semibold">Conversion funnel</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-12 animate-pulse rounded bg-muted" />
              ))}
            </div>
          ) : steps.length === 0 ? (
            <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
              No funnel data for selected period
            </div>
          ) : (
            <div className="space-y-1">
              {steps.map((step, i) => {
                const pctOfTop = topValue > 0 ? (step.value / topValue) * 100 : 0;
                const prev = i > 0 ? steps[i - 1] : null;
                const stepRate =
                  prev && prev.value > 0 ? (step.value / prev.value) * 100 : null;
                const costKey = COST_KEY[step.key];
                const cost = costKey ? summary[costKey] : null;
                const color = CHART_COLORS[i % CHART_COLORS.length];

                // Bar fill is power-scaled so deep steps stay visible instead of
                // collapsing to a 2% sliver. The real share is the "% of top" text.
                const fillPct =
                  topValue > 0
                    ? Math.max(Math.pow(step.value / topValue, 0.4) * 100, 6)
                    : 0;

                return (
                  <div key={step.key}>
                    {/* Conversion connector between this step and the one above */}
                    {prev && (
                      <div className="flex items-center gap-1.5 pl-36 text-[11px] text-muted-foreground">
                        <span aria-hidden>↳</span>
                        <span className="font-medium text-foreground">
                          {formatPercent(stepRate)}
                        </span>
                        <span>continue</span>
                        {cost != null && (
                          <span className="text-muted-foreground/70">
                            · {formatMetric(cost as number, "currency", currency)}/ea
                          </span>
                        )}
                      </div>
                    )}

                    {/* Step row: label · bar · value · share */}
                    <div className="flex items-center gap-3 py-1">
                      <div className="w-32 shrink-0 truncate text-sm font-medium">
                        {step.label}
                      </div>
                      <div className="h-9 flex-1 overflow-hidden rounded-lg bg-muted/40">
                        <div
                          className="h-full rounded-lg transition-all"
                          style={{ width: `${fillPct}%`, backgroundColor: color }}
                        />
                      </div>
                      <div className="w-44 shrink-0 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <span className="font-display text-sm font-semibold tabular-nums">
                            {formatMetric(step.value, "number", currency)}
                          </span>
                          {compare && (
                            <DeltaPill
                              current={step.value}
                              previous={previous[step.key]}
                              metricKey={step.key}
                              variant="inline"
                              valueType="number"
                              currency={currency}
                            />
                          )}
                        </div>
                        <div className="text-[11px] tabular-nums text-muted-foreground">
                          {formatPercent(pctOfTop)} of top
                          {compare && previous[step.key] != null && (
                            <> · vs {formatMetric(previous[step.key], "number", currency)}</>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
