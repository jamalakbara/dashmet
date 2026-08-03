"use client";

import { useQuery } from "@tanstack/react-query";
import { syncApi } from "@/lib/api/sync";
import { queryKeys } from "@/lib/query-keys";
import { useAccountId } from "@/hooks/use-account";

/** One per-account sync job's status, as returned by GET /sync/status. */
export type SyncJob = {
  status: string;
  last_run_at: string | null;
  is_stale: boolean;
};

/**
 * Collapsed lifecycle for a single job_type, used by empty states to tell
 * "not synced yet" apart from "genuinely no data" (PRD P-1).
 * - "syncing": no job row yet, or pending/running → data may still arrive.
 * - "done":    a completed job exists → an empty result is really empty.
 * - "failed":  last run failed/timed out.
 */
export type SyncJobState = "syncing" | "done" | "failed" | "unknown";

/**
 * Reads the active account's sync status (shares the SyncStatusBadge query
 * cache) and classifies a given job_type. Backend already exposes per-job-type
 * status in the /sync/status envelope — this just surfaces it per section so an
 * empty chart/table can say "Syncing…" instead of the misleading "No data".
 */
export function useSyncJobs() {
  const accountId = useAccountId();

  const { data } = useQuery({
    queryKey: queryKeys.syncStatus(accountId ?? ""),
    queryFn: async () => {
      const res = await syncApi.status(accountId!);
      return res.data.data as { jobs?: Record<string, SyncJob> };
    },
    enabled: !!accountId,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    staleTime: 30_000,
  });

  const jobs = data?.jobs ?? {};

  return {
    jobState(jobType: string): SyncJobState {
      const job = jobs[jobType];
      if (!job) return "syncing"; // never produced → treat as still syncing, not empty
      if (job.status === "pending" || job.status === "running") return "syncing";
      if (job.status === "failed" || job.status === "timed_out") return "failed";
      if (job.status === "completed") return "done";
      return "unknown";
    },
  };
}
