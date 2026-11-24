import * as RS from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface SelectOption {
  value: string;
  label: string;
  hint?: string;
  icon?: ReactNode;
}

interface Props {
  value: string;
  onValueChange: (v: string) => void;
  options: SelectOption[];
  label: string;
  /** Visible label rendered before the value inside the trigger. */
  prefix?: string;
  className?: string;
  id?: string;
}

export function Select({ value, onValueChange, options, label, prefix, className, id }: Props) {
  return (
    <RS.Root value={value} onValueChange={onValueChange}>
      <RS.Trigger
        id={id}
        aria-label={label}
        className={cn(
          "inline-flex h-9 min-w-0 items-center gap-2 rounded-ctl border border-line bg-surface pr-2.5 pl-3 text-left text-sm font-medium text-ink hover:border-line-2 data-[state=open]:border-blue",
          className,
        )}
      >
        {prefix && <span className="text-[12.5px] font-normal text-muted max-sm:hidden">{prefix}</span>}
        <span className="min-w-0 flex-1 truncate">
          <RS.Value />
        </span>
        <RS.Icon>
          <ChevronDown className="h-4 w-4 text-muted" aria-hidden />
        </RS.Icon>
      </RS.Trigger>
      <RS.Portal>
        <RS.Content
          position="popper"
          sideOffset={6}
          className="z-50 max-h-[var(--radix-select-content-available-height)] min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-card border border-line bg-surface p-1 shadow-pop animate-fade-in"
        >
          <RS.Viewport>
            {options.map((o) => (
              <RS.Item
                key={o.value}
                value={o.value}
                className="relative flex cursor-default items-start gap-2.5 rounded-lg py-2 pr-8 pl-2.5 text-sm outline-none select-none data-[highlighted]:bg-blue-50 data-[state=checked]:font-semibold"
              >
                {o.icon && <span className="mt-0.5 shrink-0">{o.icon}</span>}
                <span className="min-w-0">
                  <RS.ItemText>{o.label}</RS.ItemText>
                  {o.hint && <span className="block text-[12px] font-normal text-muted">{o.hint}</span>}
                </span>
                <RS.ItemIndicator className="absolute top-2.5 right-2.5 text-blue">
                  <Check className="h-4 w-4" aria-hidden />
                </RS.ItemIndicator>
              </RS.Item>
            ))}
          </RS.Viewport>
        </RS.Content>
      </RS.Portal>
    </RS.Root>
  );
}
