"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import { formatDistanceToNow } from "date-fns";
import { RefreshCw, AlertTriangle, Info, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { AnimatedIcon } from "@/components/shared/animated-icon";
import { syncApi } from "@/lib/api/sync";
import { accountsApi } from "@/lib/api/accounts";
import { queryKeys } from "@/lib/query-keys";
import { DEFAULT_DATE_PRESET } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { useIsOwner } from "@/hooks/use-role";

// Which job types matter for each date preset (mirrors the old SyncStatusBar).
const RANGE_JOBS: Record<string, string[]> = {
  today: ["insights_daily"],
  yesterday: ["insights_daily"],
  last_7d: ["insights_daily"],
  this_month: ["insights_daily"],
  last_month: ["insights_daily"],
  last_14d: ["insights_daily", "insights_historical_or_async"],
  last_30d: ["insights_daily", "insights_historical_or_async"],
  last_90d: ["insights_daily", "insights_historical_or_async"],
};

const SYNC_ETA: Record<string, string> = {
  insights_daily: "~2–8 min",
  insights_async: "~3–15 min",
  insights_historical: "~3–10 min",
  structure: "~1–3 min",
};

type Job = { status: string; last_run_at: string | null; is_stale: boolean } | undefined;
type JobMap = Record<string, Job>;
type Variant = "syncing" | "stale" | "error" | "fresh" | "idle";

const VARIANT_STYLE: Record<Variant, string> = {
  syncing: "border-amber-200 bg-amber-50 text-amber-700",
  stale: "border-amber-200 bg-amber-50 text-amber-700",
  error: "border-red-200 bg-red-50 text-red-700",
  // Fresh is calm, not lit-green (P-2): reuse the neutral idle treatment.
  fresh: "border-border bg-muted/40 text-muted-foreground",
  idle: "border-border bg-muted/40 text-muted-foreground",
};

/**
 * Single, informative sync indicator for the top bar. Replaces the old
 * dot-only badge *and* the full-width freshness banner — resolves the relevant
 * jobs for the active date preset/platform and states range + ETA / staleness /
 * failure inline. Stays present when fresh (shows "Updated Xm ago") so the
 * navbar always reports freshness.
 */
export function SyncStatusBadge() {
  // Manual sync is owner-only (backend POST /sync/trigger → 403 for members).
  // Keep the recovery action visible but locked so members see the freshness
  // state without an action that would fail.
  const isOwner = useIsOwner();
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

  const accountId = accountIdParam ?? accounts[0]?.id ?? null;
  const platformId = accounts.find((a) => a.id === accountId)?.platform ?? "meta";

  const queryClient = useQueryClient();
  const sync = useMutation({
    mutationFn: () => syncApi.trigger(accountId!),
    onSuccess: () => {
      toast.success("Sync started — data will refresh shortly.");
      queryClient.invalidateQueries({ queryKey: queryKeys.syncStatus(accountId ?? "") });
    },
    onError: () => toast.error("Couldn't start sync. Try again."),
  });

  const { data } = useQuery({
    queryKey: queryKeys.syncStatus(accountId ?? ""),
    queryFn: async () => {
      const res = await syncApi.status(accountId!);
      return res.data.data;
    },
    enabled: !!accountId,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    staleTime: 30_000,
  });

  if (!accountId) {
    return <Pill variant="idle" icon={<Info className="size-3" />} label="No account" />;
  }
  if (!data) {
    return <Pill variant="idle" icon={<Info className="size-3" />} label="Last updated —" />;
  }

  const jobs = (data.jobs ?? {}) as JobMap;
  const rangeLabel = datePreset.replace(/_/g, " ");

  // TikTok has no 90-day window.
  if (platformId === "tiktok" && datePreset === "last_90d") {
    return (
      <Pill
        variant="stale"
        icon={<Info className="size-3" />}
        label="90d not available for TikTok — use 30d"
      />
    );
  }

  const rawTypes = RANGE_JOBS[datePreset] ?? ["insights_daily"];
  const resolvedTypes = rawTypes.map((t) =>
    t === "insights_historical_or_async"
      ? platformId === "tiktok"
        ? "insights_historical"
        : "insights_async"
      : t
  );
  const relevant = resolvedTypes.map((t) => ({ type: t, job: jobs[t] }));

  // Secondary data that lives on the page but syncs on its own cadence
  // (breakdowns, hourly). Fresh KPIs with a lagging breakdown is a *partial*
  // state — the badge must not claim "Updated Xm ago" while a section is still
  // filling in (P-2). Creatives are intentionally excluded: they have no
  // sync_job producer yet (BOARD item 4), so including them would light the
  // badge permanently — the exact always-on-warning failure P-2 forbids.
  const breakdownJob = jobs.breakdown;
  const breakdownSyncing =
    !breakdownJob || breakdownJob.status === "pending" || breakdownJob.status === "running";

  const structureJob = jobs.structure;
  const isStructureSyncing =
    !structureJob || structureJob.status === "running" || structureJob.status === "pending";
  const hasSyncing =
    isStructureSyncing ||
    relevant.some(({ job }) => !job || job.status === "pending" || job.status === "running");
  const hasFailed = relevant.some(
    ({ job }) => job?.status === "failed" || job?.status === "timed_out"
  );
  const hasStale = !hasSyncing && relevant.some(({ job }) => job?.is_stale);

  const lastRun = relevant
    .map(({ job }) => job?.last_run_at)
    .filter(Boolean)
    .sort()
    .at(-1);
  const ago = lastRun
    ? formatDistanceToNow(new Date(lastRun), { addSuffix: true })
    : null;

  if (hasFailed) {
    return (
      <Pill
        variant="error"
        icon={
          <AnimatedIcon
            icon={AlertTriangle}
            motionPreset="pop"
            trigger="state"
            appear
            activeVariant="show"
            iconClassName="size-3"
          />
        }
        label={`Sync failed · ${rangeLabel}`}
        onSync={() => sync.mutate()}
        syncing={sync.isPending}
        syncDisabled={!isOwner}
        syncTitle={!isOwner ? "Owner only" : undefined}
      />
    );
  }

  if (hasSyncing) {
    const syncingJob = relevant.find(
      ({ job }) => !job || job.status === "pending" || job.status === "running"
    );
    let label: string;
    if (isStructureSyncing && !structureJob) {
      label = `Syncing account — ready in ${SYNC_ETA.structure}`;
    } else if (isStructureSyncing) {
      label = `Syncing structure — ready in ${SYNC_ETA.structure}`;
    } else {
      const eta = syncingJob ? SYNC_ETA[syncingJob.type] ?? "a few min" : SYNC_ETA.structure;
      label = `Syncing ${rangeLabel} — ready in ${eta}`;
    }
    return (
      <Pill variant="syncing" icon={<RefreshCw className="size-3 animate-spin" />} label={label} />
    );
  }

  // Primary (KPI) data is fresh but a secondary section is still catching up —
  // say so instead of a blanket "Updated Xm ago" that the empty breakdown card
  // would contradict (P-2).
  if (breakdownSyncing) {
    return (
      <Pill
        variant="stale"
        icon={<RefreshCw className="size-3 animate-spin" />}
        label="Partially synced — breakdowns pending"
      />
    );
  }

  if (hasStale) {
    return (
      <Pill
        variant="stale"
        icon={<Info className="size-3" />}
        label={`${rangeLabel} may be outdated${ago ? ` · synced ${ago}` : ""}`}
        onSync={() => sync.mutate()}
        syncing={sync.isPending}
        syncDisabled={!isOwner}
        syncTitle={!isOwner ? "Owner only" : undefined}
      />
    );
  }

  return (
    <Pill
      variant="fresh"
      icon={
        <AnimatedIcon
          icon={CheckCircle2}
          motionPreset="pop"
          trigger="state"
          appear
          activeVariant="show"
          iconClassName="size-3"
        />
      }
      label={ago ? `Updated ${ago}` : "Up to date"}
    />
  );
}

function Pill({
  variant,
  icon,
  label,
  onSync,
  syncing,
  syncDisabled,
  syncTitle,
}: {
  variant: Variant;
  icon: React.ReactNode;
  label: string;
  /** When provided, renders an inline "Sync now" recovery action (P-5). */
  onSync?: () => void;
  syncing?: boolean;
  /** Locks the action (e.g. non-owner) without hiding it. */
  syncDisabled?: boolean;
  syncTitle?: string;
}) {
  return (
    <div
      className={cn(
        "flex min-w-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
        VARIANT_STYLE[variant]
      )}
    >
      <span className="flex shrink-0 items-center">{icon}</span>
      <span className="min-w-0 max-w-[16rem] truncate">{label}</span>
      {onSync && (
        <button
          type="button"
          onClick={onSync}
          disabled={syncing || syncDisabled}
          title={syncTitle}
          className="ml-0.5 inline-flex shrink-0 items-center gap-1 rounded-full border border-current/30 px-1.5 py-0.5 font-semibold transition-opacity hover:opacity-80 disabled:opacity-50"
        >
          <RefreshCw className={cn("size-3", syncing && "animate-spin")} />
          Sync now
        </button>
      )}
    </div>
  );
}
