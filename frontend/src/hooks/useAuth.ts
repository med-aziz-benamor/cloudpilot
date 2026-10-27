import { useEffect } from "react";

import { useAuthStore } from "@/stores/auth.store";

/** Convenience hook over the auth store; also wires the global logout event. */
export function useAuth() {
  const user = useAuthStore((s) => s.user);
  const status = useAuthStore((s) => s.status);
  const login = useAuthStore((s) => s.login);
  const logout = useAuthStore((s) => s.logout);
  const loadSession = useAuthStore((s) => s.loadSession);

  useEffect(() => {
    const handler = () => logout();
    window.addEventListener("cloudpilot:logout", handler);
    return () => window.removeEventListener("cloudpilot:logout", handler);
  }, [logout]);

  return { user, status, login, logout, loadSession };
}
