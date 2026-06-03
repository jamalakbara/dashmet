import apiClient from "./client";

export const accountsApi = {
  list: () => apiClient.get("/accounts", { params: { per_page: 200 } }),
  get: (id: string) => apiClient.get(`/accounts/${id}`),
  updateConfig: (id: string, config: Record<string, string>) =>
    apiClient.patch(`/accounts/${id}/config`, config),
};
