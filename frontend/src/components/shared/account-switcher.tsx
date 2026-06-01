"use client";

import { useQuery } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import { useEffect, useRef, useState } from "react";
import { ChevronsUpDown } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { accountsApi } from "@/lib/api/accounts";
import { queryKeys } from "@/lib/query-keys";

interface Account {
  id: string;
  name: string;
  platform: string;
  currency: string;
}

export function AccountSwitcher() {
  const [accountId, setAccountId] = useQueryState("account_id");
  const [polling, setPolling] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.accounts(),
    queryFn: async () => {
      const res = await accountsApi.list();
      return res.data.data as Account[];
    },
    refetchInterval: polling ? 3000 : false,
  });

  const accounts = data ?? [];

  useEffect(() => {
    if (data !== undefined && accounts.length === 0 && !polling) {
      setPolling(true);
      pollTimer.current = setTimeout(() => setPolling(false), 60_000);
    }
    if (accounts.length > 0 && polling) {
      setPolling(false);
      if (pollTimer.current) clearTimeout(pollTimer.current);
    }
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [data, accounts.length, polling]);

  const effectiveId = accountId ?? accounts[0]?.id ?? null;
  const selectedAccount = accounts.find(a => a.id === effectiveId) ?? null;

  if (isLoading) {
    return <div className="h-8 w-48 animate-pulse rounded-lg bg-muted" />;
  }

  if (!accounts.length) {
    return (
      <span className="text-sm text-muted-foreground">No accounts connected</span>
    );
  }

  return (
    <Select
      value={effectiveId ?? undefined}
      onValueChange={(val) => setAccountId(val)}
    >
      <SelectTrigger className="w-48">
        <ChevronsUpDown className="size-3.5 text-muted-foreground" />
        <span className="truncate text-sm">
          {selectedAccount?.name ?? "Select account"}
        </span>
      </SelectTrigger>
      <SelectContent align="start">
        {accounts.map((acc) => (
          <SelectItem key={acc.id} value={acc.id}>
            {acc.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
