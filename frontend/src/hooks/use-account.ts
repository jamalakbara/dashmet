"use client";

import { useQueryState } from "nuqs";
import { useQuery } from "@tanstack/react-query";
import { accountsApi } from "@/lib/api/accounts";
import { queryKeys } from "@/lib/query-keys";

import type { AccountType } from "@/types/enums";

interface Account { id: string; name: string; currency: string; platform: string; account_type: AccountType; }

export function useAccountId(): string | null {
  const [accountId] = useQueryState("account_id");
  const { data } = useQuery({
    queryKey: queryKeys.accounts(),
    queryFn: async () => (await accountsApi.list()).data.data as Account[],
    enabled: typeof window !== "undefined",
  });
  return accountId ?? data?.[0]?.id ?? null;
}

export function useSelectedAccount(): {
  accountId: string | null;
  account: Account | null;
  platform: string | null;
  currency: string;
  accountType: AccountType | null;
} {
  const [accountId] = useQueryState("account_id");
  const { data } = useQuery({
    queryKey: queryKeys.accounts(),
    queryFn: async () => (await accountsApi.list()).data.data as Account[],
    enabled: typeof window !== "undefined",
  });
  const accounts = data ?? [];
  const effectiveId = accountId ?? accounts[0]?.id ?? null;
  const account = accounts.find((a) => a.id === effectiveId) ?? null;
  return {
    accountId: effectiveId,
    account,
    platform: account?.platform ?? null,
    currency: account?.currency ?? "USD",
    accountType: account?.account_type ?? null,
  };
}
