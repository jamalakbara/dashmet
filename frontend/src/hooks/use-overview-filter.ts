"use client";

import { useQueryState } from "nuqs";
import type { OverviewFilter } from "@/lib/query-keys";

/**
 * Reads the shared Overview-page campaign filter (status + campaign name) from
 * the URL. Written by the Control-strip Filter popover; consumed by the Overview
 * cards, funnel, and trends so they all scope to the same campaign set.
 *
 * "all" status collapses to undefined so it's omitted from the request.
 */
export function useOverviewFilter(): OverviewFilter {
  const [status] = useQueryState("status", { defaultValue: "all" });
  const [search] = useQueryState("search");
  return {
    status: status && status !== "all" ? status : undefined,
    search: search || undefined,
  };
}
