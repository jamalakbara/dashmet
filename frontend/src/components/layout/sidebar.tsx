"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  LayoutDashboard,
  Layers,
  ChevronDown,
  ChevronLeft,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { AnimatedIcon } from "@/components/shared/animated-icon";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { useSharedFilterQuery } from "@/hooks/use-shared-query";
import { useUIStore } from "@/stores/ui-store";
import { PLATFORM_TABS } from "@/lib/constants";

const PLATFORM_NAV: { platform: string; label: string }[] = [
  { platform: "meta", label: "Meta Ads" },
  { platform: "tiktok", label: "TikTok Ads" },
  { platform: "google_ads", label: "Google Ads" },
];

const ITEM =
  "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors";
const ACTIVE = "bg-sidebar-primary text-sidebar-primary-foreground";
const INACTIVE =
  "text-sidebar-foreground/75 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground";

function SectionLabel({
  collapsed,
  children,
}: {
  collapsed: boolean;
  children: React.ReactNode;
}) {
  if (collapsed) return <div className="pt-4" aria-hidden />;
  return (
    <p className="px-3 pb-1 pt-4 text-[10px] font-semibold uppercase tracking-[0.14em] text-sidebar-foreground/45">
      {children}
    </p>
  );
}

/**
 * Indigo sidebar rail (Base Data style): brand block, a DATA section with the
 * combined Summary plus an expandable Platform Data group, and a USER section.
 * Each platform's own views live in the top action strip, not here.
 *
 * The whole rail can collapse to an icon-only strip and expand back; the choice
 * lives in the persisted UI store (`sidebarCollapsed`) so it survives navigation
 * and reloads. When collapsed, labels/section headers/chevrons hide and each row
 * centers its icon (with a native tooltip via `title`).
 */
export function Sidebar() {
  const pathname = usePathname() ?? "";
  const withQuery = useSharedFilterQuery();
  const [platformsOpen, setPlatformsOpen] = useState(true);
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleCollapsed = useUIStore((s) => s.toggleSidebar);

  return (
    <aside
      className={cn(
        "relative z-30 m-3 flex shrink-0 flex-col rounded-2xl bg-sidebar text-sidebar-foreground shadow-xl ring-1 ring-black/5 transition-[width] duration-200 ease-in-out",
        collapsed ? "w-[68px]" : "w-60"
      )}
    >
      {/* Collapse toggle — a handle straddling the right edge, same spot in both
          states so it never jumps when the rail resizes. */}
      <button
        type="button"
        onClick={toggleCollapsed}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        className="absolute -right-3 top-1/2 z-20 flex size-6 -translate-y-1/2 items-center justify-center rounded-full bg-background text-foreground shadow-md ring-1 ring-border transition-colors hover:bg-muted"
      >
        <ChevronLeft
          className={cn(
            "size-4 transition-transform duration-200",
            collapsed && "rotate-180"
          )}
        />
      </button>

      {/* Brand */}
      <div
        className={cn(
          "flex items-center py-5",
          collapsed ? "justify-center px-3" : "gap-3 px-5"
        )}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.svg" alt="Base Data" className="size-10 shrink-0 rounded-xl" />
        {!collapsed && (
          <span className="text-[15px] font-bold leading-tight tracking-tight">
            Base Data
            <br />
            Dashboard
          </span>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden px-3 pb-4">
        <SectionLabel collapsed={collapsed}>Data</SectionLabel>

        <Link
          href={withQuery("/dashboard")}
          title={collapsed ? "Summary" : undefined}
          className={cn(
            ITEM,
            collapsed && "justify-center px-0",
            pathname === "/dashboard" ? ACTIVE : INACTIVE
          )}
        >
          <AnimatedIcon
            icon={LayoutDashboard}
            motionPreset="nudge"
            className="shrink-0"
            iconClassName="size-[18px]"
          />
          {!collapsed && "Summary"}
        </Link>

        {/* Platform Data group */}
        {collapsed ? (
          // Collapsed: skip the toggle, show each platform icon directly.
          <div className="mt-0.5 space-y-0.5">
            {PLATFORM_NAV.map(({ platform, label }) => {
              const landing = `/${platform}/${PLATFORM_TABS[platform][0].slug}`;
              const active = pathname.startsWith(`/${platform}`);
              return (
                <Link
                  key={platform}
                  href={withQuery(landing)}
                  title={label}
                  className={cn(
                    ITEM,
                    "justify-center px-0",
                    active ? ACTIVE : INACTIVE
                  )}
                >
                  <PlatformBadge platform={platform} size="sm" />
                </Link>
              );
            })}
          </div>
        ) : (
          <>
            <button
              type="button"
              onClick={() => setPlatformsOpen((o) => !o)}
              className={cn(ITEM, INACTIVE, "mt-0.5 w-full")}
              aria-expanded={platformsOpen}
            >
              <AnimatedIcon
                icon={Layers}
                motionPreset="nudge"
                className="shrink-0"
                iconClassName="size-[18px]"
              />
              <span className="flex-1 text-left">Platform Data</span>
              <AnimatedIcon
                icon={ChevronDown}
                motionPreset="flip"
                trigger="state"
                active={platformsOpen}
                className="shrink-0"
                iconClassName="size-4"
              />
            </button>

            {platformsOpen && (
              <div className="mt-0.5 space-y-0.5 pl-3">
                {PLATFORM_NAV.map(({ platform, label }) => {
                  const landing = `/${platform}/${PLATFORM_TABS[platform][0].slug}`;
                  const active = pathname.startsWith(`/${platform}`);
                  return (
                    <Link
                      key={platform}
                      href={withQuery(landing)}
                      className={cn(ITEM, "py-1.5", active ? ACTIVE : INACTIVE)}
                    >
                      <PlatformBadge platform={platform} size="sm" />
                      {label}
                    </Link>
                  );
                })}
              </div>
            )}
          </>
        )}

      </nav>

      {/* Settings — pinned to the bottom of the rail */}
      <div className="border-t border-sidebar-border/50 px-3 py-3">
        <Link
          href="/settings/org"
          title={collapsed ? "Settings" : undefined}
          className={cn(
            ITEM,
            collapsed && "justify-center px-0",
            pathname.startsWith("/settings/org") ? ACTIVE : INACTIVE
          )}
        >
          <AnimatedIcon
            icon={Settings}
            motionPreset="spin"
            className="shrink-0"
            iconClassName="size-[18px]"
          />
          {!collapsed && "Settings"}
        </Link>
      </div>
    </aside>
  );
}
