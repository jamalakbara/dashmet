"use client";

import { useQueryState } from "nuqs";
import { useQuery } from "@tanstack/react-query";
import { accountsApi } from "@/lib/api/accounts";
import { queryKeys } from "@/lib/query-keys";
import { usePlatform } from "@/hooks/use-platform";

import type { AccountType } from "@/types/enums";

export interface Account {
  id: string;
  name: string;
  currency: string;
  platform: string;
  account_type: AccountType;
}

/** Shared accounts query — single source for all account-aware hooks. */
export function useAccountsList(): Account[] {
  const { data } = useQuery({
    queryKey: queryKeys.accounts(),
    queryFn: async () => (await accountsApi.list()).data.data as Account[],
    enabled: typeof window !== "undefined",
  });
  return data ?? [];
}

/** Accounts filtered to a given platform (all accounts when platform is null). */
export function usePlatformAccounts(platform: string | null): Account[] {
  const accounts = useAccountsList();
  if (!platform) return accounts;
  return accounts.filter((a) => a.platform === platform);
}

export function useAccountId(): string | null {
  return useSelectedAccount().accountId;
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
  const all = useAccountsList();

  // Scope to the route's platform so a stale account_id from another platform
  // falls back to the first account of the active platform.
  const scoped = routePlatform ? all.filter((a) => a.platform === routePlatform) : all;
  const fromUrl = scoped.find((a) => a.id === accountId) ?? null;
  const account = fromUrl ?? scoped[0] ?? null;

  return {
    accountId: account?.id ?? null,
    account,
    platform: account?.platform ?? routePlatform ?? null,
    currency: account?.currency ?? "USD",
    accountType: account?.account_type ?? null,
  };
}
