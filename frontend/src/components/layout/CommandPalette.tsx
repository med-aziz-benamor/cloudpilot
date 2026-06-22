import { Command } from "cmdk";
import { AnimatePresence, motion } from "framer-motion";
import {
  Cloud,
  DollarSign,
  LayoutDashboard,
  Lightbulb,
  MessageSquare,
  Play,
  Server,
  Settings2,
  TrendingUp,
} from "lucide-react";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "@/lib/api";
import { useUIStore } from "@/stores/ui.store";

interface Action {
  icon: typeof LayoutDashboard;
  label: string;
  group: string;
  perform: () => void;
}

/** ⌘K command palette — navigation, actions, glass modal with scale animation. */
export function CommandPalette() {
  const open = useUIStore((s) => s.commandPaletteOpen);
  const setOpen = useUIStore((s) => s.setCommandPaletteOpen);
  const addToast = useUIStore((s) => s.addToast);
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!open);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  const go = (path: string) => () => {
    navigate(path);
    setOpen(false);
  };

  const runAgent = (agent: string) => async () => {
    setOpen(false);
    try {
      const { data } = await api.post<{ created: number }>(`/api/v1/admin/agents/${agent}/run`);
      addToast({
        type: "success",
        title: `${agent} ran`,
        description: `${data.created} recommendation(s) created.`,
      });
    } catch {
      addToast({ type: "error", title: "Could not run agent" });
    }
  };

  const actions: Action[] = [
    { icon: LayoutDashboard, label: "Go to Overview", group: "Navigation", perform: go("/") },
    { icon: Server, label: "Go to Resources", group: "Navigation", perform: go("/resources") },
    { icon: DollarSign, label: "Go to Costs", group: "Navigation", perform: go("/costs") },
    { icon: Lightbulb, label: "Go to Recommendations", group: "Navigation", perform: go("/recommendations") },
    { icon: TrendingUp, label: "Go to Forecast", group: "Navigation", perform: go("/forecast") },
    { icon: MessageSquare, label: "Open Cloud Advisor", group: "Navigation", perform: go("/chat") },
    { icon: Settings2, label: "Open Settings", group: "Navigation", perform: go("/settings") },
    { icon: Play, label: "Run CostAgent", group: "Actions", perform: runAgent("cost") },
    { icon: Play, label: "Run RightSizingAgent", group: "Actions", perform: runAgent("rightsizing") },
    { icon: Play, label: "Run ForecastAgent", group: "Actions", perform: runAgent("forecast") },
    { icon: Cloud, label: "Connect a cloud account", group: "Actions", perform: go("/settings/connect") },
  ];

  const groups = [...new Set(actions.map((a) => a.group))];

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[90] flex items-start justify-center bg-neutral-900/40 pt-[15vh] backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={() => setOpen(false)}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -8 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
            onClick={(e) => e.stopPropagation()}
            className="glass-strong w-full max-w-xl overflow-hidden rounded-2xl border border-neutral-200/80 shadow-modal"
          >
            <Command label="Command palette">
              <Command.Input
                autoFocus
                placeholder="Type a command or search…"
                className="w-full border-b border-neutral-200 bg-transparent px-4 py-4 text-body-lg text-neutral-900 outline-none placeholder:text-neutral-400"
              />
              <Command.List className="max-h-80 overflow-y-auto p-2">
                <Command.Empty className="py-8 text-center text-body-sm text-neutral-400">
                  No results found.
                </Command.Empty>
                {groups.map((group) => (
                  <Command.Group
                    key={group}
                    heading={group}
                    className="px-1 pb-1 pt-2 text-label uppercase text-neutral-400 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1"
                  >
                    {actions
                      .filter((a) => a.group === group)
                      .map((a) => (
                        <Command.Item
                          key={a.label}
                          onSelect={a.perform}
                          className="flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-body-sm text-neutral-700 data-[selected=true]:bg-brand-primary/[0.07] data-[selected=true]:text-brand-primary"
                        >
                          <a.icon size={16} />
                          {a.label}
                        </Command.Item>
                      ))}
                  </Command.Group>
                ))}
              </Command.List>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
