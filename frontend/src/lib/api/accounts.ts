import apiClient from "./client";

export interface AccountListParams {
  search?: string;
  platform?: string;
  page?: number;
  per_page?: number;
}

export const accountsApi = {
  // per_page defaults to 200 so existing callers (settings) keep loading all;
  // the searchable picker overrides per_page + passes search/platform.
  list: (params?: AccountListParams) =>
    apiClient.get("/accounts", { params: { per_page: 200, ...params } }),
  get: (id: string) => apiClient.get(`/accounts/${id}`),
  updateConfig: (id: string, config: Record<string, string>) =>
    apiClient.patch(`/accounts/${id}/config`, config),
};
