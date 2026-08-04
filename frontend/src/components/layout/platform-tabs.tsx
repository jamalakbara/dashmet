"use client";

import { usePathname } from "next/navigation";
import { SegmentControl, type SegmentItem } from "@/components/ui/segment-control";
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

  const activeSlug = tabs.find((t) => pathname === `/${platform}/${t.slug}`)?.slug ?? "";
  const items: SegmentItem[] = tabs.map((tab) => ({
    value: tab.slug,
    label: tab.label,
    href: withQuery(`/${platform}/${tab.slug}`),
  }));

  return (
    <SegmentControl items={items} value={activeSlug} ariaLabel={`${platform} views`} />
  );
}
