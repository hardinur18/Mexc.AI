import * as React from "react";
import { cn } from "@/lib/cn";

export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "glass rounded-[var(--radius-xl)] shadow-[var(--shadow-card)]",
        className,
      )}
      {...props}
    />
  ),
);
Card.displayName = "Card";

export const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("px-4 pt-4 pb-2", className)} {...props} />
  ),
);
CardHeader.displayName = "CardHeader";

export const CardBody = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("px-4 pb-4", className)} {...props} />
  ),
);
CardBody.displayName = "CardBody";

export const StatCard: React.FC<{
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "default" | "up" | "down" | "zero";
  className?: string;
}> = ({ label, value, sub, tone = "default", className }) => {
  const toneCls =
    tone === "up"
      ? "text-[var(--color-success)]"
      : tone === "down"
        ? "text-[var(--color-danger)]"
        : "text-[var(--color-fg)]";
  return (
    <Card className={cn("p-3", className)}>
      <div className="text-[10px] uppercase tracking-wider text-[var(--color-fg-subtle)]">
        {label}
      </div>
      <div className={cn("text-lg font-semibold num mt-1", toneCls)}>{value}</div>
      {sub && (
        <div className="text-[10px] text-[var(--color-fg-subtle)] mt-0.5">{sub}</div>
      )}
    </Card>
  );
};
