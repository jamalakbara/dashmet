"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { UserMenu } from "@/components/shared/user-menu";
import { useSharedFilterQuery } from "@/hooks/use-shared-query";
import { PLATFORM_TABS } from "@/lib/constants";

/** Top-level destinations (the "unusual menu" — a centered OS-window pill nav). */
const NAV: { key: string; label: string; href: (slug: string) => string }[] = [
  { key: "dashboard", label: "Dashboard", href: () => "/dashboard" },
  { key: "meta", label: "Meta", href: (s) => `/meta/${s}` },
  { key: "tiktok", label: "TikTok", href: (s) => `/tiktok/${s}` },
  { key: "google_ads", label: "Google", href: (s) => `/google_ads/${s}` },
];

export function TopNav() {
  const pathname = usePathname() ?? "";
  const withQuery = useSharedFilterQuery();

  const isActive = (key: string) =>
    key === "dashboard" ? pathname === "/dashboard" : pathname.startsWith(`/${key}`);

  return (
    <header className="relative flex h-12 shrink-0 items-center justify-between gap-4 border-b border-border px-4">
      {/* Left: traffic-light window dots + brand */}
      <div className="flex items-center gap-3">
        <div className="hidden items-center gap-1.5 sm:flex">
          <span className="size-2.5 rounded-full bg-[var(--iris-7)]/70" />
          <span className="size-2.5 rounded-full bg-[var(--iris-1)]/70" />
          <span className="size-2.5 rounded-full bg-[var(--iris-2)]/70" />
        </div>
        <span className="font-display text-sm font-bold tracking-tight">
          DASH<span className="text-primary">MET</span>
        </span>
      </div>

      {/* Center: pill nav */}
      <nav className="absolute left-1/2 flex -translate-x-1/2 items-center gap-0.5 rounded-full border border-border bg-card/60 p-0.5 backdrop-blur">
        {NAV.map((item) => {
          const landing =
            item.key === "dashboard"
              ? "/dashboard"
              : item.href(PLATFORM_TABS[item.key]?.[0]?.slug ?? "overview");
          const active = isActive(item.key);
          return (
            <Link
              key={item.key}
              href={withQuery(landing)}
              aria-current={active ? "page" : undefined}
              className={cn(
                "rounded-full px-3.5 py-1.5 font-mono text-xs uppercase tracking-wide transition-colors",
                active
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Right: user menu (the window's account control) */}
      <div className="flex items-center gap-3">
        <UserMenu />
      </div>
    </header>
  );
}
