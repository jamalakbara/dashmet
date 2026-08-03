"use client";

import { useQuery } from "@tanstack/react-query";
import { UserMenu } from "@/components/shared/user-menu";
import { authApi } from "@/lib/api/auth";
import { queryKeys } from "@/lib/query-keys";

/**
 * Settings top bar — no account picker / date range / sync here (those are
 * dashboard-only filters). Just the section title and the user control.
 */
export function Header() {
  const { data: me } = useQuery({
    queryKey: queryKeys.me(),
    queryFn: async () => (await authApi.me()).data.data as { name: string; email: string },
    staleTime: 60 * 60 * 1000,
  });

  return (
    <header className="flex h-16 shrink-0 items-center justify-end border-b border-border bg-card px-5">
      <div className="flex items-center gap-2.5">
        <div className="hidden text-right leading-tight sm:block">
          <p className="text-sm font-semibold">{me?.name ?? "—"}</p>
          <p className="max-w-[160px] truncate text-xs text-muted-foreground">
            {me?.email ?? ""}
          </p>
        </div>
        <UserMenu />
      </div>
    </header>
  );
}
