import { motion } from "framer-motion";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { LoginForm } from "@/components/auth/LoginForm";
import { LogoMark } from "@/components/layout/Logo";
import { ProviderBadge } from "@/components/domain/ProviderBadge";
import { useAuthStore } from "@/stores/auth.store";

/** Two-panel login: dark navy brand panel (left) + clean form (right). */
export function LoginPage() {
  const status = useAuthStore((s) => s.status);
  const navigate = useNavigate();

  useEffect(() => {
    if (status === "authenticated") navigate("/");
  }, [status, navigate]);

  return (
    <div className="flex min-h-screen">
      {/* Left brand panel */}
      <div
        className="relative hidden w-2/5 flex-col justify-between overflow-hidden p-12 text-white lg:flex"
        style={{
          background:
            "linear-gradient(135deg, #0A1628 0%, #0D3460 60%, #0D6EFD 100%)",
        }}
      >
        <div className="flex items-center gap-2">
          <LogoMark size={32} />
          <span className="text-h3 font-bold">CloudPilot</span>
        </div>

        <div>
          <motion.h2
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="text-display font-extrabold leading-tight"
          >
            From cloud chaos
            <br />
            to cloud clarity.
          </motion.h2>
          <p className="mt-4 max-w-md text-body-lg text-white/70">
            A unified multi-cloud cockpit for Azure, AWS and GCP — with autonomous
            AI agents and a RAG-powered Cloud Advisor.
          </p>

          <div className="mt-8 flex gap-2">
            {(["azure", "aws", "gcp"] as const).map((p, i) => (
              <motion.div
                key={p}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 + i * 0.1 }}
              >
                <ProviderBadge provider={p} />
              </motion.div>
            ))}
          </div>

          <div className="mt-10 grid grid-cols-3 gap-4">
            {[
              { v: "~30%", l: "avg cost cut" },
              { v: "<5 min", l: "anomaly detection" },
              { v: "3 → 1", l: "dashboards" },
            ].map((s) => (
              <div
                key={s.l}
                className="rounded-xl border border-white/10 bg-white/5 p-3 backdrop-blur-sm"
              >
                <p className="text-h3 font-bold">{s.v}</p>
                <p className="text-caption text-white/60">{s.l}</p>
              </div>
            ))}
          </div>
        </div>

        <p className="text-caption text-white/50">
          Mohammed Aziz Ben Amor — Engineering Intern · ESPRIT ARCTIC · EY Tunisie
        </p>
      </div>

      {/* Right form panel */}
      <div className="flex flex-1 items-center justify-center bg-white p-8">
        <LoginForm />
      </div>
    </div>
  );
}
