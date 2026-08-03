"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  LayoutGrid,
  ChevronDown,
  Link2,
  Settings,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { useSharedFilterQuery } from "@/hooks/use-shared-query";
import { PLATFORM_TABS } from "@/lib/constants";

const PLATFORM_NAV: { platform: string; label: string }[] = [
  { platform: "meta", label: "Meta Ads" },
  { platform: "tiktok", label: "TikTok Ads" },
  { platform: "google_ads", label: "Google Ads" },
];

const ITEM =
  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors";
const ACTIVE = "bg-sidebar-primary text-sidebar-primary-foreground";
const INACTIVE =
  "text-sidebar-foreground/75 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground";

function SectionLabel({ children }: { children: React.ReactNode }) {
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
 */
export function Sidebar() {
  const pathname = usePathname() ?? "";
  const withQuery = useSharedFilterQuery();
  const [platformsOpen, setPlatformsOpen] = useState(true);

  return (
    <aside className="flex w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground">
      {/* Brand */}
      <div className="flex items-center gap-3 px-5 py-5">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-white/15 ring-1 ring-white/20">
          <Sparkles className="size-5" />
        </span>
        <span className="text-[15px] font-bold leading-tight tracking-tight">
          Base Data
          <br />
          Dashboard
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-3 pb-4">
        <SectionLabel>Data</SectionLabel>

        <Link
          href={withQuery("/dashboard")}
          className={cn(ITEM, pathname === "/dashboard" ? ACTIVE : INACTIVE)}
        >
          <LayoutGrid className="size-[18px] shrink-0" />
          Summary
        </Link>

        {/* Platform Data group */}
        <button
          type="button"
          onClick={() => setPlatformsOpen((o) => !o)}
          className={cn(ITEM, INACTIVE, "mt-0.5 w-full")}
          aria-expanded={platformsOpen}
        >
          <LayoutGrid className="size-[18px] shrink-0" />
          <span className="flex-1 text-left">Platform Data</span>
          <ChevronDown
            className={cn(
              "size-4 shrink-0 transition-transform",
              platformsOpen && "rotate-180"
            )}
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

        <SectionLabel>User</SectionLabel>

        <Link
          href="/settings/connections"
          className={cn(
            ITEM,
            pathname.startsWith("/settings/connections") ? ACTIVE : INACTIVE
          )}
        >
          <Link2 className="size-[18px] shrink-0" />
          Account Binding
        </Link>
        <Link
          href="/settings/org"
          className={cn(
            ITEM,
            "mt-0.5",
            pathname.startsWith("/settings/org") ? ACTIVE : INACTIVE
          )}
        >
          <Settings className="size-[18px] shrink-0" />
          Settings
        </Link>
      </nav>
    </aside>
  );
}
