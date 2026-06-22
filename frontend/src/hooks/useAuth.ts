import { useEffect } from "react";

import { useAuthStore } from "@/stores/auth.store";

/** Convenience hook over the auth store; also wires the global logout event. */
export function useAuth() {
  const store = useAuthStore();

  useEffect(() => {
    const handler = () => store.logout();
    window.addEventListener("cloudpilot:logout", handler);
    return () => window.removeEventListener("cloudpilot:logout", handler);
  }, [store]);

  return store;
}
