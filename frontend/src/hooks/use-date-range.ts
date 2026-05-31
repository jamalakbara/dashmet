"use client";

import { useQueryState } from "nuqs";
import { DEFAULT_DATE_PRESET } from "@/lib/constants";
import type { DateRange } from "@/lib/query-keys";

export function useDateRange(): DateRange {
  const [datePreset] = useQueryState("date_preset", { defaultValue: DEFAULT_DATE_PRESET });
  const [dateStart] = useQueryState("date_start");
  const [dateEnd] = useQueryState("date_end");

  if (dateStart && dateEnd) {
    return { date_start: dateStart, date_end: dateEnd };
  }
  return { date_preset: datePreset };
}
