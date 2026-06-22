import { create } from "zustand";

import { api } from "@/lib/api";
import { clearAccessToken, setAccessToken } from "@/lib/auth";
import type { User } from "@/types";
import type { LoginRequest, TokenResponse } from "@/types/api";

interface AuthState {
  user: User | null;
  status: "idle" | "loading" | "authenticated" | "unauthenticated";
  login: (payload: LoginRequest) => Promise<void>;
  logout: () => Promise<void>;
  loadSession: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  status: "idle",

  login: async (payload) => {
    set({ status: "loading" });
    const { data } = await api.post<TokenResponse>("/api/v1/auth/login", payload);
    setAccessToken(data.access_token, data.expires_in);
    const me = await api.get<User>("/api/v1/auth/me");
    set({ user: me.data, status: "authenticated" });
  },

  logout: async () => {
    try {
      await api.post("/api/v1/auth/logout");
    } catch {
      /* best-effort */
    }
    clearAccessToken();
    set({ user: null, status: "unauthenticated" });
  },

  loadSession: async () => {
    set({ status: "loading" });
    try {
      // Try to mint a fresh access token from the refresh cookie, then load /me.
      const { data } = await api.post<TokenResponse>("/api/v1/auth/refresh", {});
      setAccessToken(data.access_token, data.expires_in);
      const me = await api.get<User>("/api/v1/auth/me");
      set({ user: me.data, status: "authenticated" });
    } catch {
      clearAccessToken();
      set({ user: null, status: "unauthenticated" });
    }
  },
}));
