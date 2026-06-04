"use client";

import { useQuery } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";
import { syncApi } from "@/lib/api/sync";
import { queryKeys } from "@/lib/query-keys";

type DotColor = "green" | "yellow" | "red" | "gray";

function StatusDot({ color }: { color: DotColor }) {
  return (
    <span
      className={cn("inline-block size-2 rounded-full", {
        "bg-green-500": color === "green",
        "bg-yellow-500 animate-pulse": color === "yellow",
        "bg-red-500": color === "red",
        "bg-muted-foreground": color === "gray",
      })}
    />
  );
}

export function SyncStatusBadge() {
  const [accountId] = useQueryState("account_id");

  const { data } = useQuery({
    queryKey: queryKeys.syncStatus(accountId ?? ""),
    queryFn: async () => {
      const res = await syncApi.status(accountId!);
      return res.data.data;
    },
    enabled: !!accountId,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    staleTime: 60_000,
  });

  if (!accountId || !data) {
    return <StatusDot color="gray" />;
  }

  const jobs = (data.jobs ?? {}) as Record<
    string,
    { status: string; last_run_at: string | null; is_stale: boolean }
  >;

  const hasRunning = Object.values(jobs).some((j) => j.status === "running");
  const lastRun = Object.values(jobs)
    .map((j) => j.last_run_at)
    .filter(Boolean)
    .sort()
    .at(-1);

  const color: DotColor = hasRunning ? "yellow" : lastRun ? "green" : "gray";
  const label = hasRunning
    ? "Syncing…"
    : lastRun
    ? `Updated ${formatDistanceToNow(new Date(lastRun), { addSuffix: true })}`
    : null;

  return (
    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <StatusDot color={color} />
      {label && <span>{label}</span>}
    </div>
  );
}
