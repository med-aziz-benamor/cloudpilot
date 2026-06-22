import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-caption font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "bg-neutral-100 text-neutral-700",
        brand: "bg-brand-primary/10 text-brand-primary",
        success: "bg-status-success/10 text-status-success",
        warning: "bg-status-warning/10 text-[#92400E]",
        danger: "bg-status-danger/10 text-[#991B1B]",
        info: "bg-brand-accent/15 text-[#0891B2]",
        outline: "border border-neutral-200 text-neutral-600",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { badgeVariants };
