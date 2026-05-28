import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-[var(--radius-sm)] ring-1 font-semibold text-[11px] leading-tight px-2 py-0.5 whitespace-nowrap",
  {
    variants: {
      tone: {
        neutral:
          "bg-[var(--color-surface)] text-[var(--color-fg-muted)] ring-[var(--color-border-strong)]",
        long: "bg-[var(--color-success-soft)] text-[var(--color-success)] ring-[var(--color-success)]/40",
        short: "bg-[var(--color-danger-soft)] text-[var(--color-danger)] ring-[var(--color-danger)]/40",
        warn: "bg-[var(--color-warning-soft)] text-[var(--color-warning)] ring-[var(--color-warning)]/40",
        danger: "bg-[var(--color-danger-soft)] text-[var(--color-danger)] ring-[var(--color-danger)]/50",
        accent: "bg-[var(--color-accent-soft)] text-[var(--color-accent)] ring-[var(--color-accent)]/40",
      },
      size: {
        sm: "text-[10px] px-1.5 py-0.5",
        md: "text-[11px] px-2 py-0.5",
        lg: "text-xs px-2.5 py-1",
      },
      pulse: {
        true: "",
        false: "",
      },
    },
    compoundVariants: [
      {
        pulse: true,
        tone: "danger",
        class: "[animation:warn-flash_2.2s_ease-in-out_infinite]",
      },
    ],
    defaultVariants: {
      tone: "neutral",
      size: "md",
      pulse: false,
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export const Badge: React.FC<BadgeProps> = ({ className, tone, size, pulse, ...props }) => (
  <span className={cn(badgeVariants({ tone, size, pulse }), className)} {...props} />
);
