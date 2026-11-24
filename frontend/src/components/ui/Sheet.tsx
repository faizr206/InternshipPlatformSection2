import * as RD from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

interface SheetProps {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  side?: "left" | "right";
  /** Accessible name; drawers render their own visible heading. */
  title: string;
  description?: string;
  className?: string;
  children: ReactNode;
}

/** Side drawer built on Radix Dialog (focus trap, Esc, scroll lock). */
export function Sheet({ open, onOpenChange, side = "right", title, description, className, children }: SheetProps) {
  return (
    <RD.Root open={open} onOpenChange={onOpenChange}>
      <RD.Portal>
        <RD.Overlay className="fixed inset-0 z-40 bg-navy/40 backdrop-blur-[2px] animate-fade-in" />
        <RD.Content
          className={cn(
            "fixed inset-y-0 z-50 flex w-full flex-col shadow-pop outline-none",
            side === "right" ? "right-0 max-w-[420px] animate-slide-in-right bg-surface" : "left-0 max-w-[288px] animate-slide-in-left",
            className,
          )}
        >
          {/* Visible headings live in the drawer body; these keep Radix a11y happy. */}
          <RD.Title className="sr-only">{title}</RD.Title>
          <RD.Description className="sr-only">{description ?? title}</RD.Description>
          {children}
        </RD.Content>
      </RD.Portal>
    </RD.Root>
  );
}

export function SheetClose({ className, label = "Close" }: { className?: string; label?: string }) {
  return (
    <RD.Close
      aria-label={label}
      className={cn("grid h-8 w-8 place-items-center rounded-lg text-muted hover:bg-bg hover:text-ink", className)}
    >
      <X className="h-4 w-4" aria-hidden />
    </RD.Close>
  );
}
