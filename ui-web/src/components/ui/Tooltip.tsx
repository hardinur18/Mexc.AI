import * as React from "react";
import * as RT from "@radix-ui/react-tooltip";
import { cn } from "@/lib/cn";

export const TooltipProvider = RT.Provider;
export const Tooltip = RT.Root;
export const TooltipTrigger = RT.Trigger;

export const TooltipContent = React.forwardRef<
  React.ComponentRef<typeof RT.Content>,
  React.ComponentPropsWithoutRef<typeof RT.Content>
>(({ className, sideOffset = 6, ...props }, ref) => (
  <RT.Portal>
    <RT.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        "z-50 rounded-[var(--radius-md)] glass shadow-[var(--shadow-pop)] px-3 py-2 text-xs text-[var(--color-fg)] max-w-xs",
        "data-[state=delayed-open]:animate-in data-[state=closed]:animate-out fade-in-0 fade-out-0",
        className,
      )}
      {...props}
    />
  </RT.Portal>
));
TooltipContent.displayName = "TooltipContent";
