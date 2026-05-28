import * as React from "react";
import * as RD from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/cn";

export const Dialog = RD.Root;
export const DialogTrigger = RD.Trigger;
export const DialogClose = RD.Close;

export const DialogContent = React.forwardRef<
  React.ComponentRef<typeof RD.Content>,
  React.ComponentPropsWithoutRef<typeof RD.Content> & { hideClose?: boolean }
>(({ className, children, hideClose, ...props }, ref) => (
  <RD.Portal>
    <RD.Overlay className="fixed inset-0 z-50 bg-black/60 dark:bg-black/70 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out fade-in-0 fade-out-0" />
    <RD.Content
      ref={ref}
      className={cn(
        "fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50",
        "w-[min(640px,calc(100vw-32px))] max-h-[calc(100vh-32px)] overflow-y-auto",
        "page-panel shadow-[var(--shadow-pop)]",
        "data-[state=open]:animate-in data-[state=closed]:animate-out fade-in-0 fade-out-0 zoom-in-95",
        className,
      )}
      {...props}
    >
      {children}
      {!hideClose && (
        <RD.Close className="absolute top-3 right-3 rounded-[var(--radius-sm)] p-1.5 text-[var(--color-fg-subtle)] hover:bg-[var(--color-bg-elev-2)] hover:text-[var(--color-fg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-ring)]">
          <X size={16} />
        </RD.Close>
      )}
    </RD.Content>
  </RD.Portal>
));
DialogContent.displayName = "DialogContent";

export const DialogTitle = React.forwardRef<
  React.ComponentRef<typeof RD.Title>,
  React.ComponentPropsWithoutRef<typeof RD.Title>
>(({ className, ...props }, ref) => (
  <RD.Title
    ref={ref}
    className={cn("text-lg font-semibold text-[var(--color-fg)]", className)}
    {...props}
  />
));
DialogTitle.displayName = "DialogTitle";

export const DialogDescription = React.forwardRef<
  React.ComponentRef<typeof RD.Description>,
  React.ComponentPropsWithoutRef<typeof RD.Description>
>(({ className, ...props }, ref) => (
  <RD.Description
    ref={ref}
    className={cn("text-xs text-[var(--color-fg-subtle)] mt-1", className)}
    {...props}
  />
));
DialogDescription.displayName = "DialogDescription";
