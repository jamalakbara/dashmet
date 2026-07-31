import apiClient from "./client";

export type InsightParams = {
  account_id: string;
  date_preset?: string;
  date_start?: string;
  date_end?: string;
};

export type TimeseriesParams = InsightParams & {
  level?: string;
  metrics?: string;
  time_increment?: string;
  compare_previous?: boolean;
  campaign_id?: string;
  adgroup_id?: string;
};

export type TableParams = InsightParams & {
  level?: string;
  status?: string;
  search?: string;
  sort_by?: string;
  sort_order?: string;
  page?: number;
  per_page?: number;
  campaign_id?: string;
  adgroup_id?: string;
};

export type BreakdownParams = InsightParams & {
  breakdown_type: string;
  level?: string;
  campaign_id?: string;
  adgroup_id?: string;
};

export type CombinedParams = {
  account_ids: string; // comma-separated account ids
  date_preset?: string;
  date_start?: string;
  date_end?: string;
};

export const insightsApi = {
  overview: (params: InsightParams) =>
    apiClient.get("/insights/overview", { params }),
  timeseries: (params: TimeseriesParams) =>
    apiClient.get("/insights/timeseries", { params }),
  table: (params: TableParams) =>
    apiClient.get("/insights/table", { params }),
  breakdown: (params: BreakdownParams) =>
    apiClient.get("/insights/breakdown", { params }),
  engagement: (params: InsightParams) =>
    apiClient.get("/insights/engagement", { params }),
  creative: (adId: string) => apiClient.get(`/ads/${adId}/creative`),
  combined: (params: CombinedParams) =>
    apiClient.get("/insights/combined", { params }),
  combinedTimeseries: (params: CombinedParams & { time_increment?: string }) =>
    apiClient.get("/insights/combined-timeseries", { params }),
};
