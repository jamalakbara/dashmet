"use client";

import { useEffect, useState } from "react";
import { useQueryState } from "nuqs";
import { ChevronsUpDown } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { AccountCommandList } from "@/components/shared/account-command-list";
import { useAccountSearch, useAccountsCount, useSelectedAccount } from "@/hooks/use-account";
import { usePlatform } from "@/hooks/use-platform";
import { cn } from "@/lib/utils";

const TRIGGER_CLASS =
  "flex h-8 w-56 items-center gap-2 rounded-lg border border-input bg-transparent px-2.5 text-sm hover:bg-accent";

/** Polls the account count briefly after connecting (when none exist yet). */
function useConnectPolling(): number | null {
  const [polling, setPolling] = useState(false);
  const count = useAccountsCount(polling);
  useEffect(() => {
    if (count === 0 && !polling) {
      setPolling(true);
      const t = setTimeout(() => setPolling(false), 60_000);
      return () => clearTimeout(t);
    }
    if (count != null && count > 0 && polling) setPolling(false);
  }, [count, polling]);
  return count;
}

export function AccountSwitcher() {
  const platform = usePlatform();
  return platform ? <SingleAccountSwitcher platform={platform} /> : <MultiAccountSwitcher />;
}

// ── Platform route: single account, scoped to the platform ──
function SingleAccountSwitcher({ platform }: { platform: string }) {
  const [open, setOpen] = useState(false);
  const [, setAccountId] = useQueryState("account_id");
  const { accountId: resolvedId, account } = useSelectedAccount();
  const { accounts: firstPage, isLoading } = useAccountSearch(platform, "");
  const count = useConnectPolling();

  // Keep the URL's account_id canonical (resolved default / platform-scoped).
  useEffect(() => {
    if (resolvedId) setAccountId(resolvedId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedId]);

  if (count === null && isLoading) {
    return <div className="h-8 w-56 animate-pulse rounded-lg bg-muted" />;
  }
  if (firstPage.length === 0 && !isLoading) {
    return (
      <span className="text-sm text-muted-foreground">No {platform} accounts connected</span>
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger className={TRIGGER_CLASS}>
        <ChevronsUpDown className="size-3.5 shrink-0 text-muted-foreground" />
        {account && <PlatformBadge platform={account.platform} size="sm" />}
        <span className="truncate text-sm">{account?.name ?? "Select account"}</span>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 p-0">
        <AccountCommandList
          platform={platform}
          mode="single"
          selectedId={resolvedId}
          onSelect={(a) => {
            setAccountId(a.id);
            setOpen(false);
          }}
        />
      </PopoverContent>
    </Popover>
  );
}

// ── Combined dashboard: multi-account picker (null = all) ──
function MultiAccountSwitcher() {
  const [accountsParam, setAccountsParam] = useQueryState("accounts");
  const count = useConnectPolling();

  if (count === 0) {
    return <span className="text-sm text-muted-foreground">No accounts connected</span>;
  }

  const isAll = accountsParam == null;
  const isNone = accountsParam === "";
  const explicit = !isAll && !isNone ? accountsParam!.split(",").filter(Boolean) : [];
  const selectedIds = new Set(explicit);

  const label = isAll
    ? "All accounts"
    : isNone
    ? "No accounts"
    : `${explicit.length} selected`;

  function toggle(id: string) {
    const next = new Set(isAll ? [] : explicit);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setAccountsParam(next.size === 0 ? "" : Array.from(next).join(","));
  }

  return (
    <Popover>
      <PopoverTrigger className={TRIGGER_CLASS}>
        <ChevronsUpDown className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="truncate">{label}</span>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 p-0">
        <div className="flex items-center justify-between px-2.5 pt-2.5 text-xs">
          <span className="text-muted-foreground">Combine accounts</span>
          <div className="flex gap-3">
            <button
              className={cn("hover:underline", isAll ? "text-primary" : "text-muted-foreground")}
              onClick={() => setAccountsParam(null)}
            >
              All
            </button>
            <button
              className="text-muted-foreground hover:underline"
              onClick={() => setAccountsParam("")}
            >
              Clear
            </button>
          </div>
        </div>
        <AccountCommandList
          platform={null}
          mode="multi"
          selectedIds={selectedIds}
          onToggle={(a) => toggle(a.id)}
        />
      </PopoverContent>
    </Popover>
  );
}
