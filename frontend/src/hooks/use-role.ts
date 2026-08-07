"use client";

import { useMe } from "@/hooks/use-me";

/**
 * Current user's role in the active org (from `useMe`). Owner-only settings
 * controls are *disabled* (not hidden) for members — the backend still enforces
 * the boundary with a 403, this is the matching UX so a member isn't presented
 * with actions that will fail.
 */
export function useRole(): string | undefined {
  return useMe().data?.org?.role;
}

export function useIsOwner(): boolean {
  return useRole() === "owner";
}
