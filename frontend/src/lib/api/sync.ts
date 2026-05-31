import apiClient from "./client";

export const syncApi = {
  status: (accountId: string) =>
    apiClient.get("/sync/status", { params: { account_id: accountId } }),
  trigger: (accountId: string) =>
    apiClient.post("/sync/trigger", { account_id: accountId }),
};
