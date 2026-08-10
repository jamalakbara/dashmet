"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { notificationsApi, type NotificationList } from "@/lib/api/notifications";
import { queryKeys } from "@/lib/query-keys";

/** Poll cadence for the notification inbox — worker events are minute-scale, so
 * polling matches the data cadence and is cheaper than a socket (see plan
 * Piece 3). Used by the bell so a resolved notification clears the badge on the
 * next tick (P-2). */
export const NOTIFICATIONS_POLL_MS = 45_000;

/**
 * Reads the unread notification inbox for the bell. Polls on an interval and on
 * window focus so the badge/count stay live without websockets. When the
 * backend resolves a notification, the next poll drops it from `unread` and the
 * badge count falls — clearing automatically (P-2, no permanently-lit badge).
 */
export function useNotifications() {
  return useQuery<NotificationList>({
    queryKey: queryKeys.notifications("unread"),
    queryFn: () => notificationsApi.list("unread"),
    refetchInterval: NOTIFICATIONS_POLL_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    staleTime: NOTIFICATIONS_POLL_MS,
  });
}

/**
 * Marks a notification read. Optimistically drops it from the unread list and
 * decrements the count so the bell reacts immediately; the next poll reconciles
 * with the server.
 */
export function useMarkNotificationRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => notificationsApi.markRead(id),
    onMutate: async (id: string) => {
      const key = queryKeys.notifications("unread");
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<NotificationList>(key);
      if (previous) {
        const removed = previous.items.some((n) => n.id === id);
        qc.setQueryData<NotificationList>(key, {
          items: previous.items.filter((n) => n.id !== id),
          unread_count: Math.max(0, previous.unread_count - (removed ? 1 : 0)),
        });
      }
      return { previous };
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.previous) {
        qc.setQueryData(queryKeys.notifications("unread"), ctx.previous);
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: queryKeys.notifications("unread") });
    },
  });
}
