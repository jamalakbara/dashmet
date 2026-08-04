"use client";

import { useQuery } from "@tanstack/react-query";
import { authApi } from "@/lib/api/auth";
import { queryKeys } from "@/lib/query-keys";

export interface Me {
  id: string;
  name: string;
  email: string;
  org: { id: string; name: string; slug: string; role: string };
}

/**
 * Current user (`GET /auth/me`), parsed to `Me`. This is the single canonical
 * consumer of the `queryKeys.me()` cache entry — every component reads the same
 * shape through here. Do NOT query `queryKeys.me()` directly with a different
 * return shape: TanStack keys one cache entry per key, so mixing "full axios
 * response" and "parsed body" shapes makes the value depend on mount order
 * (which is how the navbar user info silently blanked to "—").
 */
export function useMe() {
  return useQuery({
    queryKey: queryKeys.me(),
    queryFn: async () => (await authApi.me()).data.data as Me,
    staleTime: 60 * 60 * 1000,
  });
}
