import apiClient from "./client";

// Derived connection health, computed by the backend (pure read, no stored
// enum column). Mirrors app/schemas/accounts.py::_derive_health.
export type ConnectionHealth = "healthy" | "expiring" | "expired" | "error";

// Response shape of GET /connections (each item in the `data` array).
// Mirrors app/schemas/accounts.py::ConnectionResponse — keep in sync
// (api-contract-parity rule).
export interface Connection {
  id: string;
  platform: string;
  is_active: boolean;
  scopes: string[] | null;
  token_type: string;
  connected_by: string | null;
  connected_at: string | null;
  last_used_at: string | null;
  token_expires_at: string | null;
  last_error: string | null;
  last_error_at: string | null;
  health: ConnectionHealth;
}

export const connectionsApi = {
  list: () => apiClient.get<{ data: Connection[] }>("/connections"),
  create: (platform: string, access_token: string, token_type = "system_user") =>
    apiClient.post("/connections", { platform, access_token, token_type }),
  delete: (id: string) => apiClient.delete(`/connections/${id}`),
  initiateTikTokOAuth: () => apiClient.get("/connections/tiktok/oauth/initiate"),
  initiateGoogleOAuth: () => apiClient.get("/connections/google/oauth/initiate"),
};
