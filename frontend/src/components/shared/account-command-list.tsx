"use client";

import { useState } from "react";
import { Star } from "lucide-react";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { Checkbox } from "@/components/ui/checkbox";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { useAccountSearch, type Account } from "@/hooks/use-account";
import { useUIStore, type AccountSnapshot } from "@/stores/ui-store";
import { cn } from "@/lib/utils";

const PLATFORM_LABELS: Record<string, string> = {
  meta: "Meta",
  tiktok: "TikTok",
  google_ads: "Google Ads",
  google_analytics: "Google Analytics",
};

function toSnapshot(a: Account): AccountSnapshot {
  return {
    id: a.id,
    name: a.name,
    platform: a.platform,
    currency: a.currency,
    external_id: a.external_id,
    account_type: a.account_type,
  };
}

function snapshotToAccount(s: AccountSnapshot): Account {
  return {
    id: s.id,
    name: s.name,
    platform: s.platform,
    currency: s.currency,
    external_id: s.external_id,
    account_type: (s.account_type as Account["account_type"]) ?? "standard",
  };
}

interface AccountCommandListProps {
  /** Active platform (null = combined dashboard → results grouped by platform). */
  platform: string | null;
  mode: "single" | "multi";
  selectedId?: string | null;
  selectedIds?: Set<string>;
  onSelect?: (account: Account) => void;
  onToggle?: (account: Account) => void;
}

export function AccountCommandList({
  platform,
  mode,
  selectedId,
  selectedIds,
  onSelect,
  onToggle,
}: AccountCommandListProps) {
  const [search, setSearch] = useState("");
  const { accounts, isFetching } = useAccountSearch(platform, search);

  const snapshots = useUIStore((s) => s.accountSnapshots);
  const pinnedIds = useUIStore((s) => s.pinnedAccountIds);
  const recentIds = useUIStore((s) => s.recentAccountIds);
  const recordAccount = useUIStore((s) => s.recordAccount);
  const togglePin = useUIStore((s) => s.togglePin);

  const searching = search.trim().length > 0;
  const scopeOk = (p: string) => !platform || p === platform;

  const pinned = pinnedIds
    .map((id) => snapshots[id])
    .filter((s): s is AccountSnapshot => !!s && scopeOk(s.platform));
  const recent = recentIds
    .filter((id) => !pinnedIds.includes(id))
    .map((id) => snapshots[id])
    .filter((s): s is AccountSnapshot => !!s && scopeOk(s.platform))
    .slice(0, 5);

  // When idle, don't repeat pinned/recent inside the results list.
  const shortcutIds = new Set([...pinned, ...recent].map((s) => s.id));
  const results = searching ? accounts : accounts.filter((a) => !shortcutIds.has(a.id));

  function pick(account: Account) {
    recordAccount(toSnapshot(account));
    if (mode === "single") onSelect?.(account);
    else onToggle?.(account);
  }

  const isSelected = (id: string) =>
    mode === "single" ? selectedId === id : !!selectedIds?.has(id);

  function Row({ account }: { account: Account }) {
    const selected = isSelected(account.id);
    const pinnedNow = pinnedIds.includes(account.id);
    return (
      <CommandItem
        value={`${account.id} ${account.name} ${account.external_id ?? ""}`}
        onSelect={() => pick(account)}
        data-checked={mode === "single" ? selected : undefined}
        className="gap-2.5 py-2"
      >
        {mode === "multi" && (
          <Checkbox checked={selected} className="pointer-events-none shrink-0" />
        )}
        <PlatformBadge platform={account.platform} size="sm" />
        <div className="flex min-w-0 flex-1 flex-col leading-tight">
          <span className="truncate font-medium">{account.name}</span>
          <span className="truncate text-xs text-muted-foreground tabular-nums">
            {account.business_name ?? account.external_id}
          </span>
        </div>
        <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
          {account.currency}
        </span>
        <button
          type="button"
          aria-label={pinnedNow ? "Unpin account" : "Pin account"}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            togglePin(account.id);
          }}
          className="shrink-0 rounded p-0.5 hover:bg-accent"
        >
          <Star
            className={cn(
              "size-3.5",
              pinnedNow ? "fill-amber-400 text-amber-400" : "text-muted-foreground"
            )}
          />
        </button>
      </CommandItem>
    );
  }

  // Combined dashboard: group results by platform.
  const grouped: Record<string, Account[]> = {};
  if (!platform) {
    for (const a of results) (grouped[a.platform] ??= []).push(a);
  }

  return (
    <Command shouldFilter={false} className="bg-transparent">
      <CommandInput
        placeholder="Search accounts…"
        value={search}
        onValueChange={setSearch}
      />
      <CommandList>
        <CommandEmpty>
          {isFetching ? "Searching…" : "No accounts found."}
        </CommandEmpty>

        {!searching && pinned.length > 0 && (
          <CommandGroup heading="Pinned">
            {pinned.map((s) => (
              <Row key={`pin-${s.id}`} account={snapshotToAccount(s)} />
            ))}
          </CommandGroup>
        )}

        {!searching && recent.length > 0 && (
          <CommandGroup heading="Recent">
            {recent.map((s) => (
              <Row key={`recent-${s.id}`} account={snapshotToAccount(s)} />
            ))}
          </CommandGroup>
        )}

        {(pinned.length > 0 || recent.length > 0) && !searching && results.length > 0 && (
          <CommandSeparator />
        )}

        {platform ? (
          results.length > 0 && (
            <CommandGroup heading={searching ? undefined : "All accounts"}>
              {results.map((a) => (
                <Row key={a.id} account={a} />
              ))}
            </CommandGroup>
          )
        ) : (
          Object.entries(grouped).map(([p, list]) => (
            <CommandGroup key={p} heading={PLATFORM_LABELS[p] ?? p}>
              {list.map((a) => (
                <Row key={a.id} account={a} />
              ))}
            </CommandGroup>
          ))
        )}
      </CommandList>
    </Command>
  );
}
