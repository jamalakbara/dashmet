"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, AlertTriangle, AlertCircle, Info } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { AnimatedIcon } from "@/components/shared/animated-icon";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import {
  useNotifications,
  useMarkNotificationRead,
} from "@/hooks/use-notifications";
import type {
  NotificationItem,
  NotificationSeverity,
} from "@/lib/api/notifications";

const SEVERITY_ICON: Record<NotificationSeverity, typeof Info> = {
  info: Info,
  warning: AlertTriangle,
  error: AlertCircle,
};

// Icon tint per severity. Rows stay neutral otherwise so the list reads calm
// when everything is only mildly noteworthy (P-2 spirit).
const SEVERITY_ICON_CLASS: Record<NotificationSeverity, string> = {
  info: "text-muted-foreground",
  warning: "text-amber-600",
  error: "text-red-600",
};

/**
 * Bell + unread badge + inbox popover for the top chrome. The unread count and
 * list come from a polled query (see useNotifications) so the badge refreshes
 * on its own and clears when the backend resolves a notification (P-2). The
 * badge is hidden entirely at 0 — no permanently-lit warning.
 */
export function NotificationCenter() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const { data } = useNotifications();
  const markRead = useMarkNotificationRead();

  const items = data?.items ?? [];
  const unread = data?.unread_count ?? 0;
  const hasUnread = unread > 0;

  function handleClick(n: NotificationItem) {
    markRead.mutate(n.id);
    if (n.deep_link) {
      setOpen(false);
      router.push(n.deep_link);
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        aria-label={hasUnread ? `Notifications (${unread} unread)` : "Notifications"}
        className="group relative flex size-9 items-center justify-center rounded-full text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:ring-2 focus-visible:ring-ring"
      >
        <AnimatedIcon icon={Bell} motionPreset="wiggle" iconClassName="size-[18px]" />
        {hasUnread && (
          <span className="pointer-events-none absolute right-0.5 top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold leading-none text-white tabular-nums ring-2 ring-card">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 gap-0 p-0">
        <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
          <span className="text-sm font-semibold">Notifications</span>
          {hasUnread && (
            <span className="text-xs text-muted-foreground">{unread} unread</span>
          )}
        </div>

        {items.length === 0 ? (
          <div className="flex flex-col items-center gap-1.5 px-3 py-8 text-center">
            <Info className="size-5 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">You&apos;re all caught up</p>
          </div>
        ) : (
          <ul className="max-h-96 divide-y divide-border overflow-y-auto">
            {items.map((n) => {
              const Icon = SEVERITY_ICON[n.severity] ?? Info;
              return (
                <li key={n.id}>
                  <button
                    type="button"
                    onClick={() => handleClick(n)}
                    className="flex w-full items-start gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-accent"
                  >
                    <Icon
                      className={cn(
                        "mt-0.5 size-4 shrink-0",
                        SEVERITY_ICON_CLASS[n.severity] ?? "text-muted-foreground"
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{n.title}</p>
                      <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                        {n.body}
                      </p>
                      <p className="mt-1 text-[11px] text-muted-foreground">
                        {formatDistanceToNow(new Date(n.created_at), {
                          addSuffix: true,
                        })}
                      </p>
                    </div>
                    {n.status === "unread" && (
                      <span className="mt-1.5 size-2 shrink-0 rounded-full bg-red-600" />
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </PopoverContent>
    </Popover>
  );
}
