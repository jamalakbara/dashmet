"use client";

import dynamic from "next/dynamic";
import { Bell, Menu } from "lucide-react";
import { AnimatedIcon } from "@/components/shared/animated-icon";
import { useUIStore } from "@/stores/ui-store";
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
  { ssr: false, loading: () => <div className="h-8 w-40 animate-pulse rounded-lg bg-muted sm:w-56" /> }
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
  const openMobileNav = useUIStore((s) => s.setMobileNavOpen);

  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-border bg-card px-3 sm:gap-4 sm:px-5">
      {/* Left: hamburger (mobile) · platform identity · freshness · account picker */}
      <div className="flex min-w-0 items-center gap-2 sm:gap-3">
        <button
          type="button"
          onClick={() => openMobileNav(true)}
          aria-label="Open navigation"
          className="flex size-9 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground md:hidden"
        >
          <Menu className="size-5" />
        </button>
        {/* Platform identity + freshness collapse away on narrow screens — the
            account switcher already carries a platform badge, so this is
            redundant chrome there. */}
        <div className="hidden min-w-0 items-center gap-3 sm:flex">
          {platform ? <PlatformBadge platform={platform} size="md" /> : null}
          <span className="shrink-0 text-lg font-bold tracking-tight">{title}</span>
          <div className="hidden min-w-0 md:block">
            <SyncStatusBadge />
          </div>
        </div>
        <AccountSwitcher />
      </div>

      {/* Right: date · notifications · user. Date moves into the control strip
          below `sm` (see ControlStrip) so the narrow top bar doesn't collide the
          account name with the range button. */}
      <div className="flex shrink-0 items-center gap-3">
        <div className="hidden sm:block">
          <DateRangePicker />
        </div>
        <button
          type="button"
          aria-label="Notifications"
          className="group relative hidden size-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground sm:flex"
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
