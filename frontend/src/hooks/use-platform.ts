"use client";

import { usePathname } from "next/navigation";
import type { Platform } from "@/types/enums";

/**
 * Single source of truth for the active platform, derived from the route.
 * `/meta/*` → "meta", `/tiktok/*` → "tiktok", `/google_ads/*` → "google_ads",
 * `/dashboard` (combined) → null.
 */
export function usePlatform(): Platform | null {
  const pathname = usePathname() ?? "";
  if (pathname.startsWith("/meta")) return "meta";
  if (pathname.startsWith("/tiktok")) return "tiktok";
  if (pathname.startsWith("/google_ads")) return "google_ads";
  return null;
}
