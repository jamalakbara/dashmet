"use client";

import { Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";

/**
 * The TikTok "mode" switch — TikTok Ads · TikTok Shop · Ads × Shop — mirroring
 * the reference dashboard's top-level lens toggle.
 *
 * Only **TikTok Ads** (the GMV Max lens) is backed by real data today: dashmet
 * integrates the TikTok Business/Marketing API (ads) only. The Shop and Ads×Shop
 * lenses need the TikTok Shop Open API (orders, products, LIVE, affiliate,
 * finance, channel attribution) which isn't integrated — so they render as
 * **locked**, never as fabricated numbers (P-1/P-4). The frame is kept so the
 * intended shape is visible and a future Shop integration slots straight in.
 *
 * Presentational only; owns no state. `value` is always "ads" for now.
 */
const MODES = [
  { value: "ads", label: "TikTok Ads", locked: false },
  { value: "shop", label: "TikTok Shop", locked: true },
  { value: "combined", label: "Ads × Shop", locked: true },
] as const;

const LOCKED_HINT = "Needs the TikTok Shop Open API — not integrated yet.";

export function TikTokModeSwitch({ value = "ads" }: { value?: string } = {}) {
  return (
    <div
      className="inline-flex items-center gap-0.5 rounded-lg bg-muted p-0.5"
      role="tablist"
      aria-label="TikTok mode"
    >
      {MODES.map((mode) => {
        const active = mode.value === value && !mode.locked;
        const base =
          "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-sm whitespace-nowrap transition-colors";

        if (mode.locked) {
          return (
            <Tooltip key={mode.value}>
              <TooltipTrigger
                render={
                  <span
                    role="tab"
                    aria-selected={false}
                    aria-disabled
                    className={cn(
                      base,
                      "cursor-not-allowed text-muted-foreground/60",
                    )}
                  />
                }
              >
                <Lock className="size-3.5" />
                {mode.label}
              </TooltipTrigger>
              <TooltipContent>{LOCKED_HINT}</TooltipContent>
            </Tooltip>
          );
        }

        return (
          <span
            key={mode.value}
            role="tab"
            aria-selected={active}
            className={cn(
              base,
              active
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground",
            )}
          >
            {mode.label}
          </span>
        );
      })}
    </div>
  );
}
