"use client";

import dynamic from "next/dynamic";
import { Bell } from "lucide-react";
import { AnimatedIcon } from "@/components/shared/animated-icon";
import { DateRangePicker } from "@/components/shared/date-range-picker";
import { SyncStatusBadge } from "@/components/shared/sync-status-badge";
import { UserMenu } from "@/components/shared/user-menu";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { usePlatform } from "@/hooks/use-platform";
import { useMe } from "@/hooks/use-me";

const AccountSwitcher = dynamic(
  () =>
    import("@/components/shared/account-switcher").then((m) => ({
      default: m.AccountSwitcher,
    })),
  { ssr: false, loading: () => <div className="h-8 w-56 animate-pulse rounded-lg bg-muted" /> }
);

const PLATFORM_TITLE: Record<string, string> = {
  meta: "Meta Ads",
  tiktok: "TikTok Ads",
  google_ads: "Google Ads",
};

/**
 * Light top chrome bar: active-platform title on the left, then freshness /
 * date-range / notifications / user on the right. Mirrors the Base Data header.
 */
export function TopBar() {
  const platform = usePlatform();
  const title = platform ? PLATFORM_TITLE[platform] : "Summary";

  const { data: me } = useMe();

  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-border bg-card px-5">
      {/* Left: platform identity · freshness · account picker */}
      <div className="flex min-w-0 items-center gap-3">
        {platform ? (
          <PlatformBadge platform={platform} size="md" />
        ) : null}
        <span className="shrink-0 text-lg font-bold tracking-tight">{title}</span>
        <div className="hidden min-w-0 md:block">
          <SyncStatusBadge />
        </div>
        <AccountSwitcher />
      </div>

      {/* Right: date · notifications · user */}
      <div className="flex shrink-0 items-center gap-3">
        <DateRangePicker />
        <button
          type="button"
          aria-label="Notifications"
          className="group relative flex size-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
        >
          <AnimatedIcon icon={Bell} motionPreset="wiggle" iconClassName="size-[18px]" />
        </button>
        <div className="flex items-center gap-2.5">
          <UserMenu />
          <div className="hidden leading-tight sm:block">
            <p className="text-sm font-semibold">{me?.name ?? "—"}</p>
            <p className="max-w-[160px] truncate text-xs text-muted-foreground">
              {me?.email ?? ""}
            </p>
          </div>
        </div>
      </div>
    </header>
  );
}
