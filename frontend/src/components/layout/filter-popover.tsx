"use client";

import { useEffect, useState } from "react";
import { useQueryState } from "nuqs";
import { SlidersHorizontal, X } from "lucide-react";
import { AnimatedIcon } from "@/components/shared/animated-icon";
import { buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const STATUS_OPTIONS = [
  { value: "all", label: "All statuses" },
  { value: "active", label: "Active" },
  { value: "paused", label: "Paused" },
  { value: "archived", label: "Archived" },
];

/**
 * Shared campaign filter for the dashboard. Writes `status` + `search` URL params
 * that the Overview cards, funnel, trends, and the Table/Ads tabs all read, so a
 * single filter scopes every view (see useOverviewFilter). Search matches campaign
 * name (the entity at the current level for the Table/Ads tabs).
 */
export function FilterPopover() {
  const [status, setStatus] = useQueryState("status", { defaultValue: "all" });
  const [search, setSearch] = useQueryState("search");

  // Debounce the text input → URL so we don't refetch on every keystroke.
  const [searchInput, setSearchInput] = useState(search ?? "");
  useEffect(() => {
    const t = setTimeout(() => setSearch(searchInput || null), 300);
    return () => clearTimeout(t);
  }, [searchInput, setSearch]);
  // Keep the input in sync when the URL changes elsewhere (e.g. Clear).
  useEffect(() => setSearchInput(search ?? ""), [search]);

  const activeCount = (status !== "all" ? 1 : 0) + (search ? 1 : 0);

  function clearAll() {
    setStatus("all");
    setSearch(null);
    setSearchInput("");
  }

  return (
    <Popover>
      <PopoverTrigger
        className={cn(buttonVariants({ variant: "outline", size: "lg" }), "group gap-2")}
      >
        <AnimatedIcon icon={SlidersHorizontal} motionPreset="spin" iconClassName="size-4" />
        Filter
        {activeCount > 0 && (
          <Badge variant="secondary" className="ml-0.5 h-5 min-w-5 justify-center px-1.5">
            {activeCount}
          </Badge>
        )}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold">Filter</p>
          {activeCount > 0 && (
            <button
              onClick={clearAll}
              className="group flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <AnimatedIcon icon={X} motionPreset="wiggle" iconClassName="size-3" />
              Clear
            </button>
          )}
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Campaign name</Label>
          <Input
            placeholder="Search campaigns…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs text-muted-foreground">Status</Label>
          <Select items={STATUS_OPTIONS} value={status} onValueChange={(v) => setStatus(v)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </PopoverContent>
    </Popover>
  );
}
