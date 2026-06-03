import type { MetricType } from "@/lib/formatters";
import type { AccountType } from "@/types/enums";

export interface MetricDef {
  key: string;
  label: string;
  type: MetricType;
  align: "left" | "right";
  platforms: string[];
  accountTypes: AccountType[];
  showInKpi: boolean;
  showInPeriodic: boolean;
  showInTable: boolean;
  tableDefaultVisible: boolean;
}

export const METRIC_REGISTRY: MetricDef[] = [
  // ── Shared (meta + tiktok, both account types) ───────────────────────
  { key: "spend",       label: "Spend",       type: "currency", align: "right", platforms: ["meta","tiktok"], accountTypes: ["standard","cpas"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:true  },
  { key: "impressions", label: "Impressions", type: "number",   align: "right", platforms: ["meta","tiktok"], accountTypes: ["standard","cpas"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:true  },
  { key: "reach",       label: "Reach",       type: "number",   align: "right", platforms: ["meta","tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true,  showInTable:true,  tableDefaultVisible:false },
  { key: "frequency",   label: "Frequency",   type: "number",   align: "right", platforms: ["meta","tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:false, showInTable:false, tableDefaultVisible:false },
  { key: "clicks",      label: "Clicks",      type: "number",   align: "right", platforms: ["meta","tiktok"], accountTypes: ["standard","cpas"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:true  },
  { key: "ctr",         label: "CTR",         type: "percent",  align: "right", platforms: ["meta","tiktok"], accountTypes: ["standard","cpas"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:true  },
  { key: "cpm",         label: "CPM",         type: "currency", align: "right", platforms: ["meta","tiktok"], accountTypes: ["standard","cpas"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:false },
  { key: "cpc",         label: "CPC",         type: "currency", align: "right", platforms: ["meta","tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true,  showInTable:true,  tableDefaultVisible:false },
  // ── Meta standard-only ────────────────────────────────────────────────
  { key: "inline_link_clicks", label: "Link Clicks",  type: "number",   align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:false, showInTable:false, tableDefaultVisible:false },
  { key: "cpp",              label: "CPP",         type: "currency", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:false, showInTable:false, tableDefaultVisible:false },
  { key: "conversions",      label: "Conversions", type: "number",   align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:true  },
  { key: "conversion_value", label: "Conv. Value", type: "currency", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:false, showInTable:true,  tableDefaultVisible:false },
  { key: "roas",             label: "ROAS",        type: "roas",     align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:true  },
  { key: "cpa",              label: "CPA",         type: "currency", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true,  showInTable:true,  tableDefaultVisible:false },
  // ── Meta CPAS-primary ─────────────────────────────────────────────────
  { key: "outbound_clicks",         label: "Outbound Clicks",     type: "number",   align: "right", platforms: ["meta"], accountTypes: ["cpas"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:true  },
  { key: "outbound_clicks_ctr",     label: "Outbound CTR",        type: "percent",  align: "right", platforms: ["meta"], accountTypes: ["cpas"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:true  },
  { key: "cost_per_outbound_click", label: "Cost/Outbound Click", type: "currency", align: "right", platforms: ["meta"], accountTypes: ["cpas"], showInKpi:false, showInPeriodic:true,  showInTable:true,  tableDefaultVisible:false },
];

export function getMetricsForPlatform(
  platform: string | null | undefined,
  accountType: AccountType | null = null,
): MetricDef[] {
  return METRIC_REGISTRY.filter(
    (m) =>
      (!platform || m.platforms.includes(platform)) &&
      (!accountType || m.accountTypes.includes(accountType)),
  );
}

export const getKpiMetrics = (p: string | null | undefined, at: AccountType | null = null) =>
  getMetricsForPlatform(p, at).filter((m) => m.showInKpi);
export const getSelectableMetrics = (p: string | null | undefined, at: AccountType | null = null) =>
  getMetricsForPlatform(p, at).filter((m) => m.showInPeriodic);
export const getTableMetricCols = (p: string | null | undefined, at: AccountType | null = null) =>
  getMetricsForPlatform(p, at).filter((m) => m.showInTable);
