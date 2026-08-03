"use client";

import dynamic from "next/dynamic";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { PlatformTabs } from "@/components/layout/platform-tabs";
import { FilterPopover } from "@/components/layout/filter-popover";
import { useSelectedAccount } from "@/hooks/use-account";
import { syncApi } from "@/lib/api/sync";
import { queryKeys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";

const AccountSwitcher = dynamic(
  () =>
    import("@/components/shared/account-switcher").then((m) => ({
      default: m.AccountSwitcher,
    })),
  { ssr: false, loading: () => <div className="h-8 w-56 animate-pulse rounded-lg bg-muted" /> }
);

/**
 * Action strip under the top bar: primary Sync Data action, the account picker,
 * the platform view tabs, and a Filter affordance. Manual sync stays here as a
 * recovery path (P-5) rather than a permanent fixture on every card.
 */
export function ControlStrip() {
  const { accountId } = useSelectedAccount();
  const queryClient = useQueryClient();

  const sync = useMutation({
    mutationFn: () => syncApi.trigger(accountId!),
    onSuccess: () => {
      toast.success("Sync started — data will refresh shortly.");
      queryClient.invalidateQueries({ queryKey: queryKeys.syncStatus(accountId ?? "") });
    },
    onError: () => toast.error("Couldn't start sync. Try again."),
  });

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-border bg-card px-5 py-3">
      <Button
        size="lg"
        onClick={() => sync.mutate()}
        disabled={!accountId || sync.isPending}
        className="gap-2"
      >
        <RefreshCw className={cn("size-4", sync.isPending && "animate-spin")} />
        Sync Data
      </Button>

      <AccountSwitcher />

      <div className="hidden items-center rounded-lg border border-border p-0.5 sm:flex">
        <PlatformTabs />
      </div>

      <FilterPopover />
    </div>
  );
}
