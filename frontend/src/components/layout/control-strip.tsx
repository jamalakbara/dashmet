"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import { FileDown } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { PlatformTabs } from "@/components/layout/platform-tabs";
import { FilterPopover } from "@/components/layout/filter-popover";
import { DateRangePicker } from "@/components/shared/date-range-picker";
import { useSelectedAccount } from "@/hooks/use-account";
import { useDateRange } from "@/hooks/use-date-range";
import { useOverviewFilter } from "@/hooks/use-overview-filter";
import { usePlatform } from "@/hooks/use-platform";
import { insightsApi } from "@/lib/api/insights";
import { cn } from "@/lib/utils";

/**
 * View-control strip under the top bar: the platform view tabs, the global
 * "compare previous period" toggle, and the Filter / Export affordances. No
 * permanent Sync Data button lives here (P-5) — manual sync is a recovery path
 * surfaced contextually in the freshness chip (SyncStatusBadge).
 */
export function ControlStrip() {
  const { accountId } = useSelectedAccount();
  const platform = usePlatform();
  const dateRange = useDateRange();
  const filter = useOverviewFilter();

  // Global "compare previous period" toggle — drives every Overview section
  // (Trends overlay, card/funnel/table/ad delta pills) via URL state. Lives with
  // the view tabs because it's a view control, not top-level chrome.
  const [compareStr, setCompareStr] = useQueryState("compare");

  // Opt-in AI insight boxes in the exported deck. Default OFF so the standard
  // export never spends tokens (P-5: manual/gated, not automatic).
  const [includeAiSummary, setIncludeAiSummary] = useState(false);

  // Export lives on single-account (platform) views only; the combined
  // dashboard (platform === null) has no single-account overview to render.
  const isSingleAccount = platform !== null;

  const exportPptx = useMutation({
    mutationFn: () =>
      insightsApi.exportOverviewPptx({
        account_id: accountId!,
        ...dateRange,
        ...filter,
        include_ai_summary: includeAiSummary,
      }),
    onSuccess: ({ blob, filename }) => {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    },
    onError: () => toast.error("Couldn't export overview. Try again."),
  });

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-border bg-card px-3 py-3 sm:px-5">
      {/* View tabs scroll horizontally on narrow screens rather than hiding —
          they're the only way to reach a platform's Periodic/Table/… views. */}
      <div className="-mx-3 flex w-full items-center overflow-x-auto px-3 [scrollbar-width:none] sm:mx-0 sm:w-auto sm:px-0">
        <PlatformTabs />
      </div>

      {/* Date range lives here only on mobile — the top bar hosts it from `sm` up. */}
      <div className="sm:hidden">
        <DateRangePicker />
      </div>

      <label className="flex cursor-pointer items-center gap-2 whitespace-nowrap text-sm text-muted-foreground">
        <Switch
          checked={compareStr === "true"}
          onCheckedChange={(v) => setCompareStr(v ? "true" : null)}
        />
        Compare prev.
      </label>

      {/* Below `sm` this is its own full-width block: Filter alone (left), then a
          correlated Export row — the "Include AI summary" toggle sits with the
          Export button because it only affects the exported deck. From `sm` up it
          collapses back to one right-aligned row. */}
      <div className="flex w-full flex-wrap items-center gap-3 sm:ml-auto sm:w-auto sm:flex-nowrap sm:justify-end">
        <FilterPopover />

        {isSingleAccount && (
          <div className="flex w-full items-center gap-3 sm:w-auto">
            <label className="flex cursor-pointer items-center gap-2 whitespace-nowrap text-sm text-muted-foreground">
              <Switch
                checked={includeAiSummary}
                onCheckedChange={setIncludeAiSummary}
              />
              Include AI summary
            </label>

            <Button
              size="lg"
              variant="outline"
              onClick={() => exportPptx.mutate()}
              disabled={!accountId || exportPptx.isPending}
              className="ml-auto gap-2 sm:ml-0"
            >
              <FileDown className={cn("size-4", exportPptx.isPending && "animate-pulse")} />
              Export PPTX
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
