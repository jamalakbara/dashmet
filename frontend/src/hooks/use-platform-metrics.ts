"use client";

import { useMemo } from "react";
import { useSelectedAccount } from "@/hooks/use-account";
import { getKpiMetrics, getSelectableMetrics, getTableMetricCols, type MetricDef } from "@/lib/metrics";
import type { AccountType } from "@/types/enums";

export interface PlatformMetrics {
  kpiMetrics: MetricDef[];
  selectableMetrics: MetricDef[];
  tableMetricDefs: MetricDef[];
  currency: string;
  platform: string | null;
  accountType: AccountType | null;
}

export function usePlatformMetrics(): PlatformMetrics {
  const { platform, currency, accountType } = useSelectedAccount();

  const kpiMetrics       = useMemo(() => getKpiMetrics(platform, accountType),       [platform, accountType]);
  const selectableMetrics = useMemo(() => getSelectableMetrics(platform, accountType), [platform, accountType]);
  const tableMetricDefs  = useMemo(() => getTableMetricCols(platform, accountType),  [platform, accountType]);

  return { kpiMetrics, selectableMetrics, tableMetricDefs, currency, platform, accountType };
}
