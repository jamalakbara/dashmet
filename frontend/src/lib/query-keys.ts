export type DateRange =
  | { date_preset: string }
  | { date_start: string; date_end: string };

export type TableFilters = {
  status?: string;
  search?: string;
  sort_by?: string;
  sort_order?: string;
  page?: number;
  campaign_id?: string;
  adgroup_id?: string;
};

export const queryKeys = {
  me: () => ["me"] as const,
  accounts: () => ["accounts"] as const,
  account: (id: string) => ["account", id] as const,
  syncStatus: (accountId: string) => ["sync-status", accountId] as const,
  overview: (accountId: string, dateRange: DateRange) =>
    ["overview", accountId, dateRange] as const,
  timeseries: (
    accountId: string,
    dateRange: DateRange,
    level: string,
    metrics: string[],
    timeIncrement: string
  ) => ["timeseries", accountId, dateRange, level, metrics, timeIncrement] as const,
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
