import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-card border border-line bg-surface shadow-card", className)} {...rest} />;
}

export function CardHeader({
  title,
  subtitle,
  action,
  icon,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-start gap-3 border-b border-line px-5 py-4", className)}>
      {icon && <div className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-blue-50 text-blue">{icon}</div>}
      <div className="min-w-0 flex-1">
        <h2 className="text-[15px] leading-6 font-semibold">{title}</h2>
        {subtitle && <p className="text-[13px] text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
