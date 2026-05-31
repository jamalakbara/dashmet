"use client";

import { useQueryState } from "nuqs";
import { useQuery } from "@tanstack/react-query";
import { accountsApi } from "@/lib/api/accounts";
import { queryKeys } from "@/lib/query-keys";

interface Account { id: string; name: string; currency: string; platform: string; }

export function useAccountId(): string | null {
  const [accountId] = useQueryState("account_id");
  const { data } = useQuery({
    queryKey: queryKeys.accounts(),
    queryFn: async () => (await accountsApi.list()).data.data as Account[],
    enabled: typeof window !== "undefined",
  });
  return accountId ?? data?.[0]?.id ?? null;
}
