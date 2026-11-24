import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "gold" | "ai" | "nav";
type Size = "sm" | "md" | "icon";

const variants: Record<Variant, string> = {
  primary: "bg-blue text-white hover:bg-navy-2 shadow-sm",
  secondary: "bg-surface text-ink border border-line hover:border-line-2 hover:bg-bg",
  ghost: "text-ink hover:bg-blue-50",
  gold: "bg-gold text-navy hover:bg-gold-2 shadow-sm",
  ai: "bg-ai text-white hover:bg-[#4a3bc2] shadow-sm",
  nav: "text-nav-ink hover:bg-white/10 hover:text-white",
};
const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px] gap-1.5",
  md: "h-9 px-3.5 text-sm gap-2",
  icon: "h-9 w-9 justify-center",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

/** Button look for non-button elements (e.g. router links). */
export function buttonStyles(variant: Variant = "secondary", size: Size = "md", className?: string) {
  return cn(
    "inline-flex shrink-0 items-center rounded-ctl font-medium whitespace-nowrap transition-colors disabled:opacity-50",
    variants[variant],
    sizes[size],
    className,
  );
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", className, type = "button", ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={buttonStyles(variant, size, className)}
      {...rest}
    />
  );
});
