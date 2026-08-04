import apiClient from "./client";

export type InsightParams = {
  account_id: string;
  date_preset?: string;
  date_start?: string;
  date_end?: string;
};

// Overview cards + funnel share the campaign filter (status + campaign name).
export type OverviewParams = InsightParams & {
  status?: string;
  search?: string;
};

// PPTX export takes the overview params plus an optional flag to have the deck's
// insight boxes auto-filled by the AI narrative service (gated: token spend).
export type ExportOverviewParams = OverviewParams & {
  include_ai_summary?: boolean;
};

/**
 * On-demand AI structured summary of the single-account overview. Unlike the
 * other insights GETs, this endpoint returns the object at the TOP LEVEL (not
 * wrapped in a `{ data }` envelope). Carries the period/freshness envelope so
 * the summary stays anchored to the numbers shown on screen (P-1).
 *
 * The narrative is broken into four labeled fields (all required): `headline`
 * (the lead), `driver` (likely cause), `watch` (a risk to monitor), and
 * `next_step` (the recommended action).
 */
export interface OverviewSummary {
  headline: string;
  driver: string;
  watch: string;
  next_step: string;
  period: {
    date_start: string;
    date_stop: string;
    preset: string | null;
  };
  model: string;
  generated_at: string;
  /** ISO datetime the diagnosis was generated against (freshness anchor, P-1). */
  data_as_of: string | null;
  /** True when this diagnosis was served from the cache (no token spend). */
  cached: boolean;
}

export type TimeseriesParams = InsightParams & {
  level?: string;
  metrics?: string;
  time_increment?: string;
  compare_previous?: boolean;
  campaign_id?: string;
  adgroup_id?: string;
  status?: string;
  search?: string;
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
  /** When true, each row also carries `metrics_previous` (prior period). */
  compare_previous?: boolean;
};

/**
 * Prior-period metric values for a table/ad row, present on each row only when
 * the request was made with `compare_previous: true`. Same keys as `metrics`.
 */
export type MetricsPrevious = Record<string, number | null>;

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

/** Extract the download filename from a Content-Disposition header, preferring
 * the RFC 5987 `filename*` (UTF-8) form and falling back to plain `filename`. */
function parseContentDispositionFilename(cd?: string): string | null {
  if (!cd) return null;
  const star = /filename\*=\s*(?:UTF-8'')?([^;]+)/i.exec(cd);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ""));
    } catch {
      /* fall through to plain filename */
    }
  }
  const plain = /filename=\s*"?([^";]+)"?/i.exec(cd);
  return plain?.[1]?.trim() ?? null;
}

export const insightsApi = {
  overview: (params: OverviewParams) =>
    apiClient.get("/insights/overview", { params }),
  /**
   * Server-rendered PPTX export of the single-account overview. Takes the same
   * params as `overview` and returns the raw .pptx bytes as a Blob (the endpoint
   * also sets a Content-Disposition attachment filename).
   */
  exportOverviewPptx: async (
    params: ExportOverviewParams,
  ): Promise<{ blob: Blob; filename: string }> => {
    const res = await apiClient.get<Blob>("/insights/overview/export.pptx", {
      params,
      responseType: "blob",
    });
    const cd = res.headers["content-disposition"] as string | undefined;
    return {
      blob: res.data,
      filename: parseContentDispositionFilename(cd) ?? "Monthly Report.pptx",
    };
  },
  /**
   * On-demand AI narrative summary of the single-account overview. POST (not
   * GET) so the token-spending intent is explicit and it stays off the cacheable
   * read path. Response is returned at the top level — NOT `{ data }`-wrapped —
   * so we hand back `res.data` directly. Any AI failure surfaces as a 502 whose
   * `detail` the caller shows verbatim (P-4: no fake/empty summary).
   *
   * Without `force` the backend returns a cached diagnosis when one exists (no
   * token spend); `force: true` regenerates and overwrites the cache.
   */
  generateSummary: async (
    params: OverviewParams & { force?: boolean },
  ): Promise<OverviewSummary> => {
    const res = await apiClient.post<OverviewSummary>(
      "/insights/overview/summary",
      null,
      { params },
    );
    return res.data;
  },
  /**
   * Cache-only peek at the overview summary — NEVER generates or spends tokens.
   * Safe to auto-run on mount to hydrate an existing summary instantly. Returns
   * the cached `OverviewSummary` (`cached: true`) on a hit, or `null` on a miss
   * (the backend replies HTTP 204 No Content, which axios surfaces with an empty
   * body — we map that to `null` rather than an error).
   */
  peekSummary: async (
    params: OverviewParams,
  ): Promise<OverviewSummary | null> => {
    const res = await apiClient.get<OverviewSummary | "">(
      "/insights/overview/summary/peek",
      { params },
    );
    if (res.status === 204 || !res.data) return null;
    return res.data;
  },
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
