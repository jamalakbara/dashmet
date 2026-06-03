"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { accountsApi } from "@/lib/api/accounts";
import { queryKeys } from "@/lib/query-keys";
import type { AccountType } from "@/types/enums";

interface Account {
  id: string;
  name: string;
  platform: string;
  currency: string;
  account_type: AccountType;
  account_status: string;
}

export default function AccountsSettingsPage() {
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.accounts(),
    queryFn: async () => (await accountsApi.list()).data.data as Account[],
  });

  const mutation = useMutation({
    mutationFn: ({ id, account_type }: { id: string; account_type: AccountType }) =>
      accountsApi.updateConfig(id, { account_type }),
    onSuccess: (_, { account_type }) => {
      qc.invalidateQueries({ queryKey: queryKeys.accounts() });
      toast.success(`Account type updated to ${account_type === "cpas" ? "CPAS" : "Standard"}`);
    },
    onError: () => toast.error("Failed to update account type"),
  });

  const accounts = data ?? [];

  return (
    <div className="space-y-2">
      <div className="mb-4">
        <h2 className="text-sm font-medium">Account Type</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          CPAS (Collaborative Ads) accounts show traffic metrics only — ROAS and conversion data are owned by the retailer.
        </p>
      </div>

      {isLoading
        ? Array.from({ length: 3 }).map((_, i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <div className="h-10 animate-pulse rounded bg-muted" />
              </CardContent>
            </Card>
          ))
        : accounts.length === 0
        ? (
          <p className="text-sm text-muted-foreground">No ad accounts connected yet.</p>
        )
        : accounts.map((account) => (
            <Card key={account.id}>
              <CardContent className="flex items-center justify-between gap-4 p-4">
                <div className="flex items-center gap-3 min-w-0">
                  <PlatformBadge platform={account.platform} />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{account.name}</p>
                    <p className="text-xs text-muted-foreground">{account.currency}</p>
                  </div>
                </div>
                <Select
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
              </CardContent>
            </Card>
          ))}
    </div>
  );
}
