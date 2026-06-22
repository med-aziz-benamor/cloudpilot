import { cn } from "@/lib/utils";
import { PROVIDER_META } from "@/lib/constants";
import type { CloudProvider } from "@/types";

interface ProviderBadgeProps {
  provider: CloudProvider;
  size?: "sm" | "md";
  className?: string;
}

/** A colored pill identifying a cloud provider, using official brand colors. */
export function ProviderBadge({ provider, size = "md", className }: ProviderBadgeProps) {
  const meta = PROVIDER_META[provider];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-medium",
        size === "sm" ? "px-2 py-0.5 text-caption" : "px-2.5 py-1 text-body-sm",
        className,
      )}
      style={{ backgroundColor: `${meta.color}14`, color: meta.color }}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: meta.color }}
      />
      {meta.label}
    </span>
  );
}
