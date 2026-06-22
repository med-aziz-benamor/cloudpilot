import { Navigate } from "react-router-dom";

import { LogoMark } from "@/components/layout/Logo";
import { useAuthStore } from "@/stores/auth.store";

/** Gate authenticated routes; shows a branded splash while the session loads. */
export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const status = useAuthStore((s) => s.status);

  if (status === "idle" || status === "loading") {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <div className="animate-pulse">
          <LogoMark size={48} />
        </div>
        <p className="text-body-sm text-neutral-400">Loading CloudPilot…</p>
      </div>
    );
  }

  if (status === "unauthenticated") {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
