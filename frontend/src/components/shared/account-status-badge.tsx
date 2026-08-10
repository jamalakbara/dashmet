import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const UNSETTLED_TITLE =
  "Billing or review pending on Meta — data may be incomplete.";

/**
 * Surfaces a Meta ad account's health so a flagged account is never shown
 * without indication of why (P-2/P-4). Only "unsettled" (billing/review
 * pending, not closed) renders a badge; "active" and other states render
 * nothing so the badge disappears when everything is fine (P-2).
 */
export function AccountStatusBadge({
  status,
  className,
}: {
  status?: string;
  className?: string;
}) {
  if (status !== "unsettled") return null;
  return (
    <Badge
      title={UNSETTLED_TITLE}
      className={cn(
        "border-amber-500/30 bg-amber-500/15 text-amber-700 dark:text-amber-400",
        className
      )}
    >
      Unsettled
    </Badge>
  );
}
