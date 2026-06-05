import type { DatePreset } from "@/types/enums";

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

export const CHART_COLORS = [
  "#2563eb",
  "#16a34a",
  "#dc2626",
  "#d97706",
  "#7c3aed",
  "#0891b2",
  "#be185d",
  "#65a30d",
  "#c2410c",
  "#1d4ed8",
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
    { slug: "periodic", label: "Periodic" },
    { slug: "table",    label: "Table" },
    { slug: "ads",      label: "Ads" },
  ],
  tiktok: [
    { slug: "overview",   label: "Overview" },
    { slug: "periodic",   label: "Periodic" },
    { slug: "table",      label: "Table" },
    { slug: "ads",        label: "Ads" },
    { slug: "engagement", label: "Engagement" },
  ],
};
