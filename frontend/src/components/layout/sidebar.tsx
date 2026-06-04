"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Settings, LayoutDashboard } from "lucide-react";
import { cn } from "@/lib/utils";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { useUIStore } from "@/stores/ui-store";
import { useSharedFilterQuery } from "@/hooks/use-shared-query";
import { PLATFORM_TABS } from "@/lib/constants";

const PLATFORM_NAV: { platform: string; label: string }[] = [
  { platform: "meta", label: "Meta" },
  { platform: "tiktok", label: "TikTok" },
];

const NAV_BASE =
  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors";
const NAV_ACTIVE = "bg-primary text-primary-foreground";
const NAV_INACTIVE =
  "text-muted-foreground hover:bg-accent hover:text-accent-foreground";

export function Sidebar() {
  const pathname = usePathname() ?? "";
  const { sidebarCollapsed } = useUIStore();
  const withQuery = useSharedFilterQuery();

  return (
    <aside
      className={cn(
        "flex flex-col border-r bg-card transition-all duration-200",
        sidebarCollapsed ? "w-16" : "w-56"
      )}
    >
      {/* Logo */}
      <div className="flex h-14 items-center border-b px-4">
        {!sidebarCollapsed && (
          <span className="text-lg font-bold tracking-tight">DashMet</span>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-1 overflow-y-auto p-2">
        {/* Combined dashboard */}
        <Link
          href={withQuery("/dashboard")}
          className={cn(NAV_BASE, pathname === "/dashboard" ? NAV_ACTIVE : NAV_INACTIVE)}
        >
          <LayoutDashboard className="h-4 w-4 shrink-0" />
          {!sidebarCollapsed && "Dashboard"}
        </Link>

        {/* One entry per platform — its views live in the top tab bar */}
        {PLATFORM_NAV.map(({ platform, label }) => {
          const landing = `/${platform}/${PLATFORM_TABS[platform][0].slug}`;
          const active = pathname.startsWith(`/${platform}`);
          return (
            <Link
              key={platform}
              href={withQuery(landing)}
              className={cn(
                NAV_BASE,
                sidebarCollapsed && "justify-center",
                active ? NAV_ACTIVE : NAV_INACTIVE
              )}
            >
              <PlatformBadge platform={platform} size="sm" />
              {!sidebarCollapsed && label}
            </Link>
          );
        })}
      </nav>

      {/* Settings */}
      <div className="border-t p-2">
        <Link
          href="/settings/org"
          className={cn(NAV_BASE, NAV_INACTIVE, sidebarCollapsed && "justify-center")}
        >
          <Settings className="h-4 w-4 shrink-0" />
          {!sidebarCollapsed && "Settings"}
        </Link>
      </div>
    </aside>
  );
}
