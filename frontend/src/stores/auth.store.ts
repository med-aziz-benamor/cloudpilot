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

// A session load in flight. Refresh tokens are single-use and rotate on every
// call, so two concurrent bootstraps do not merely duplicate work: the second one
// presents a token the first has already consumed, gets a 401, and reports the
// user as signed out. React's StrictMode double-invokes effects in development,
// which made that happen on every reload — the app would restore the session and
// then immediately bounce off the requested page onto the Overview. Sharing the
// one promise is the same guard `lib/api.ts` uses around its own refresh.
let sessionLoad: Promise<void> | null = null;

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
    if (sessionLoad) return sessionLoad;

    set({ status: "loading" });
    sessionLoad = (async () => {
      try {
        // Try to mint a fresh access token from the refresh cookie, then load /me.
        const { data } = await api.post<TokenResponse>("/api/v1/auth/refresh", {});
        setAccessToken(data.access_token, data.expires_in);
        const me = await api.get<User>("/api/v1/auth/me");
        set({ user: me.data, status: "authenticated" });
      } catch {
        clearAccessToken();
        set({ user: null, status: "unauthenticated" });
      } finally {
        sessionLoad = null;
      }
    })();
    return sessionLoad;
  },
}));
