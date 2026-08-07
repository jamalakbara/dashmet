import apiClient from "./client";

export const connectionsApi = {
  list: () => apiClient.get("/connections"),
  create: (platform: string, access_token: string, token_type = "system_user") =>
    apiClient.post("/connections", { platform, access_token, token_type }),
  delete: (id: string) => apiClient.delete(`/connections/${id}`),
  initiateTikTokOAuth: () => apiClient.get("/connections/tiktok/oauth/initiate"),
  initiateGoogleOAuth: () => apiClient.get("/connections/google/oauth/initiate"),
};
