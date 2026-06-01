"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { BarChart2, Table, TrendingUp, Image, Settings } from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/ui-store";

const NAV_ITEMS = [
  { label: "Overview",  href: "/overview",  icon: BarChart2 },
  { label: "Periodic",  href: "/periodic",  icon: TrendingUp },
  { label: "Table",     href: "/table",     icon: Table },
  { label: "Ads",       href: "/ads",       icon: Image },
];

export function Sidebar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { sidebarCollapsed } = useUIStore();

  const sharedParams = new URLSearchParams();
  ["account_id", "date_preset", "date_start", "date_end"].forEach(key => {
    const v = searchParams.get(key);
    if (v) sharedParams.set(key, v);
  });
  const sharedQuery = sharedParams.toString();

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
      <nav className="flex-1 space-y-1 p-2">
        {NAV_ITEMS.map(({ label, href, icon: Icon }) => (
          <Link
            key={href}
            href={sharedQuery ? `${href}?${sharedQuery}` : href}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              pathname === href
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            )}
          >
            <Icon className="h-4 w-4 shrink-0" />
            {!sidebarCollapsed && label}
          </Link>
        ))}
      </nav>

      {/* Settings */}
      <div className="border-t p-2">
        <Link
          href="/settings/org"
          className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <Settings className="h-4 w-4 shrink-0" />
          {!sidebarCollapsed && "Settings"}
        </Link>
      </div>
    </aside>
  );
}
