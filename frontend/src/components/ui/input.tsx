import { forwardRef } from "react";

import { cn } from "@/lib/utils";

export const Input = forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, type, ...props }, ref) => (
  <input
    ref={ref}
    type={type}
    className={cn(
      "flex h-10 w-full rounded-md border border-neutral-200 bg-white px-3 py-2 text-body text-neutral-900 transition-shadow",
      "placeholder:text-neutral-400",
      "focus-visible:outline-none focus-visible:border-brand-primary focus-visible:shadow-glow-brand",
      "disabled:cursor-not-allowed disabled:opacity-50",
      className,
    )}
    {...props}
  />
));
Input.displayName = "Input";
