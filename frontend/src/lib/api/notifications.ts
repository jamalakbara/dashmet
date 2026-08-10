import apiClient from "./client";

// Severity drives the visual treatment of a notification row.
export type NotificationSeverity = "info" | "warning" | "error";

// Lifecycle status. Only `unread`/`read` surface in the bell; `resolved`
// notifications (e.g. a token refresh recovered) drop out so the badge clears
// automatically (P-2 — no permanently-lit warning).
export type NotificationStatus = "unread" | "read" | "resolved";

// Mirrors app/schemas/notifications.py::NotificationOut — keep in sync
// (api-contract-parity rule).
export interface NotificationItem {
  id: string;
  type: string;
  severity: NotificationSeverity;
  title: string;
  body: string;
  // Stored column, never inferred from message text (anti-req). When present,
  // clicking the notification navigates here.
  deep_link: string | null;
  dedup_key: string;
  status: NotificationStatus;
  resolved_at: string | null;
  created_at: string;
}

// Unwrapped shape of GET /notifications.
export interface NotificationList {
  items: NotificationItem[];
  unread_count: number;
}

export const notificationsApi = {
  /**
   * GET /notifications — tenant-scoped list + unread count. Read-only, emits
   * nothing server-side. Defaults to the unread inbox for the bell.
   */
  list: async (status?: NotificationStatus): Promise<NotificationList> => {
    const res = await apiClient.get<{ data: NotificationList }>("/notifications", {
      params: status ? { status } : undefined,
    });
    return res.data.data;
  },

  /** POST /notifications/{id}/read — mark read, returns the updated row. */
  markRead: async (id: string): Promise<NotificationItem> => {
    const res = await apiClient.post<{ data: NotificationItem }>(
      `/notifications/${id}/read`
    );
    return res.data.data;
  },
};
