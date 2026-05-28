import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 font-medium transition select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-ring)] disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none",
  {
    variants: {
      tone: {
        default:
          "bg-[var(--color-surface)] text-[var(--color-fg)] ring-1 ring-[var(--color-border)] hover:bg-[var(--color-bg-elev-2)]",
        accent:
          "bg-[var(--color-accent-soft)] text-[var(--color-accent)] ring-1 ring-[var(--color-accent)]/40 hover:bg-[var(--color-accent-soft)]/80",
        ghost: "text-[var(--color-fg-muted)] hover:bg-[var(--color-bg-elev-2)]",
        active:
          "bg-[var(--color-accent-soft)] text-[var(--color-accent)] ring-1 ring-[var(--color-accent)]/50",
      },
      size: {
        sm: "h-7 px-2.5 text-[11px] rounded-[var(--radius-sm)]",
        md: "h-8 px-3.5 text-[12px] rounded-[var(--radius-md)]",
        lg: "h-9 px-5 text-[13px] rounded-[var(--radius-md)]",
        icon: "h-8 w-8 rounded-[var(--radius-md)]",
      },
    },
    defaultVariants: { tone: "default", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, tone, size, ...props }, ref) => (
    <button ref={ref} className={cn(buttonVariants({ tone, size }), className)} {...props} />
  ),
);
Button.displayName = "Button";
