import { initials } from "@/lib/format";
import { cn } from "@/lib/cn";

const palette = ["bg-blue-50 text-blue", "bg-gold-50 text-gold-ink", "bg-ok-50 text-ok", "bg-ai-50 text-ai"];

export function Avatar({ name, className }: { name: string; className?: string }) {
  const i = [...name].reduce((n, c) => n + c.charCodeAt(0), 0) % palette.length;
  return (
    <span
      aria-hidden
      className={cn("grid h-8 w-8 shrink-0 place-items-center rounded-full text-[12px] font-bold", palette[i], className)}
    >
      {initials(name)}
    </span>
  );
}
