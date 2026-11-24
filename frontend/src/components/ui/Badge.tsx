import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export type Tone = "neutral" | "blue" | "gold" | "ok" | "warn" | "bad" | "ai" | "navy";

const tones: Record<Tone, string> = {
  neutral: "bg-bg text-muted border-line",
  blue: "bg-blue-50 text-blue border-blue-100",
  gold: "bg-gold-50 text-gold-ink border-gold/40",
  ok: "bg-ok-50 text-ok border-ok/15",
  warn: "bg-warn-50 text-warn border-warn/15",
  bad: "bg-bad-50 text-bad border-bad/15",
  ai: "bg-ai-50 text-ai border-ai-line",
  navy: "bg-navy text-white border-navy",
};

export function Badge({ tone = "neutral", className, ...rest }: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11.5px] leading-4 font-semibold whitespace-nowrap",
        tones[tone],
        className,
      )}
      {...rest}
    />
  );
}

/** Small chip naming the team module that owns a page or record. */
export function OwnerChip({ owner, className }: { owner: string; className?: string }) {
  return (
    <span
      title={owner === "Core" ? "Shared platform core" : `Owned by team module ${owner}`}
      className={cn(
        "inline-flex items-center gap-1 rounded-md border border-gold/50 bg-gold-50 px-1.5 py-px font-mono text-[11px] font-semibold tracking-tight text-gold-ink",
        className,
      )}
    >
      {owner}
    </span>
  );
}
