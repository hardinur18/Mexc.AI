import * as React from "react";
import * as RT from "@radix-ui/react-tabs";
import { cn } from "@/lib/cn";

export const Tabs = RT.Root;

export const TabsList = React.forwardRef<
  React.ComponentRef<typeof RT.List>,
  React.ComponentPropsWithoutRef<typeof RT.List>
>(({ className, ...props }, ref) => (
  <RT.List
    ref={ref}
    className={cn(
      "inline-flex items-center gap-1 rounded-[var(--radius-md)] bg-white/5 p-1 ring-1 ring-[var(--color-border)]",
      className,
    )}
    {...props}
  />
));
TabsList.displayName = "TabsList";

export const TabsTrigger = React.forwardRef<
  React.ComponentRef<typeof RT.Trigger>,
  React.ComponentPropsWithoutRef<typeof RT.Trigger>
>(({ className, ...props }, ref) => (
  <RT.Trigger
    ref={ref}
    className={cn(
      "inline-flex items-center justify-center rounded-[var(--radius-sm)] px-3 py-1 text-xs font-medium transition",
      "text-[var(--color-fg-subtle)] hover:text-[var(--color-fg)]",
      "data-[state=active]:bg-[var(--color-accent-soft)] data-[state=active]:text-[var(--color-accent)] data-[state=active]:ring-1 data-[state=active]:ring-[var(--color-accent)]/40",
      className,
    )}
    {...props}
  />
));
TabsTrigger.displayName = "TabsTrigger";

export const TabsContent = React.forwardRef<
  React.ComponentRef<typeof RT.Content>,
  React.ComponentPropsWithoutRef<typeof RT.Content>
>(({ className, ...props }, ref) => (
  <RT.Content ref={ref} className={cn("mt-3", className)} {...props} />
));
TabsContent.displayName = "TabsContent";
