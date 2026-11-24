import * as DM from "@radix-ui/react-dropdown-menu";
import { Check } from "lucide-react";
import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { cn } from "@/lib/cn";

export const DropdownMenu = DM.Root;
export const DropdownTrigger = DM.Trigger;
export const DropdownRadioGroup = DM.RadioGroup;

export function DropdownContent({ className, children, ...rest }: ComponentPropsWithoutRef<typeof DM.Content>) {
  return (
    <DM.Portal>
      <DM.Content
        sideOffset={6}
        align="end"
        className={cn("z-50 min-w-60 rounded-card border border-line bg-surface p-1 shadow-pop animate-fade-in", className)}
        {...rest}
      >
        {children}
      </DM.Content>
    </DM.Portal>
  );
}

const itemCls =
  "relative flex cursor-default items-start gap-2.5 rounded-lg px-2.5 py-2 text-sm outline-none select-none data-[highlighted]:bg-blue-50 data-[disabled]:opacity-50";

export function DropdownItem({ className, ...rest }: ComponentPropsWithoutRef<typeof DM.Item>) {
  return <DM.Item className={cn(itemCls, className)} {...rest} />;
}

export function DropdownRadioItem({
  className,
  children,
  hint,
  ...rest
}: ComponentPropsWithoutRef<typeof DM.RadioItem> & { hint?: ReactNode }) {
  return (
    <DM.RadioItem className={cn(itemCls, "pl-8", className)} {...rest}>
      <DM.ItemIndicator className="absolute top-2.5 left-2.5 text-blue">
        <Check className="h-4 w-4" aria-hidden />
      </DM.ItemIndicator>
      <span>
        <span className="block font-medium">{children}</span>
        {hint && <span className="block text-[12px] text-muted">{hint}</span>}
      </span>
    </DM.RadioItem>
  );
}

export function DropdownLabel({ className, ...rest }: ComponentPropsWithoutRef<typeof DM.Label>) {
  return (
    <DM.Label
      className={cn("px-2.5 pt-2 pb-1 text-[10.5px] font-semibold tracking-[0.08em] text-muted uppercase", className)}
      {...rest}
    />
  );
}

export const DropdownSeparator = () => <DM.Separator className="my-1 h-px bg-line" />;
