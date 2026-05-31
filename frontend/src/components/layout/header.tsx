"use client";

import dynamic from "next/dynamic";
import { PanelLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DateRangePicker } from "@/components/shared/date-range-picker";
import { SyncStatusBadge } from "@/components/shared/sync-status-badge";
import { UserMenu } from "@/components/shared/user-menu";
import { useUIStore } from "@/stores/ui-store";

const AccountSwitcher = dynamic(
  () => import("@/components/shared/account-switcher").then((m) => ({ default: m.AccountSwitcher })),
  { ssr: false, loading: () => <div className="h-8 w-48 animate-pulse rounded-lg bg-muted" /> }
);

export function Header() {
  const { toggleSidebar } = useUIStore();

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b bg-card px-4">
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleSidebar}
          aria-label="Toggle sidebar"
        >
          <PanelLeft className="size-4" />
        </Button>
        <AccountSwitcher />
        <DateRangePicker />
      </div>
      <div className="flex items-center gap-4">
        <SyncStatusBadge />
        <UserMenu />
      </div>
    </header>
  );
}
