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
  { key: "spend",       label: "Spend",       type: "currency", align: "right", platforms: ["meta","tiktok","google_ads"], accountTypes: ["standard","cpas"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:true  },
  { key: "impressions", label: "Impressions", type: "number",   align: "right", platforms: ["meta","tiktok","google_ads"], accountTypes: ["standard","cpas"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:true  },
  { key: "reach",       label: "Reach",       type: "number",   align: "right", platforms: ["meta","tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true,  showInTable:true,  tableDefaultVisible:false },
  { key: "frequency",   label: "Frequency",   type: "number",   align: "right", platforms: ["meta","tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:false, showInTable:false, tableDefaultVisible:false },
  { key: "clicks",      label: "Clicks",      type: "number",   align: "right", platforms: ["meta","tiktok","google_ads"], accountTypes: ["standard","cpas"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:true  },
  { key: "ctr",         label: "CTR",         type: "percent",  align: "right", platforms: ["meta","tiktok","google_ads"], accountTypes: ["standard","cpas"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:true  },
  { key: "cpm",         label: "CPM",         type: "currency", align: "right", platforms: ["meta","tiktok","google_ads"], accountTypes: ["standard","cpas"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:false },
  { key: "cpc",         label: "CPC",         type: "currency", align: "right", platforms: ["meta","tiktok","google_ads"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true,  showInTable:true,  tableDefaultVisible:false },
  // ── Meta standard-only ────────────────────────────────────────────────
  { key: "inline_link_clicks", label: "Link Clicks",  type: "number",   align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:false, showInTable:false, tableDefaultVisible:false },
  { key: "cpp",              label: "CPP",         type: "currency", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:false, showInTable:false, tableDefaultVisible:false },
  { key: "conversions",      label: "Conversions", type: "number",   align: "right", platforms: ["meta","tiktok","google_ads"], accountTypes: ["standard"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:true  },
  { key: "conversion_value", label: "Conv. Value", type: "currency", align: "right", platforms: ["meta","google_ads"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:false, showInTable:true,  tableDefaultVisible:false },
  { key: "roas",             label: "ROAS",        type: "roas",     align: "right", platforms: ["meta","google_ads"], accountTypes: ["standard"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:true  },
  { key: "cpa",              label: "CPA",         type: "currency", align: "right", platforms: ["meta","tiktok","google_ads"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true,  showInTable:true,  tableDefaultVisible:false },
  { key: "conversion_rate",  label: "CVR",         type: "percent",  align: "right", platforms: ["meta","tiktok","google_ads"], accountTypes: ["standard"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:false },
  // ── Meta CPAS-primary ─────────────────────────────────────────────────
  { key: "outbound_clicks",         label: "Outbound Clicks",     type: "number",   align: "right", platforms: ["meta"], accountTypes: ["cpas"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:true  },
  { key: "outbound_clicks_ctr",     label: "Outbound CTR",        type: "percent",  align: "right", platforms: ["meta"], accountTypes: ["cpas"], showInKpi:true,  showInPeriodic:true,  showInTable:true,  tableDefaultVisible:true  },
  { key: "cost_per_outbound_click", label: "Cost/Outbound Click", type: "currency", align: "right", platforms: ["meta"], accountTypes: ["cpas"], showInKpi:false, showInPeriodic:true,  showInTable:true,  tableDefaultVisible:false },

  // ── Meta conversion detail (from the synced `actions` array) ──────────
  { key: "add_to_cart",        label: "Add to Cart",        type: "number", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "initiate_checkout",  label: "Checkouts",          type: "number", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "landing_page_views", label: "Landing Page Views", type: "number", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "leads",              label: "Leads",              type: "number", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },

  // ── Meta engagement & recall (metrics_daily scalar columns) ──────────
  { key: "inline_post_engagement",          label: "Post Engagement",  type: "number",   align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "cost_per_inline_post_engagement", label: "Cost/Engagement",  type: "currency", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "estimated_ad_recall_rate",        label: "Est. Recall Rate", type: "percent",  align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "estimated_ad_recallers",          label: "Est. Recallers",   type: "number",   align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },

  // ── Meta-specific video depth ─────────────────────────────────────────
  { key: "video_2s",         label: "2s Views",       type: "number", align: "right", platforms: ["meta"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "video_thruplays",  label: "ThruPlays",      type: "number", align: "right", platforms: ["meta"], accountTypes: ["standard","cpas"], showInKpi:true,  showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "video_avg_time",   label: "Avg Watch Time", type: "number", align: "right", platforms: ["meta"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },

  // ── Shared video stages (identical field_name on both platforms) ──────
  { key: "video_views", label: "Video Views", type: "number", align: "right", platforms: ["meta","tiktok","google_ads"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "video_p25",   label: "Video 25%",   type: "number", align: "right", platforms: ["meta","tiktok","google_ads"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "video_p50",   label: "Video 50%",   type: "number", align: "right", platforms: ["meta","tiktok","google_ads"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "video_p75",   label: "Video 75%",   type: "number", align: "right", platforms: ["meta","tiktok","google_ads"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "video_p100",  label: "Video 100%",  type: "number", align: "right", platforms: ["meta","tiktok","google_ads"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },

  // ── TikTok engagement ─────────────────────────────────────────────────
  { key: "likes",           label: "Likes",          type: "number",  align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:true  },
  { key: "comments",        label: "Comments",       type: "number",  align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "shares",          label: "Shares",         type: "number",  align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "follows",         label: "Follows",        type: "number",  align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "profile_visits",  label: "Profile Visits", type: "number",  align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "engagement_rate", label: "Engagement Rate",type: "percent", align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:true,  showInPeriodic:true, showInTable:true, tableDefaultVisible:true  },

  // ── TikTok conversion & results ───────────────────────────────────────
  { key: "result",          label: "Results",         type: "number",   align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "cost_per_result", label: "Cost/Result",     type: "currency", align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },

  // ── TikTok-specific video depth ───────────────────────────────────────
  { key: "video_2s_views",  label: "2s Views",       type: "number", align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "video_6s_views",  label: "6s Views",       type: "number", align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "avg_watch_time",  label: "Avg Watch Time", type: "number", align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },

  // ── TikTok website / app events ───────────────────────────────────────
  { key: "web_purchases",      label: "Web Purchases",  type: "number",   align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:true,  showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "web_purchase_value", label: "Web Purch. Val", type: "currency", align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "web_add_to_cart",    label: "Web Add to Cart",type: "number",   align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "app_installs",       label: "App Installs",   type: "number",   align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "install_cost",       label: "Install Cost",   type: "currency", align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },

  // ── Meta funnel events (from the synced `actions` array) ──────────────
  { key: "view_content",          label: "Content Views",  type: "number", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "purchase",              label: "Purchases",      type: "number", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "search",                label: "Searches",       type: "number", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "complete_registration", label: "Registrations",  type: "number", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },

  // ── Meta cost per funnel step (computed) ──────────────────────────────
  { key: "cost_per_view_content",       label: "Cost/Content View", type: "currency", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "cost_per_add_to_cart",        label: "Cost/Add to Cart",  type: "currency", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "cost_per_initiate_checkout",  label: "Cost/Checkout",     type: "currency", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "cost_per_purchase",           label: "Cost/Purchase",     type: "currency", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "cost_per_landing_page_view",  label: "Cost/LP View",      type: "currency", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "cost_per_lead",               label: "Cost/Lead",         type: "currency", align: "right", platforms: ["meta"], accountTypes: ["standard"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },

  // ── TikTok web funnel events ──────────────────────────────────────────
  { key: "web_checkout",          label: "Web Checkouts",     type: "number",   align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "cost_per_web_purchase", label: "Cost/Web Purchase", type: "currency", align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
  { key: "cost_per_web_add_to_cart", label: "Cost/Web ATC",   type: "currency", align: "right", platforms: ["tiktok"], accountTypes: ["standard","cpas"], showInKpi:false, showInPeriodic:true, showInTable:true, tableDefaultVisible:false },
];

/** Resolve a metric's display label / format type by key (single source of truth). */
const METRIC_BY_KEY = new Map(METRIC_REGISTRY.map((m) => [m.key, m]));
export const metricLabel = (key: string): string => METRIC_BY_KEY.get(key)?.label ?? key;
export const metricType = (key: string): MetricType => METRIC_BY_KEY.get(key)?.type ?? "number";

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

/**
 * Metrics safe to aggregate across platforms on the combined Dashboard — i.e.
 * scalar metrics that every platform populates identically in metrics_daily.
 * Deliberately excludes conversions/ROAS: TikTok stores conversions under a
 * different action field than Meta, so summing them cross-platform would
 * undercount. Surface those only on the per-platform views.
 */
const COMBINABLE_KEYS = new Set([
  "spend", "impressions", "reach", "frequency", "clicks", "ctr", "cpm", "cpc",
]);
export const getCombinableMetrics = () =>
  METRIC_REGISTRY.filter((m) => COMBINABLE_KEYS.has(m.key));

export const getKpiMetrics = (p: string | null | undefined, at: AccountType | null = null) =>
  getMetricsForPlatform(p, at).filter((m) => m.showInKpi);
export const getSelectableMetrics = (p: string | null | undefined, at: AccountType | null = null) =>
  getMetricsForPlatform(p, at).filter((m) => m.showInPeriodic);
export const getTableMetricCols = (p: string | null | undefined, at: AccountType | null = null) =>
  getMetricsForPlatform(p, at).filter((m) => m.showInTable);
