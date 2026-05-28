import * as React from "react";
import * as RP from "@radix-ui/react-popover";
import { cn } from "@/lib/cn";

export const Popover = RP.Root;
export const PopoverTrigger = RP.Trigger;
export const PopoverAnchor = RP.Anchor;

export const PopoverContent = React.forwardRef<
  React.ComponentRef<typeof RP.Content>,
  React.ComponentPropsWithoutRef<typeof RP.Content>
>(({ className, sideOffset = 8, ...props }, ref) => (
  <RP.Portal>
    <RP.Content
      ref={ref}
      sideOffset={sideOffset}
      className={cn(
        "z-50 page-panel p-1.5 min-w-[220px] shadow-[var(--shadow-pop)]",
        "data-[state=open]:animate-in data-[state=closed]:animate-out fade-in-0 fade-out-0 zoom-in-95",
        className,
      )}
      {...props}
    />
  </RP.Portal>
));
PopoverContent.displayName = "PopoverContent";
