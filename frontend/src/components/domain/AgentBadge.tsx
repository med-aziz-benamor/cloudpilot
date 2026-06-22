import { Bot, Lightbulb, TrendingUp, Zap } from "lucide-react";

import { AGENT_META } from "@/lib/constants";
import { cn } from "@/lib/utils";
import type { AgentType } from "@/types";

const ICONS = {
  cost: Zap,
  rightsizing: Lightbulb,
  forecast: TrendingUp,
  architect: Bot,
} as const;

interface AgentBadgeProps {
  agent: AgentType;
  className?: string;
}

/** Identifies which AI agent produced a recommendation, with a consistent color. */
export function AgentBadge({ agent, className }: AgentBadgeProps) {
  const meta = AGENT_META[agent];
  const Icon = ICONS[agent];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-caption font-semibold",
        className,
      )}
      style={{ backgroundColor: meta.bg, color: meta.color }}
    >
      <Icon size={13} strokeWidth={2} />
      {meta.label}
    </span>
  );
}
