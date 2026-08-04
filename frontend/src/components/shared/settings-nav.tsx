"use client";

import { usePathname } from "next/navigation";
import { SegmentControl, type SegmentItem } from "@/components/ui/segment-control";

const TABS: SegmentItem[] = [
  { value: "/settings/org",         label: "Organization", href: "/settings/org" },
  { value: "/settings/members",     label: "Members",      href: "/settings/members" },
  { value: "/settings/connections", label: "Connections",  href: "/settings/connections" },
  { value: "/settings/accounts",    label: "Accounts",     href: "/settings/accounts" },
];

export function SettingsNav() {
  const pathname = usePathname();
  const value = TABS.find((t) => t.value === pathname)?.value ?? "";
  return <SegmentControl items={TABS} value={value} ariaLabel="Settings sections" />;
}
