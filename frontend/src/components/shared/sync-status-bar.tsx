"use client";

import { useQuery } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import { formatDistanceToNow } from "date-fns";
import { RefreshCw, AlertTriangle, Info } from "lucide-react";
import { syncApi } from "@/lib/api/sync";
import { accountsApi } from "@/lib/api/accounts";
import { queryKeys } from "@/lib/query-keys";
import { DEFAULT_DATE_PRESET } from "@/lib/constants";
import { cn } from "@/lib/utils";

// Which job types matter for each date preset
const RANGE_JOBS: Record<string, string[]> = {
  today:      ["insights_daily"],
  yesterday:  ["insights_daily"],
  last_7d:    ["insights_daily"],
  this_month: ["insights_daily"],
  last_month: ["insights_daily"],
  last_14d:   ["insights_daily", "insights_historical_or_async"],
  last_30d:   ["insights_daily", "insights_historical_or_async"],
  last_90d:   ["insights_daily", "insights_historical_or_async"],
};

const SYNC_ETA: Record<string, string> = {
  insights_daily:      "~2–8 min",
  insights_async:      "~3–15 min",
  insights_historical: "~3–10 min",
  structure:           "~1–3 min",
};

type JobMap = Record<string, { status: string; last_run_at: string | null; is_stale: boolean } | undefined>;

export function SyncStatusBar() {
  const [accountIdParam] = useQueryState("account_id");
  const [datePreset] = useQueryState("date_preset", { defaultValue: DEFAULT_DATE_PRESET });

  const { data: accounts = [] } = useQuery({
    queryKey: queryKeys.accounts(),
    queryFn: async () => {
      const res = await accountsApi.list();
      return res.data.data as { id: string; platform: string }[];
    },
    staleTime: 5 * 60 * 1000,
  });

  // Mirror AccountSwitcher: fall back to first account if URL param not set
  const accountId = accountIdParam ?? accounts[0]?.id ?? null;
  const platformId = accounts.find(a => a.id === accountId)?.platform ?? "meta";

  const { data } = useQuery({
    queryKey: queryKeys.syncStatus(accountId ?? ""),
    queryFn: async () => {
      const res = await syncApi.status(accountId!);
      return res.data.data;
    },
    enabled: !!accountId,
    refetchInterval: 30_000, // 30s — fast enough for progress, low enough to not spam
    refetchIntervalInBackground: false,
    staleTime: 30_000,
  });

  if (!accountId || !data) return null;

  const jobs = data.jobs as JobMap;

  // TikTok last_90d is not covered — show a clear message
  if (platformId === "tiktok" && datePreset === "last_90d") {
    return (
      <div className="flex items-center gap-2 border-b bg-yellow-50 px-6 py-1.5 text-xs text-yellow-700 dark:bg-yellow-950/30 dark:text-yellow-400 dark:border-yellow-900">
        <Info className="size-3 shrink-0" />
        <span>Last 90 days not available for TikTok Ads — use Last 30 days instead</span>
      </div>
    );
  }

  // Resolve "insights_historical_or_async" to the actual job type for this platform
  const rawTypes = RANGE_JOBS[datePreset] ?? ["insights_daily"];
  const resolvedTypes = rawTypes.map(t =>
    t === "insights_historical_or_async"
      ? platformId === "tiktok" ? "insights_historical" : "insights_async"
      : t
  );

  const relevantJobs = resolvedTypes.map(t => ({ type: t, job: jobs[t] }));

  const structureJob = jobs.structure;
  const isStructureSyncing = !structureJob || structureJob.status === "running" || structureJob.status === "pending";
  const hasSyncing = isStructureSyncing || relevantJobs.some(({ job }) => !job || job.status === "pending" || job.status === "running");
  const hasFailed  = relevantJobs.some(({ job }) => job?.status === "failed" || job?.status === "timed_out");
  const hasStale   = !hasSyncing && relevantJobs.some(({ job }) => job?.is_stale);
  const allFresh   = relevantJobs.every(({ job }) => job?.status === "completed" && !job?.is_stale);

  if (allFresh && !hasFailed) return null;

  const syncingJob = relevantJobs.find(({ job }) => !job || job.status === "pending" || job.status === "running");
  // Use the stale job's last_run_at — not the most recent overall — so the time shown matches the warning
  const staleJobs = relevantJobs.filter(({ job }) => job?.is_stale && job?.status === "completed");
  const lastRun = staleJobs.length > 0
    ? staleJobs.map(({ job }) => job?.last_run_at).filter(Boolean).sort().at(-1)
    : relevantJobs.map(({ job }) => job?.last_run_at).filter(Boolean).sort().at(-1);

  const rangeLabel = datePreset.replace(/_/g, " ");

  let icon: React.ReactNode;
  let message: string;
  let variant: "syncing" | "stale" | "error";

  if (hasFailed) {
    icon = <AlertTriangle className="size-3 shrink-0" />;
    message = `Sync failed for ${rangeLabel}. Data may be incomplete.`;
    variant = "error";
  } else if (hasSyncing) {
    const eta = syncingJob ? (SYNC_ETA[syncingJob.type] ?? "a few minutes") : SYNC_ETA.structure;
    if (isStructureSyncing && !structureJob) {
      message = `Syncing your account — first data ready in ${SYNC_ETA.structure}`;
    } else if (isStructureSyncing) {
      message = `Syncing account structure — ready in ${SYNC_ETA.structure}`;
    } else {
      message = `Syncing ${rangeLabel} data — ready in ${eta}`;
    }
    icon = <RefreshCw className="size-3 shrink-0 animate-spin" />;
    variant = "syncing";
  } else {
    const ago = lastRun ? ` · last synced ${formatDistanceToNow(new Date(lastRun), { addSuffix: true })}` : "";
    message = `${rangeLabel} data may be outdated${ago}`;
    icon = <Info className="size-3 shrink-0" />;
    variant = "stale";
  }

  return (
    <div className={cn(
      "flex items-center gap-2 border-b px-6 py-1.5 text-xs",
      variant === "syncing" && "bg-blue-50 text-blue-700 border-blue-100 dark:bg-blue-950/30 dark:text-blue-400 dark:border-blue-900",
      variant === "stale"   && "bg-yellow-50 text-yellow-700 border-yellow-100 dark:bg-yellow-950/30 dark:text-yellow-400 dark:border-yellow-900",
      variant === "error"   && "bg-red-50 text-red-700 border-red-100 dark:bg-red-950/30 dark:text-red-400 dark:border-red-900",
    )}>
      {icon}
      <span>{message}</span>
    </div>
  );
}
