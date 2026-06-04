"use client";

import { usePathname } from "next/navigation";
import type { Platform } from "@/types/enums";

/**
 * Single source of truth for the active platform, derived from the route.
 * `/meta/*` → "meta", `/tiktok/*` → "tiktok", `/dashboard` (combined) → null.
 */
export function usePlatform(): Platform | null {
  const pathname = usePathname() ?? "";
  if (pathname.startsWith("/meta")) return "meta";
  if (pathname.startsWith("/tiktok")) return "tiktok";
  return null;
}
