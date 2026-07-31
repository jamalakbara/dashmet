"use client";

import dynamic from "next/dynamic";
import { DateRangePicker } from "@/components/shared/date-range-picker";
import { SyncStatusBadge } from "@/components/shared/sync-status-badge";
import { PlatformTabs } from "@/components/layout/platform-tabs";

const AccountSwitcher = dynamic(
  () =>
    import("@/components/shared/account-switcher").then((m) => ({
      default: m.AccountSwitcher,
    })),
  { ssr: false, loading: () => <div className="h-8 w-48 animate-pulse rounded-lg bg-muted" /> }
);

/**
 * Secondary control bar under the window chrome: platform sub-tabs on the left
 * (self-hides on the combined dashboard), account/date/sync filters on the right.
 */
export function ControlStrip() {
  return (
    <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-2">
      <div className="min-h-8 flex items-center">
        <PlatformTabs />
      </div>
      <div className="flex items-center gap-3">
        <AccountSwitcher />
        <DateRangePicker />
        <SyncStatusBadge />
      </div>
    </div>
  );
}
