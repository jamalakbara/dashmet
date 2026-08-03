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
import { cn } from "@/lib/utils";

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
            <div className="space-y-2">
              {steps.map((step, i) => {
                const pctOfTop = topValue > 0 ? (step.value / topValue) * 100 : 0;
                const prev = i > 0 ? steps[i - 1] : null;
                const stepRate =
                  prev && prev.value > 0 ? (step.value / prev.value) * 100 : null;
                const costKey = COST_KEY[step.key];
                const cost = costKey ? summary[costKey] : null;
                const color = CHART_COLORS[i % CHART_COLORS.length];

                return (
                  <div key={step.key} className="flex items-center gap-3">
                    {/* Label + bar */}
                    <div className="w-40 shrink-0 text-sm font-medium">{step.label}</div>
                    <div className="relative h-10 flex-1 rounded bg-muted/40">
                      <div
                        className={cn(
                          "flex h-full items-center rounded px-3 text-sm font-medium text-white transition-all",
                          pctOfTop < 18 && "justify-end pr-0 text-foreground",
                        )}
                        style={{
                          width: `${Math.max(pctOfTop, 2)}%`,
                          backgroundColor: color,
                        }}
                      >
                        <span className={cn(pctOfTop < 18 && "ml-2 text-foreground")}>
                          {formatMetric(step.value, "number", currency)}
                        </span>
                      </div>
                    </div>
                    {/* Right-side stats */}
                    <div className="w-44 shrink-0 text-right text-xs text-muted-foreground">
                      {compare && (
                        <div className="mb-0.5 flex justify-end">
                          <DeltaPill
                            current={step.value}
                            previous={previous[step.key]}
                            metricKey={step.key}
                            variant="inline"
                            valueType="number"
                            currency={currency}
                          />
                        </div>
                      )}
                      <div>{formatPercent(pctOfTop)} of top</div>
                      <div>
                        {stepRate !== null ? `${formatPercent(stepRate)} from prev` : "—"}
                        {cost != null
                          ? ` · ${formatMetric(cost as number, "currency", currency)}/ea`
                          : ""}
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
