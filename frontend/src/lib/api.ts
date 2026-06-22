import axios, {
  type AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from "axios";

import {
  clearAccessToken,
  getAccessToken,
  setAccessToken,
} from "@/lib/auth";
import { API_BASE_URL } from "@/lib/constants";
import type { APIError, TokenResponse } from "@/types/api";

// Axios instance. Credentials are included so the HttpOnly refresh cookie flows.
export const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  timeout: 35_000,
});

// ─── Request interceptor: inject the bearer token ───
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ─── Response interceptor: transparent refresh on 401 ───
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  try {
    const { data } = await axios.post<TokenResponse>(
      `${API_BASE_URL}/api/v1/auth/refresh`,
      {},
      { withCredentials: true },
    );
    setAccessToken(data.access_token, data.expires_in);
    return data.access_token;
  } catch {
    clearAccessToken();
    return null;
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<APIError>) => {
    const original = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };
    const isAuthCall = original?.url?.includes("/auth/");

    if (error.response?.status === 401 && !original._retry && !isAuthCall) {
      original._retry = true;
      refreshPromise = refreshPromise ?? refreshAccessToken();
      const newToken = await refreshPromise;
      refreshPromise = null;
      if (newToken) {
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      }
      // Refresh failed → broadcast a logout event for the app to react.
      window.dispatchEvent(new CustomEvent("cloudpilot:logout"));
    }
    return Promise.reject(error);
  },
);

/** Extract a user-friendly message from an axios error. */
export function apiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as APIError | undefined;
    return data?.error?.message || error.message || "Something went wrong.";
  }
  return "An unexpected error occurred.";
}
