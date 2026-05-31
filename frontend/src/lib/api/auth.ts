import apiClient from "./client";

export interface LoginPayload {
  email: string;
  password: string;
}

export interface SignupPayload {
  name: string;
  email: string;
  password: string;
  org_name: string;
}

export const authApi = {
  login: (payload: LoginPayload) => apiClient.post("/auth/login", payload),
  signup: (payload: SignupPayload) => apiClient.post("/auth/signup", payload),
  verifyEmail: (token: string) =>
    apiClient.post("/auth/verify-email", { token }),
  forgotPassword: (email: string) =>
    apiClient.post("/auth/forgot-password", { email }),
  resetPassword: (token: string, new_password: string) =>
    apiClient.post("/auth/reset-password", { token, new_password }),
  logout: () => apiClient.post("/auth/logout"),
  me: () => apiClient.get("/auth/me"),
};
