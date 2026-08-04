"use client";

import { Lock } from "lucide-react";
import { useIsOwner } from "@/hooks/use-role";

/**
 * Shown to members on settings pages: owner-only controls are visible but
 * locked. Silent for owners (P-2 — no permanently-lit state when nothing is
 * wrong).
 */
export function SettingsReadonlyBanner() {
  const isOwner = useIsOwner();
  if (isOwner) return null;

  return (
    <div className="mt-4 flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
      <Lock className="size-4 shrink-0" />
      <span>You have member access. Only owners can change these settings.</span>
    </div>
  );
}
