"use client";

import { useQueryState } from "nuqs";
import { CalendarDays, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
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

  const currentLabel =
    DATE_PRESETS.find((p) => p.value === datePreset)?.label ?? "Last 30 days";

  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button variant="outline" className="gap-2">
            <CalendarDays className="size-4" />
            {currentLabel}
            <ChevronDown className="size-3.5 text-muted-foreground" />
          </Button>
        }
      />
      <PopoverContent align="start" className="w-52 p-1.5">
        <div className="flex flex-col gap-0.5">
          {DATE_PRESETS.map((preset) => (
            <button
              key={preset.value}
              onClick={() => setDatePreset(preset.value)}
              className={cn(
                "rounded-md px-2.5 py-1.5 text-left text-sm transition-colors",
                preset.value === datePreset
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-accent hover:text-accent-foreground"
              )}
            >
              {preset.label}
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
