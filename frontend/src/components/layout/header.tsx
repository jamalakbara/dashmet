"use client";

import { Menu } from "lucide-react";
import { UserMenu } from "@/components/shared/user-menu";
import { NotificationCenter } from "@/components/shared/notification-center";
import { useMe } from "@/hooks/use-me";
import { useUIStore } from "@/stores/ui-store";

/**
 * Settings top bar — no account picker / date range / sync here (those are
 * dashboard-only filters). Just the mobile nav trigger and the user control.
 */
export function Header() {
  const { data: me } = useMe();
  const openMobileNav = useUIStore((s) => s.setMobileNavOpen);

  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-border bg-card px-3 sm:px-5">
      {/* Hamburger opens the nav drawer below `md`, where the rail is hidden. */}
      <button
        type="button"
        onClick={() => openMobileNav(true)}
        aria-label="Open navigation"
        className="flex size-9 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground md:hidden"
      >
        <Menu className="size-5" />
      </button>
      <div className="flex items-center gap-2.5 ml-auto">
        <NotificationCenter />
        <div className="hidden text-right leading-tight sm:block">
          <p className="text-sm font-semibold">{me?.name ?? "—"}</p>
          <p className="max-w-[160px] truncate text-xs text-muted-foreground">
            {me?.email ?? ""}
          </p>
        </div>
        <UserMenu />
      </div>
    </header>
  );
}
