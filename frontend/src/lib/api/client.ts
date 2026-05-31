import axios from "axios";

export function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
  return match ? decodeURIComponent(match[2]) : null;
}

export function setAuthCookie(token: string, expiresIn: number) {
  const expires = new Date(Date.now() + expiresIn * 1000);
  document.cookie = `access_token=${encodeURIComponent(token)}; path=/; expires=${expires.toUTCString()}; SameSite=Lax`;
}

export function clearAuthCookie() {
  document.cookie =
    "access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
}

const apiClient = axios.create({
  baseURL:
    (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") + "/api/v1",
  headers: { "Content-Type": "application/json" },
});

apiClient.interceptors.request.use((config) => {
  const token = getCookie("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      error.response?.status === 401 &&
      typeof window !== "undefined"
    ) {
      clearAuthCookie();
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export default apiClient;
