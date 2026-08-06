export type DateRange =
  | { date_preset: string }
  | { date_start: string; date_end: string };

export type TableFilters = {
  status?: string;
  search?: string;
  /** Raw platform objective filter (e.g. TikTok "PRODUCT_SALES", GMV Max view). */
  platform_objective?: string;
  sort_by?: string;
  sort_order?: string;
  page?: number;
  campaign_id?: string;
  adgroup_id?: string;
  compare_previous?: boolean;
};

// Shared Overview-page campaign filter (status + campaign name). Kept out of
// DateRange so it can vary independently and stay in the query cache key.
export type OverviewFilter = {
  status?: string;
  search?: string;
};

export const queryKeys = {
  me: () => ["me"] as const,
  accounts: () => ["accounts"] as const,
  accountsSearch: (platform: string | null, search: string) =>
    ["accounts", "search", platform, search] as const,
  accountsList: (platform: string | null, search: string, page: number, perPage: number) =>
    ["accounts", "list", platform, search, page, perPage] as const,
  accountsCount: () => ["accounts", "count"] as const,
  account: (id: string) => ["account", id] as const,
  syncStatus: (accountId: string) => ["sync-status", accountId] as const,
  overview: (accountId: string, dateRange: DateRange, filter: OverviewFilter = {}) =>
    ["overview", accountId, dateRange, filter] as const,
  timeseries: (
    accountId: string,
    dateRange: DateRange,
    level: string,
    metrics: string[],
    timeIncrement: string,
    comparePrev: boolean,
    filter: OverviewFilter = {}
  ) => ["timeseries", accountId, dateRange, level, metrics, timeIncrement, comparePrev, filter] as const,
  table: (accountId: string, dateRange: DateRange, level: string, filters: TableFilters) =>
    ["table", accountId, dateRange, level, filters] as const,
  breakdown: (accountId: string, dateRange: DateRange, type: string) =>
    ["breakdown", accountId, dateRange, type] as const,
  engagement: (accountId: string, dateRange: DateRange) =>
    ["engagement", accountId, dateRange] as const,
  creative: (adId: string) => ["creative", adId] as const,
  combined: (accountIds: string[], dateRange: DateRange) =>
    ["combined", accountIds, dateRange] as const,
  combinedTimeseries: (accountIds: string[], dateRange: DateRange, timeIncrement: string) =>
    ["combined-timeseries", accountIds, dateRange, timeIncrement] as const,
};
