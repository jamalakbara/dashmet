"use client";

import { RefreshCw, AlertTriangle } from "lucide-react";
import { useSyncJobs } from "@/hooks/use-sync-jobs";
import { cn } from "@/lib/utils";

/**
 * Empty-state placeholder that consults the section's own sync job before
 * deciding what to say (PRD P-1: never render "not synced yet" as "no data").
 * - job still syncing → "Syncing…" with spinner (data may still arrive)
 * - job completed, zero rows → the genuine empty label
 * - job failed → a failure hint
 */
export function SyncAwareEmpty({
  jobType,
  emptyLabel = "No data for this period",
  syncingLabel = "Syncing… this fills in once the first sync finishes",
  height = 280,
}: {
  jobType: string;
  emptyLabel?: string;
  syncingLabel?: string;
  height?: number;
}) {
  const { jobState } = useSyncJobs();
  const state = jobState(jobType);

  let icon: React.ReactNode = null;
  let label = emptyLabel;
  let tone = "text-muted-foreground";

  if (state === "syncing") {
    icon = <RefreshCw className="size-3.5 animate-spin" />;
    label = syncingLabel;
    tone = "text-amber-600";
  } else if (state === "failed") {
    icon = <AlertTriangle className="size-3.5" />;
    label = "Sync failed — it will retry automatically";
    tone = "text-red-600";
  }

  return (
    <div
      className={cn("flex items-center justify-center gap-2 text-sm", tone)}
      style={{ height }}
    >
      {icon}
      <span>{label}</span>
    </div>
  );
}
