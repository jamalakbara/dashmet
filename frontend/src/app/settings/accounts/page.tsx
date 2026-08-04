"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Search } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { SegmentControl } from "@/components/ui/segment-control";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { PaginationBar } from "@/components/shared/pagination-bar";
import { accountsApi } from "@/lib/api/accounts";
import { queryKeys } from "@/lib/query-keys";
import { useDebounced } from "@/hooks/use-account";
import type { AccountType } from "@/types/enums";

const PAGE_SIZE = 20;

interface Account {
  id: string;
  name: string;
  platform: string;
  currency: string;
  account_type: AccountType;
  account_status: string;
}

interface AccountsPage {
  data: Account[];
  pagination: { total: number; total_pages: number; page: number; per_page: number };
}

const PLATFORM_TABS = [
  { value: "all", label: "All" },
  { value: "meta", label: "Meta" },
  { value: "tiktok", label: "TikTok" },
  { value: "google_ads", label: "Google Ads" },
];

export default function AccountsSettingsPage() {
  const qc = useQueryClient();

  const [searchInput, setSearchInput] = useState("");
  const [platform, setPlatform] = useState("all");
  const [page, setPage] = useState(1);
  const debounced = useDebounced(searchInput.trim(), 250);

  // Any new search/filter restarts paging from the first page.
  useEffect(() => {
    setPage(1);
  }, [debounced, platform]);

  const platformParam = platform === "all" ? null : platform;

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.accountsList(platformParam, debounced, page),
    queryFn: async () =>
      (
        await accountsApi.list({
          search: debounced || undefined,
          platform: platformParam ?? undefined,
          page,
          per_page: PAGE_SIZE,
        })
      ).data as AccountsPage,
    placeholderData: (prev) => prev, // avoid list flash while typing / paging
  });

  const mutation = useMutation({
    mutationFn: ({ id, account_type }: { id: string; account_type: AccountType }) =>
      accountsApi.updateConfig(id, { account_type }),
    onSuccess: (_, { account_type }) => {
      // Prefix-invalidates every accounts cache (list, picker search, count).
      qc.invalidateQueries({ queryKey: queryKeys.accounts() });
      toast.success(`Account type updated to ${account_type === "cpas" ? "CPAS" : "Standard"}`);
    },
    onError: () => toast.error("Failed to update account type"),
  });

  const accounts = data?.data ?? [];
  const pagination = data?.pagination;
  const filtering = debounced.length > 0 || platform !== "all";

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm font-medium">Account Type</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          CPAS (Collaborative Ads) accounts show traffic metrics only — ROAS and conversion data are owned by the retailer. CPAS applies to Meta accounts only.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-48 max-w-64 flex-1">
          <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search accounts…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="h-8 pl-8"
          />
        </div>
        <SegmentControl
          items={PLATFORM_TABS}
          value={platform}
          onValueChange={setPlatform}
          ariaLabel="Filter accounts by platform"
        />
      </div>

      <div className="space-y-2">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <div className="h-10 animate-pulse rounded bg-muted" />
              </CardContent>
            </Card>
          ))
        ) : accounts.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {filtering ? "No accounts match your filters." : "No ad accounts connected yet."}
          </p>
        ) : (
          accounts.map((account) => (
            <Card key={account.id}>
              <CardContent className="flex items-center justify-between gap-4 p-4">
                <div className="flex min-w-0 items-center gap-3">
                  <PlatformBadge platform={account.platform} />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{account.name}</p>
                    <p className="text-xs text-muted-foreground">{account.currency}</p>
                  </div>
                </div>
                {account.platform === "meta" ? (
                  <Select
                    items={[
                      { value: "standard", label: "Standard" },
                      { value: "cpas", label: "CPAS" },
                    ]}
                    value={account.account_type}
                    onValueChange={(val) =>
                      mutation.mutate({ id: account.id, account_type: val as AccountType })
                    }
                    disabled={mutation.isPending}
                  >
                    <SelectTrigger className="w-36 shrink-0">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="standard">Standard</SelectItem>
                      <SelectItem value="cpas">CPAS</SelectItem>
                    </SelectContent>
                  </Select>
                ) : (
                  <span className="w-36 shrink-0 text-center text-sm text-muted-foreground">—</span>
                )}
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {pagination && pagination.total_pages > 1 && (
        <PaginationBar
          page={page}
          totalPages={pagination.total_pages}
          total={pagination.total}
          perPage={PAGE_SIZE}
          onPage={setPage}
        />
      )}
    </div>
  );
}
