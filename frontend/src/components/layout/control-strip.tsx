"use client";

import { useMutation } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import { FileDown } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { PlatformTabs } from "@/components/layout/platform-tabs";
import { FilterPopover } from "@/components/layout/filter-popover";
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

  // Export lives on single-account (platform) views only; the combined
  // dashboard (platform === null) has no single-account overview to render.
  const isSingleAccount = platform !== null;

  const exportPptx = useMutation({
    mutationFn: () =>
      insightsApi.exportOverviewPptx({
        account_id: accountId!,
        ...dateRange,
        ...filter,
      }),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "overview.pptx";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    },
    onError: () => toast.error("Couldn't export overview. Try again."),
  });

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-border bg-card px-5 py-3">
      <div className="hidden items-center rounded-lg border border-border p-0.5 sm:flex">
        <PlatformTabs />
      </div>

      <label className="flex cursor-pointer items-center gap-2 whitespace-nowrap text-sm text-muted-foreground">
        <Switch
          checked={compareStr === "true"}
          onCheckedChange={(v) => setCompareStr(v ? "true" : null)}
        />
        Compare prev.
      </label>

      <div className="ml-auto flex items-center gap-3">
        <FilterPopover />

        {isSingleAccount && (
          <Button
            size="lg"
            variant="outline"
            onClick={() => exportPptx.mutate()}
            disabled={!accountId || exportPptx.isPending}
            className="gap-2"
          >
            <FileDown className={cn("size-4", exportPptx.isPending && "animate-pulse")} />
            Export PPTX
          </Button>
        )}
      </div>
    </div>
  );
}
