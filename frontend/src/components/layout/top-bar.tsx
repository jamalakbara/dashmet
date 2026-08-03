"use client";

import { useQuery } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import { Bell } from "lucide-react";
import { AnimatedIcon } from "@/components/shared/animated-icon";
import { DateRangePicker } from "@/components/shared/date-range-picker";
import { Switch } from "@/components/ui/switch";
import { SyncStatusBadge } from "@/components/shared/sync-status-badge";
import { UserMenu } from "@/components/shared/user-menu";
import { PlatformBadge } from "@/components/shared/platform-badge";
import { usePlatform } from "@/hooks/use-platform";
import { authApi } from "@/lib/api/auth";
import { queryKeys } from "@/lib/query-keys";

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

  const { data: me } = useQuery({
    queryKey: queryKeys.me(),
    queryFn: async () => (await authApi.me()).data.data as { name: string; email: string },
    staleTime: 60 * 60 * 1000,
  });

  // Global "compare previous period" toggle — drives every Overview section
  // (Trends overlay, card/funnel/table/ad delta pills) via URL state.
  const [compareStr, setCompareStr] = useQueryState("compare");

  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-border bg-card px-5">
      {/* Left: platform identity */}
      <div className="flex items-center gap-3">
        {platform ? (
          <PlatformBadge platform={platform} size="md" />
        ) : null}
        <span className="text-lg font-bold tracking-tight">{title}</span>
        <div className="ml-2 hidden md:block">
          <SyncStatusBadge />
        </div>
      </div>

      {/* Right: date · notifications · user */}
      <div className="flex items-center gap-3">
        <DateRangePicker />
        <label className="flex cursor-pointer items-center gap-2 whitespace-nowrap text-sm text-muted-foreground">
          <Switch
            checked={compareStr === "true"}
            onCheckedChange={(v) => setCompareStr(v ? "true" : null)}
          />
          Compare prev.
        </label>
        <button
          type="button"
          aria-label="Notifications"
          className="group relative flex size-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
        >
          <AnimatedIcon icon={Bell} motionPreset="wiggle" iconClassName="size-[18px]" />
        </button>
        <div className="flex items-center gap-2.5">
          <div className="hidden text-right leading-tight sm:block">
            <p className="text-sm font-semibold">{me?.name ?? "—"}</p>
            <p className="max-w-[160px] truncate text-xs text-muted-foreground">
              {me?.email ?? ""}
            </p>
          </div>
          <UserMenu />
        </div>
      </div>
    </header>
  );
}
