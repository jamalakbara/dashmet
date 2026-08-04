import apiClient from "./client";

export const orgApi = {
  get: () => apiClient.get("/org"),
  update: (name: string) => apiClient.patch("/org", { name }),
  members: () => apiClient.get("/org/members"),
  invite: (email: string, role = "member") =>
    apiClient.post("/org/members/invite", { email, role }),
  acceptInvite: (token: string, name: string, password: string) =>
    apiClient.post("/org/members/accept-invite", { token, name, password }),
  removeMember: (membershipId: string) =>
    apiClient.delete(`/org/members/${membershipId}`),
  memberAccounts: (membershipId: string) =>
    apiClient.get(`/org/members/${membershipId}/accounts`),
  setMemberAccounts: (membershipId: string, accountIds: string[]) =>
    apiClient.put(`/org/members/${membershipId}/accounts`, { account_ids: accountIds }),
};
