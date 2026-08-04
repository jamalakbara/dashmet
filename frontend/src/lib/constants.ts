import type { DatePreset, AccountType } from "@/types/enums";

/** Every platform the combined picker fans out over (grouped by these, in order).
 *  Unconnected platforms return no accounts and their group is dropped. */
export const SUPPORTED_PLATFORMS = ["meta", "tiktok", "google_ads", "google_analytics"] as const;

export const DATE_PRESETS: { label: string; value: DatePreset }[] = [
  { label: "Today",       value: "today" },
  { label: "Yesterday",   value: "yesterday" },
  { label: "Last 7 days", value: "last_7d" },
  { label: "Last 14 days",value: "last_14d" },
  { label: "Last 30 days",value: "last_30d" },
  { label: "Last 90 days",value: "last_90d" },
  { label: "This month",  value: "this_month" },
  { label: "Last month",  value: "last_month" },
];

export const DEFAULT_DATE_PRESET: DatePreset = "last_30d";

export const METRIC_LABELS: Record<string, string> = {
  spend:               "Spend",
  impressions:         "Impressions",
  reach:               "Reach",
  frequency:           "Frequency",
  clicks:              "Clicks",
  inline_link_clicks:  "Link Clicks",
  ctr:                 "CTR",
  cpm:                 "CPM",
  cpc:                 "CPC",
  cpp:                 "CPP",
  conversions:         "Conversions",
  conversion_value:    "Conv. Value",
  roas:                     "ROAS",
  cpa:                      "CPA",
  outbound_clicks:          "Outbound Clicks",
  outbound_clicks_ctr:      "Outbound CTR",
  cost_per_outbound_click:  "Cost/Outbound Click",
};

export const METRIC_TYPES: Record<string, "currency" | "percent" | "number" | "roas"> = {
  spend:            "currency",
  impressions:      "number",
  reach:            "number",
  frequency:        "number",
  clicks:           "number",
  inline_link_clicks: "number",
  ctr:              "percent",
  cpm:              "currency",
  cpc:              "currency",
  cpp:              "currency",
  conversions:      "number",
  conversion_value: "currency",
  roas:                    "roas",
  cpa:                     "currency",
  outbound_clicks:         "number",
  outbound_clicks_ctr:     "percent",
  cost_per_outbound_click: "currency",
};

/** Warm-anchored, multi-hue series palette (Bright Modern SaaS). Reads in both
 *  light and dark. Led by the coral accent. Shared chart styling lives in
 *  lib/chart-theme.ts — import series colors from there or here. */
export const CHART_COLORS = [
  "#F26A4B", // coral (accent)
  "#F5A623", // amber
  "#4FB477", // green
  "#5B8DEF", // blue
  "#9B6DFF", // violet
  "#22B8CF", // cyan
  "#E8619D", // pink
  "#8CC63F", // lime
  "#E4572E", // burnt orange
  "#3AAFA9", // teal
];

export const DEFAULT_METRICS = ["spend", "clicks"];

export const KPI_METRICS = [
  "spend",
  "impressions",
  "reach",
  "clicks",
  "ctr",
  "cpm",
  "conversions",
  "roas",
] as const;

export interface PlatformTab {
  slug: string;
  label: string;
}

/**
 * Single source of truth for the per-platform view tabs. Consumed by the
 * PlatformTabs bar and by the sidebar (first slug = the platform's landing tab).
 */
export const PLATFORM_TABS: Record<string, PlatformTab[]> = {
  meta: [
    { slug: "overview", label: "Overview" },
    { slug: "table",    label: "Table" },
    { slug: "ads",      label: "Ads" },
  ],
  tiktok: [
    { slug: "overview",   label: "Overview" },
    { slug: "table",      label: "Table" },
    { slug: "ads",        label: "Ads" },
    { slug: "engagement", label: "Engagement" },
  ],
  google_ads: [
    { slug: "overview", label: "Overview" },
    { slug: "table",    label: "Table" },
    { slug: "ads",      label: "Ads" },
  ],
};

export interface FunnelStep {
  key: string;
  label: string;
}

/**
 * Ordered funnel steps per platform for the Funnel view. Each key must exist in
 * the overview summary (METRIC_REGISTRY). Steps with null/0 values are hidden at
 * render time, so accounts without a Pixel collapse to the steps they do have.
 *
 * Meta is account-type-aware and is resolved via `getFunnelSteps` (standard vs
 * cpas use different, strictly-separated conversion keys) — never read
 * `FUNNEL_STEPS.meta` directly. tiktok / google_ads are platform-only.
 */
export const FUNNEL_STEPS: Record<string, FunnelStep[]> = {
  tiktok: [
    { key: "impressions",      label: "Impressions" },
    { key: "clicks",           label: "Clicks" },
    { key: "video_views",      label: "Video Views" },
    { key: "web_add_to_cart",  label: "Web Add to Cart" },
    { key: "web_checkout",     label: "Web Checkout" },
    { key: "web_purchases",    label: "Web Purchases" },
    { key: "conversions",      label: "Conversions" },
  ],
  // Google has no ecommerce-pixel funnel — show the search funnel.
  google_ads: [
    { key: "impressions", label: "Impressions" },
    { key: "clicks",      label: "Clicks" },
    { key: "conversions", label: "Conversions" },
  ],
};

/** Meta funnel steps keyed by account type — strictly separated so a standard
 *  account never renders `*_shared` steps and a cpas account never renders the
 *  standard pixel steps. */
export const META_FUNNEL_STEPS: Record<AccountType, FunnelStep[]> = {
  standard: [
    { key: "landing_page_views", label: "Landing Page View" },
    { key: "add_to_cart",        label: "Add to Cart" },
    { key: "initiate_checkout",  label: "Initiate Checkout" },
    { key: "purchase",           label: "Purchase" },
  ],
  cpas: [
    { key: "content_view_shared", label: "Content View Shared Item" },
    { key: "add_to_cart_shared",  label: "Add to Cart Shared Item" },
    { key: "purchase_shared",     label: "Purchase Shared Item" },
  ],
};

/**
 * Resolve the ordered funnel steps for a platform + account type. Meta branches
 * on account type (standard vs cpas shared-item); tiktok / google_ads ignore it.
 * Falls back to Meta standard when platform is unknown.
 */
export function getFunnelSteps(
  platform: string | null | undefined,
  accountType: AccountType | null,
): FunnelStep[] {
  if (!platform || platform === "meta") {
    return META_FUNNEL_STEPS[accountType ?? "standard"];
  }
  return FUNNEL_STEPS[platform] ?? META_FUNNEL_STEPS.standard;
}
