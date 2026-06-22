import { ChevronRight, Cloud } from "lucide-react";

import { SparklineChart } from "@/components/domain/SparklineChart";
import { ProviderBadge } from "@/components/domain/ProviderBadge";
import { cn, formatCurrency } from "@/lib/utils";
import type { CloudProvider, Resource } from "@/types";

interface ResourceRowProps {
  resource: Resource;
  selected?: boolean;
  onClick?: () => void;
}

/** A single resource row in the explorer's middle column. */
export function ResourceTreeRow({ resource, selected, onClick }: ResourceRowProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "group flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors",
        selected ? "bg-brand-primary/5" : "hover:bg-neutral-50",
      )}
    >
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-md",
          selected ? "bg-brand-primary/10 text-brand-primary" : "bg-neutral-100 text-neutral-400",
        )}
      >
        <Cloud size={16} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-mono text-body-sm font-medium text-neutral-900">
          {resource.name}
        </p>
        <p className="truncate text-caption text-neutral-400">
          {resource.service.replace(/_/g, " ")} · {resource.region}
        </p>
      </div>
      <div className="hidden w-16 sm:block">
        <SparklineChart data={fallbackTrend(resource)} height={28} />
      </div>
      <div className="text-right">
        <p className="text-body-sm font-semibold tabular-nums text-neutral-900">
          {formatCurrency(resource.monthly_cost_usd)}
        </p>
        <p className="text-caption text-neutral-400">/mo</p>
      </div>
      <ChevronRight
        size={16}
        className={cn(
          "text-neutral-300 transition-transform",
          selected && "translate-x-0.5 text-brand-primary",
        )}
      />
    </button>
  );
}

/** A small deterministic trend so each row shows a sparkline even before detail load. */
function fallbackTrend(resource: Resource): number[] {
  const base = resource.monthly_cost_usd / 30;
  const seed = resource.id.charCodeAt(0);
  return Array.from({ length: 7 }, (_, i) =>
    Math.max(0, base * (0.85 + ((seed + i) % 7) / 20)),
  );
}

export function ProviderTreeLabel({ provider }: { provider: CloudProvider }) {
  return <ProviderBadge provider={provider} size="sm" />;
}
