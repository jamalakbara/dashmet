"use client";

import { useSearchParams } from "next/navigation";
import { useCallback } from "react";

const SHARED_KEYS = ["account_id", "date_preset", "date_start", "date_end"] as const;

/**
 * Returns a `withQuery(href)` helper that re-appends the shared dashboard filter
 * params (account_id, date range) so they survive sidebar / tab navigation.
 * account_id is reconciled against the target platform by useSelectedAccount.
 */
export function useSharedFilterQuery(): (href: string) => string {
  const searchParams = useSearchParams();
  return useCallback(
    (href: string) => {
      const params = new URLSearchParams();
      SHARED_KEYS.forEach((key) => {
        const v = searchParams.get(key);
        if (v) params.set(key, v);
      });
      const q = params.toString();
      if (!q) return href;
      const sep = href.includes("?") ? "&" : "?";
      return `${href}${sep}${q}`;
    },
    [searchParams]
  );
}
