import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";

import { cn } from "@/lib/utils";
import { type Toast, useUIStore } from "@/stores/ui.store";

const ICONS = {
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
} as const;

const STYLES = {
  success: "border-status-success/30 text-status-success",
  error: "border-status-danger/30 text-status-danger",
  warning: "border-status-warning/30 text-[#92400E]",
  info: "border-brand-accent/30 text-[#0891B2]",
} as const;

function ToastCard({ toast }: { toast: Toast }) {
  const remove = useUIStore((s) => s.removeToast);
  const Icon = ICONS[toast.type];
  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: 40, scale: 0.95 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 40, scale: 0.95 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        "pointer-events-auto flex w-80 items-start gap-3 rounded-lg border bg-white p-3.5 shadow-elevated",
        STYLES[toast.type],
      )}
    >
      <Icon size={18} className="mt-0.5 shrink-0" />
      <div className="flex-1">
        <p className="text-body-sm font-semibold text-neutral-900">{toast.title}</p>
        {toast.description && (
          <p className="mt-0.5 text-caption text-neutral-500">{toast.description}</p>
        )}
      </div>
      <button
        onClick={() => remove(toast.id)}
        className="text-neutral-400 transition-colors hover:text-neutral-700"
        aria-label="Dismiss"
      >
        <X size={16} />
      </button>
    </motion.div>
  );
}

export function Toaster() {
  const toasts = useUIStore((s) => s.toasts);
  return (
    <div className="pointer-events-none fixed bottom-6 right-6 z-[100] flex flex-col gap-2">
      <AnimatePresence mode="popLayout">
        {toasts.map((t) => (
          <ToastCard key={t.id} toast={t} />
        ))}
      </AnimatePresence>
    </div>
  );
}
