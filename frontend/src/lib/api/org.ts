import apiClient from "./client";

export const orgApi = {
  get: () => apiClient.get("/org"),
  update: (name: string) => apiClient.patch("/org", { name }),
  members: () => apiClient.get("/org/members"),
  invite: (email: string, role = "member") =>
    apiClient.post("/org/members/invite", { email, role }),
  removeMember: (userId: string) =>
    apiClient.delete(`/org/members/${userId}`),
};
