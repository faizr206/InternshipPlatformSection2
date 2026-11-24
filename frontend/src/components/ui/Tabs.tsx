import * as RT from "@radix-ui/react-tabs";
import type { ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/cn";

export const Tabs = RT.Root;
export const TabsContent = RT.Content;

export function TabsList({ className, ...rest }: ComponentPropsWithoutRef<typeof RT.List>) {
  return <RT.List className={cn("inline-flex gap-0.5 rounded-ctl bg-bg p-0.5", className)} {...rest} />;
}

export function TabsTrigger({ className, ...rest }: ComponentPropsWithoutRef<typeof RT.Trigger>) {
  return (
    <RT.Trigger
      className={cn(
        "rounded-lg px-2.5 py-1 text-[12.5px] font-medium text-muted transition-colors hover:text-ink data-[state=active]:bg-surface data-[state=active]:text-ink data-[state=active]:shadow-sm",
        className,
      )}
      {...rest}
    />
  );
}
