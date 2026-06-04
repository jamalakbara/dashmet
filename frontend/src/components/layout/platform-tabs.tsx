"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { usePlatform } from "@/hooks/use-platform";
import { useSharedFilterQuery } from "@/hooks/use-shared-query";
import { PLATFORM_TABS } from "@/lib/constants";

/**
 * Route-based tab bar for a platform's views (Overview / Periodic / Table / …).
 * Uses <Link> (not the shadcn Tabs primitive) so each tab owns a real URL and
 * deep links stay shareable. Self-hides on the combined dashboard (platform === null).
 */
export function PlatformTabs() {
  const platform = usePlatform();
  const pathname = usePathname() ?? "";
  const withQuery = useSharedFilterQuery();

  if (!platform) return null;
  const tabs = PLATFORM_TABS[platform] ?? [];
  if (tabs.length === 0) return null;

  return (
    <div className="shrink-0 border-b bg-card px-6">
      <nav className="inline-flex h-11 items-center gap-1" aria-label={`${platform} views`}>
        {tabs.map((tab) => {
          const href = `/${platform}/${tab.slug}`;
          const active = pathname === href;
          return (
            <Link
              key={tab.slug}
              href={withQuery(href)}
              aria-current={active ? "page" : undefined}
              className={cn(
                "relative inline-flex h-11 items-center border-b-2 px-3 text-sm font-medium transition-colors",
                active
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
