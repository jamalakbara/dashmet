"use client";

import { useState } from "react";
import { useQueryState } from "nuqs";
import { CalendarDays, ChevronDown, ChevronLeft } from "lucide-react";
import { format, parseISO, subDays } from "date-fns";
import type { DateRange as DayRange } from "react-day-picker";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { DATE_PRESETS, DEFAULT_DATE_PRESET } from "@/lib/constants";
import { cn } from "@/lib/utils";

export function DateRangePicker() {
  const [datePreset, setDatePreset] = useQueryState("date_preset", {
    defaultValue: DEFAULT_DATE_PRESET,
  });
  const [dateStart, setDateStart] = useQueryState("date_start");
  const [dateEnd, setDateEnd] = useQueryState("date_end");

  const [open, setOpen] = useState(false);
  const [view, setView] = useState<"presets" | "custom">("presets");
  const [range, setRange] = useState<DayRange | undefined>(undefined);

  const isCustom = !!(dateStart && dateEnd);
  const today = new Date();
  const cutoff = subDays(today, 30);

  const rangeWarn = !!range?.from && range.from < cutoff;
  const rangeText =
    range?.from && range?.to
      ? `${format(range.from, "MMM d")} – ${format(range.to, "MMM d, yyyy")}`
      : range?.from
      ? `${format(range.from, "MMM d")} – …`
      : "Select a range";

  const customLabel = isCustom
    ? `${format(parseISO(dateStart!), "MMM d")} – ${format(parseISO(dateEnd!), "MMM d")}`
    : "";
  const triggerLabel = isCustom
    ? customLabel
    : DATE_PRESETS.find((p) => p.value === datePreset)?.label ?? "Last 30 days";

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (!next) setView("presets"); // reset for the next open
  }

  function choosePreset(value: string) {
    setDateStart(null);
    setDateEnd(null);
    setDatePreset(value);
    onOpenChange(false);
  }

  function openCustom() {
    setRange(
      isCustom ? { from: parseISO(dateStart!), to: parseISO(dateEnd!) } : undefined
    );
    setView("custom");
  }

  function applyCustom() {
    if (!range?.from || !range?.to) return;
    setDatePreset(null); // backend rejects preset + custom together
    setDateStart(format(range.from, "yyyy-MM-dd"));
    setDateEnd(format(range.to, "yyyy-MM-dd"));
    onOpenChange(false);
  }

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger
        render={
          <Button variant="outline" className="gap-2">
            <CalendarDays className="size-4" />
            {triggerLabel}
            <ChevronDown className="size-3.5 text-muted-foreground" />
          </Button>
        }
      />
      <PopoverContent
        align="start"
        className={cn(view === "custom" ? "w-auto p-0" : "w-52 p-1.5")}
      >
        {view === "presets" ? (
          <div className="flex flex-col gap-0.5">
            {DATE_PRESETS.map((preset) => (
              <button
                key={preset.value}
                onClick={() => choosePreset(preset.value)}
                className={cn(
                  "rounded-md px-2.5 py-1.5 text-left text-sm transition-colors",
                  !isCustom && preset.value === datePreset
                    ? "bg-primary text-primary-foreground"
                    : "hover:bg-accent hover:text-accent-foreground"
                )}
              >
                {preset.label}
              </button>
            ))}
            <div className="my-1 h-px bg-border" />
            <button
              onClick={openCustom}
              className={cn(
                "rounded-md px-2.5 py-1.5 text-left text-sm transition-colors",
                isCustom
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-accent hover:text-accent-foreground"
              )}
            >
              {isCustom ? customLabel : "Custom range…"}
            </button>
          </div>
        ) : (
          <div className="flex w-72 flex-col">
            <button
              onClick={() => setView("presets")}
              className="flex items-center gap-1 border-b px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground"
            >
              <ChevronLeft className="size-3.5" /> Presets
            </button>
            <Calendar
              mode="range"
              numberOfMonths={1}
              defaultMonth={range?.from ?? today}
              selected={range}
              onSelect={(r) => setRange(r)}
              disabled={{ after: today }}
              autoFocus
              className="mx-auto [--cell-size:--spacing(8.5)]"
            />
            {rangeWarn && (
              <p className="border-t px-3 py-2 text-[11px] leading-snug text-amber-600 dark:text-amber-500">
                Range goes past 30 days — breakdowns may be incomplete until sync
                catches up.
              </p>
            )}
            <div className="flex items-center justify-between gap-2 border-t px-3 py-2">
              <span className="truncate text-xs tabular-nums text-muted-foreground">
                {rangeText}
              </span>
              <div className="flex shrink-0 gap-2">
                <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  disabled={!range?.from || !range?.to}
                  onClick={applyCustom}
                >
                  Apply
                </Button>
              </div>
            </div>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}
