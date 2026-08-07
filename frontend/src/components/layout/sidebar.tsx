"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
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
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
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
 * The rail's content: brand block, DATA section (Summary + Platform Data group),
 * and a pinned Settings row. Shared verbatim between the desktop rail and the
 * mobile drawer.
 *
 * - `collapsed` drives the icon-only desktop layout. The mobile drawer always
 *   passes `collapsed={false}` — an off-canvas sheet has room for full labels.
 * - `onNavigate` fires when any nav link is tapped so the mobile drawer can
 *   close itself. Desktop leaves it undefined (the rail is persistent).
 * - `showCollapseToggle` hides the collapse chevron inside the mobile drawer,
 *   where collapsing an overlay makes no sense.
 */
function SidebarInner({
  collapsed,
  onNavigate,
  showCollapseToggle = true,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
  showCollapseToggle?: boolean;
}) {
  const pathname = usePathname() ?? "";
  const withQuery = useSharedFilterQuery();
  const [platformsOpen, setPlatformsOpen] = useState(true);
  const toggleCollapsed = useUIStore((s) => s.toggleSidebar);

  return (
    <div className="flex flex-1 flex-col motion-safe:animate-[sidebar-swap-in_200ms_ease-out]">
      {/* Brand + collapse toggle. The toggle sits next to the logo (ChatGPT
          style). When collapsed, the logo alone shows; hovering it swaps the
          logo for the expand button so the icon-only rail stays clean. */}
      <div
        className={cn(
          "flex items-center py-5",
          collapsed ? "justify-center px-3" : "gap-3 px-5"
        )}
      >
        {collapsed ? (
          <div className="group/brand relative flex size-10 items-center justify-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/logo.svg"
              alt="Base Data"
              className="size-10 shrink-0 rounded-xl transition-opacity group-hover/brand:opacity-0"
            />
            <button
              type="button"
              onClick={toggleCollapsed}
              aria-label="Expand sidebar"
              title="Expand sidebar"
              className="absolute inset-0 flex items-center justify-center rounded-xl bg-sidebar-accent text-sidebar-accent-foreground opacity-0 transition-opacity hover:bg-sidebar-accent group-hover/brand:opacity-100"
            >
              <ChevronLeft className="size-4 rotate-180" />
            </button>
          </div>
        ) : (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/logo.svg"
              alt="Base Data"
              className="size-10 shrink-0 rounded-xl"
            />
            <span className="text-[15px] font-bold leading-tight tracking-tight">
              Base Data
              <br />
              Dashboard
            </span>
            {showCollapseToggle && (
              <button
                type="button"
                onClick={toggleCollapsed}
                aria-label="Collapse sidebar"
                title="Collapse sidebar"
                className="ml-auto flex size-7 shrink-0 items-center justify-center rounded-lg text-sidebar-foreground/60 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              >
                <ChevronLeft className="size-4" />
              </button>
            )}
          </>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden px-3 pb-4 [contain:layout_paint]">
        <SectionLabel collapsed={collapsed}>Data</SectionLabel>

        <Link
          href={withQuery("/dashboard")}
          onClick={onNavigate}
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
                  onClick={onNavigate}
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
                      onClick={onNavigate}
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
          onClick={onNavigate}
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
    </div>
  );
}

/**
 * Indigo sidebar rail (Base Data style). Persistent from `md` up; below that it
 * hides and the {@link MobileSidebar} drawer takes over (opened from the top-bar
 * hamburger) so the content canvas gets the full narrow-screen width.
 *
 * The whole rail can collapse to an icon-only strip and expand back; the choice
 * lives in the persisted UI store (`sidebarCollapsed`) so it survives navigation
 * and reloads. When collapsed, labels/section headers/chevrons hide and each row
 * centers its icon (with a native tooltip via `title`).
 */
export function Sidebar() {
  const collapsed = useUIStore((s) => s.sidebarCollapsed);

  return (
    <>
      {/* In-flow spacer reserves the rail's footprint (margin + width) so the
          content column sizes off THIS, not the animating rail. It snaps with no
          transition, so content reflows exactly once per toggle instead of every
          frame. The rail itself is an absolute overlay (below) that animates its
          width over this empty slot — its tiny, contained subtree is the only
          thing that reflows during the 200ms. Hidden below `md`, where the
          mobile drawer replaces the rail and content spans full width. */}
      <div
        aria-hidden
        className={cn(
          "hidden shrink-0 md:block",
          collapsed ? "md:w-[92px]" : "md:w-[264px]"
        )}
      />
      <aside
        className={cn(
          "absolute inset-y-0 left-0 z-30 m-3 hidden flex-col rounded-2xl bg-sidebar text-sidebar-foreground shadow-xl ring-1 ring-black/5 transition-[width] duration-200 ease-out will-change-[width] md:flex",
          collapsed ? "w-[68px]" : "w-60"
        )}
      >
        {/* Keyed on `collapsed` so React remounts on every toggle, replaying the
            `sidebar-swap-in` fade — this masks the frames where the (discrete)
            collapsed/expanded layout doesn't yet match the (animating) rail
            width. */}
        <SidebarInner key={collapsed ? "collapsed" : "expanded"} collapsed={collapsed} />
      </aside>
    </>
  );
}

/**
 * Off-canvas nav drawer for narrow screens. Rendered at all sizes but only
 * reachable below `md` (the trigger — the top-bar hamburger — is itself
 * `md:hidden`). Backed by `mobileNavOpen` in the UI store; closes on backdrop
 * tap, route change, or any nav link tap.
 */
export function MobileSidebar() {
  const pathname = usePathname();
  const open = useUIStore((s) => s.mobileNavOpen);
  const setOpen = useUIStore((s) => s.setMobileNavOpen);

  // Close whenever the route changes (covers link taps and back/forward).
  useEffect(() => {
    setOpen(false);
  }, [pathname, setOpen]);

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      {/* Same detached-card shape as the ad-detail drawer (inset from the edges,
          rounded, own close button, near-full width) but keeping the indigo rail
          background — only the container style is borrowed, not the color. */}
      <SheetContent
        side="left"
        className="flex w-[calc(100%-1.5rem)] flex-col overflow-hidden bg-sidebar p-0 text-sidebar-foreground shadow-xl ring-1 ring-black/5 !inset-y-3 !left-3 !h-auto !rounded-2xl !border-0"
      >
        <SheetTitle className="sr-only">Navigation</SheetTitle>
        <SidebarInner
          collapsed={false}
          showCollapseToggle={false}
          onNavigate={() => setOpen(false)}
        />
      </SheetContent>
    </Sheet>
  );
}
