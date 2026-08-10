"use client";

import { format, formatDistanceToNow } from "date-fns";
import { AlertTriangle, XCircle } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { Connection, ConnectionHealth } from "@/lib/api/connections";

const HEALTH_STYLE: Record<Exclude<ConnectionHealth, "healthy">, string> = {
  expiring: "border-amber-200 bg-amber-50 text-amber-700",
  expired: "border-red-200 bg-red-50 text-red-700",
  error: "border-red-200 bg-red-50 text-red-700",
};

/**
 * Per-connection health chip driven by the backend-derived `health` field.
 *
 * P-2: renders nothing when health is "healthy" — no permanently-lit badge. It
 * reappears only when the backend reports a degraded state and clears again on
 * the next healthy read.
 */
export function ConnectionHealthBadge({ conn }: { conn: Connection }) {
  if (conn.health === "healthy") return null;

  const expiresRel = conn.token_expires_at
    ? formatDistanceToNow(new Date(conn.token_expires_at), { addSuffix: true })
    : null;
  const expiresAbs = conn.token_expires_at
    ? format(new Date(conn.token_expires_at), "PP")
    : null;

  let icon = <AlertTriangle className="size-3" />;
  let label: string;
  let detail: string | null = null;

  if (conn.health === "expiring") {
    label = expiresRel ? `Token expires ${expiresRel}` : "Token expires soon";
    detail = expiresAbs ? `Access token valid until ${expiresAbs}.` : null;
  } else if (conn.health === "expired") {
    icon = <XCircle className="size-3" />;
    label = "Token expired — reconnect";
    detail = expiresAbs ? `Access token expired on ${expiresAbs}.` : null;
  } else {
    // error
    icon = <XCircle className="size-3" />;
    label = "Connection error";
    detail = conn.last_error ?? "The last sync for this platform failed.";
  }

  const chipClass = cn(
    "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
    HEALTH_STYLE[conn.health]
  );

  if (!detail) {
    return (
      <span className={chipClass}>
        {icon}
        {label}
      </span>
    );
  }

  return (
    <Tooltip>
      <TooltipTrigger render={<span className={cn(chipClass, "cursor-default")} />}>
        {icon}
        {label}
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-left">
        {detail}
        {conn.last_error_at && (
          <span className="mt-0.5 block text-muted-foreground">
            {formatDistanceToNow(new Date(conn.last_error_at), { addSuffix: true })}
          </span>
        )}
      </TooltipContent>
    </Tooltip>
  );
}
