"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const TABS = [
  { href: "/settings/org",         label: "Organization" },
  { href: "/settings/members",     label: "Members" },
  { href: "/settings/connections", label: "Connections" },
  { href: "/settings/accounts",    label: "Accounts" },
];

export function SettingsNav() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-0 border-b">
      {TABS.map(({ href, label }) => (
        <Link
          key={href}
          href={href}
          className={cn(
            "px-4 py-2.5 text-sm font-medium border-b-2 transition-colors",
            pathname === href
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          )}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
