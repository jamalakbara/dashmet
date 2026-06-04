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
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { accountsApi } from "@/lib/api/accounts";
import { queryKeys } from "@/lib/query-keys";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { usePlatform } from "@/hooks/use-platform";

interface Account {
  id: string;
  name: string;
  platform: string;
  currency: string;
}

export function AccountSwitcher() {
  const platform = usePlatform();
  const [accountId, setAccountId] = useQueryState("account_id");
  const [accountsParam, setAccountsParam] = useQueryState("accounts");
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
  const scoped = platform ? accounts.filter((a) => a.platform === platform) : accounts;
  const scopedIds = scoped.map((a) => a.id).join(",");

  // Poll briefly for accounts right after connecting (none yet).
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

  // On a platform route, keep account_id valid for the active platform.
  useEffect(() => {
    if (!platform || scoped.length === 0) return;
    if (!accountId || !scoped.some((a) => a.id === accountId)) {
      setAccountId(scoped[0].id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [platform, accountId, scopedIds]);

  if (isLoading) {
    return <div className="h-8 w-48 animate-pulse rounded-lg bg-muted" />;
  }

  if (!accounts.length) {
    return (
      <span className="text-sm text-muted-foreground">No accounts connected</span>
    );
  }

  // ── Combined dashboard: multi-account picker ──
  if (!platform) {
    const allIds = accounts.map((a) => a.id);
    const selected =
      accountsParam && accountsParam.length > 0
        ? new Set(accountsParam.split(",").filter(Boolean))
        : new Set(allIds); // default: all accounts
    const allSelected = selected.size === allIds.length;

    function setSelected(next: Set<string>) {
      const ids = allIds.filter((id) => next.has(id));
      // Persist explicit list; clear param when it equals "all" to keep URLs clean.
      setAccountsParam(ids.length === allIds.length ? null : ids.join(","));
    }

    function toggle(id: string) {
      const next = new Set(selected);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      setSelected(next);
    }

    const label = allSelected
      ? `All accounts (${allIds.length})`
      : `${selected.size} of ${allIds.length} accounts`;

    return (
      <Popover>
        <PopoverTrigger className="flex h-8 w-56 items-center gap-2 rounded-lg border border-input bg-transparent px-2.5 text-sm hover:bg-accent">
          <ChevronsUpDown className="size-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate">{label}</span>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-64 p-2">
          <div className="flex items-center justify-between px-1 pb-2">
            <span className="text-xs text-muted-foreground">Combine accounts</span>
            <button
              className="text-xs text-primary hover:underline"
              onClick={() => setAccountsParam(allSelected ? "" : null)}
            >
              {allSelected ? "Clear" : "Select all"}
            </button>
          </div>
          <div className="max-h-72 space-y-1 overflow-y-auto">
            {accounts.map((acc) => (
              <label
                key={acc.id}
                className="flex cursor-pointer items-center gap-2 rounded px-1 py-1.5 text-sm hover:bg-accent"
              >
                <Checkbox
                  checked={selected.has(acc.id)}
                  onCheckedChange={() => toggle(acc.id)}
                />
                <PlatformBadge platform={acc.platform} size="sm" />
                <span className="truncate">{acc.name}</span>
                <span className="ml-auto text-xs text-muted-foreground">{acc.currency}</span>
              </label>
            ))}
          </div>
        </PopoverContent>
      </Popover>
    );
  }

  // ── Platform route: single account, scoped to the platform ──
  if (!scoped.length) {
    return (
      <span className="text-sm text-muted-foreground">
        No {platform} accounts connected
      </span>
    );
  }

  const effectiveId = scoped.some((a) => a.id === accountId) ? accountId! : scoped[0].id;
  const selectedAccount = scoped.find((a) => a.id === effectiveId) ?? null;

  return (
    <Select value={effectiveId} onValueChange={(val) => setAccountId(val)}>
      <SelectTrigger className="w-48">
        <ChevronsUpDown className="size-3.5 text-muted-foreground" />
        {selectedAccount && (
          <PlatformBadge platform={selectedAccount.platform} size="sm" />
        )}
        <span className="truncate text-sm">
          {selectedAccount?.name ?? "Select account"}
        </span>
      </SelectTrigger>
      <SelectContent align="start">
        {scoped.map((acc) => (
          <SelectItem key={acc.id} value={acc.id}>
            <div className="flex items-center gap-2">
              <PlatformBadge platform={acc.platform} size="sm" />
              <span className="truncate">{acc.name}</span>
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
