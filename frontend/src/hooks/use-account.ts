"use client";

import { useEffect, useState } from "react";
import { useQueryState } from "nuqs";
import { useQuery, useQueries } from "@tanstack/react-query";
import { accountsApi } from "@/lib/api/accounts";
import { queryKeys } from "@/lib/query-keys";
import { SUPPORTED_PLATFORMS } from "@/lib/constants";
import { usePlatform } from "@/hooks/use-platform";
import { useUIStore, type AccountSnapshot } from "@/stores/ui-store";

import type { AccountType } from "@/types/enums";

export interface Account {
  id: string;
  name: string;
  currency: string;
  platform: string;
  account_type: AccountType;
  external_id?: string;
  business_name?: string | null;
}

const PICKER_PAGE_SIZE = 50;

/** Debounce a fast-changing value (e.g. a search input). */
export function useDebounced<T>(value: T, ms = 250): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

/**
 * Server-side searched account list for the picker, scoped to a platform
 * (null = all platforms, for the combined dashboard). The whole list is never
 * loaded at once — the backend filters and caps the page.
 */
export function useAccountSearch(
  platform: string | null,
  search: string,
  enabled = true,
) {
  const debounced = useDebounced(search.trim(), 250);
  const { data, isLoading, isFetching } = useQuery({
    queryKey: queryKeys.accountsSearch(platform, debounced),
    queryFn: async () =>
      (
        await accountsApi.list({
          platform: platform ?? undefined,
          search: debounced || undefined,
          per_page: PICKER_PAGE_SIZE,
        })
      ).data.data as Account[],
    enabled: enabled && typeof window !== "undefined",
    placeholderData: (prev) => prev, // keep prior results visible while typing
  });
  return { accounts: data ?? [], isLoading, isFetching };
}

/**
 * Combined-dashboard picker: fans out one capped query per supported platform so
 * every connected platform is represented (a single capped page would otherwise
 * be dominated by the platform with the most accounts). Reuses the same key +
 * fetcher as useAccountSearch; empty (unconnected) platforms drop out naturally.
 */
export function useGroupedAccountSearch(search: string, enabled = true) {
  const debounced = useDebounced(search.trim(), 250);
  const queries = useQueries({
    queries: SUPPORTED_PLATFORMS.map((platform) => ({
      queryKey: queryKeys.accountsSearch(platform, debounced),
      queryFn: async () =>
        (
          await accountsApi.list({
            platform,
            search: debounced || undefined,
            per_page: PICKER_PAGE_SIZE,
          })
        ).data.data as Account[],
      enabled: enabled && typeof window !== "undefined",
      placeholderData: (prev: Account[] | undefined) => prev,
    })),
  });
  // flatMap preserves SUPPORTED_PLATFORMS order → Meta group before TikTok, etc.
  const accounts = queries.flatMap((q) => q.data ?? []);
  const isFetching = queries.some((q) => q.isFetching);
  return { accounts, isFetching };
}

/** Total connected-account count — for empty states and on-connect polling. */
export function useAccountsCount(polling = false): number | null {
  const { data } = useQuery({
    queryKey: queryKeys.accountsCount(),
    queryFn: async () => {
      const res = await accountsApi.list({ per_page: 1 });
      return (res.data.pagination?.total ?? 0) as number;
    },
    enabled: typeof window !== "undefined",
    refetchInterval: polling ? 3000 : false,
  });
  return data ?? null;
}

export function useAccountId(): string | null {
  return useSelectedAccount().accountId;
}

function snapshotToAccount(s: AccountSnapshot): Account {
  return {
    id: s.id,
    name: s.name,
    platform: s.platform,
    currency: s.currency,
    external_id: s.external_id,
    account_type: (s.account_type as AccountType) ?? "standard",
  };
}

export function useSelectedAccount(): {
  accountId: string | null;
  account: Account | null;
  platform: string | null;
  currency: string;
  accountType: AccountType | null;
} {
  const [accountId] = useQueryState("account_id");
  const routePlatform = usePlatform();
  const snapshots = useUIStore((s) => s.accountSnapshots);
  const pinned = useUIStore((s) => s.pinnedAccountIds);
  const recent = useUIStore((s) => s.recentAccountIds);

  // First page for the active platform — seeds the default selection and acts
  // as a resolution source for a freshly-picked account_id.
  const { accounts: firstPage } = useAccountSearch(routePlatform, "");

  // Resolve the selected id by a single fetch only when it's neither in the
  // snapshot store nor on the first page (e.g. a deep-linked account_id).
  const knownLocally = !!accountId && (!!snapshots[accountId] || firstPage.some((a) => a.id === accountId));
  const { data: fetched } = useQuery({
    queryKey: queryKeys.account(accountId ?? ""),
    queryFn: async () => (await accountsApi.get(accountId!)).data.data as Account,
    enabled: typeof window !== "undefined" && !!accountId && !knownLocally,
  });

  const scopeOk = (a: { platform: string } | null | undefined) =>
    !routePlatform || a?.platform === routePlatform;

  // 1) Explicit account_id → first page → snapshot → single fetch.
  let account: Account | null = null;
  if (accountId) {
    const snap = snapshots[accountId];
    account =
      firstPage.find((a) => a.id === accountId) ??
      (snap ? snapshotToAccount(snap) : null) ??
      (fetched && fetched.id === accountId ? fetched : null);
  }

  // 2) Missing / wrong-platform selection → first remembered account for the
  //    platform, else the first row of the page.
  if (!account || !scopeOk(account)) {
    const remembered = [...pinned, ...recent]
      .map((id) => snapshots[id])
      .find((s) => s && scopeOk(s));
    account = (remembered ? snapshotToAccount(remembered) : null) ?? firstPage[0] ?? null;
  }

  return {
    accountId: account?.id ?? null,
    account,
    platform: account?.platform ?? routePlatform ?? null,
    currency: account?.currency ?? "USD",
    accountType: account?.account_type ?? null,
  };
}
