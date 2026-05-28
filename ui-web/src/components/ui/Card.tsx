import * as React from "react";
import { cn } from "@/lib/cn";

export const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "page-panel transition-shadow duration-150",
        className,
      )}
      {...props}
    />
  ),
);
Card.displayName = "Card";

export const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("px-5 pt-4 pb-2", className)} {...props} />
  ),
);
CardHeader.displayName = "CardHeader";

export const CardBody = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("px-5 pb-4", className)} {...props} />
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
    <Card className={cn("p-4", className)}>
      <div className="text-[11px] uppercase tracking-wider text-[var(--color-fg-subtle)] font-medium">
        {label}
      </div>
      <div className={cn("text-lg font-semibold num mt-1.5", toneCls)}>{value}</div>
      {sub && (
        <div className="text-[11px] text-[var(--color-fg-faint)] mt-1">{sub}</div>
      )}
    </Card>
  );
};
