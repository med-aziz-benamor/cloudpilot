import { cn } from "@/lib/utils";

/** CloudPilot logo mark — a cloud with a navigation arrow, in the brand gradient. */
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      <defs>
        <linearGradient id="logo-grad" x1="0" y1="0" x2="32" y2="32">
          <stop stopColor="#0D6EFD" />
          <stop offset="1" stopColor="#0DCAF0" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#logo-grad)" />
      <path
        d="M10 21h11a4 4 0 0 0 .4-7.98A6 6 0 0 0 9.2 14.2 3.5 3.5 0 0 0 10 21z"
        fill="#FFFFFF"
        fillOpacity="0.95"
      />
      <path d="M16 9.5l3.2 6.4-3.2-1.6-3.2 1.6L16 9.5z" fill="#0A1628" />
    </svg>
  );
}

export function Logo({ collapsed }: { collapsed?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <LogoMark />
      <span
        className={cn(
          "text-h4 font-bold tracking-tight text-neutral-900 transition-opacity",
          collapsed && "hidden",
        )}
      >
        CloudPilot
      </span>
    </div>
  );
}
