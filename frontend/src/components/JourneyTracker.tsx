import { AlertTriangle, Check } from "lucide-react";
import type { Journey, JourneyStage, StageStatus } from "@/api/types";
import { OwnerChip } from "@/components/ui";
import { cn } from "@/lib/cn";

const statusText: Record<StageStatus, string> = {
  done: "Done",
  current: "In progress",
  upcoming: "Not started",
  blocked: "Needs attention",
};

function Node({ stage, index }: { stage: JourneyStage; index: number }) {
  const base = "relative z-10 grid h-9 w-9 shrink-0 place-items-center rounded-full text-[13px] font-bold";
  switch (stage.status) {
    case "done":
      return (
        <span className={cn(base, "bg-ok text-white")}>
          <Check className="h-[18px] w-[18px]" strokeWidth={3} aria-hidden />
        </span>
      );
    case "current":
      return (
        <span className={cn(base, "bg-blue text-white ring-4 ring-blue-100")}>
          <span className="absolute inset-0 animate-ping rounded-full bg-blue/25 motion-reduce:hidden" aria-hidden />
          {index + 1}
        </span>
      );
    case "blocked":
      return (
        <span className={cn(base, "bg-bad-50 text-bad ring-1 ring-bad/30")}>
          <AlertTriangle className="h-4 w-4" aria-hidden />
        </span>
      );
    default:
      return <span className={cn(base, "border border-line-2 bg-surface text-muted")}>{index + 1}</span>;
  }
}

/** P01→P07 tracker: horizontal stepper on wide screens, vertical list on narrow ones. */
export function JourneyTracker({ journey }: { journey: Journey }) {
  const stages = journey.stages;
  return (
    <ol aria-label={`${journey.display_name}'s journey`} className="grid gap-0 lg:grid-cols-7 lg:gap-2">
      {stages.map((s, i) => {
        const nextDone = s.status === "done" && stages[i + 1] && stages[i + 1].status !== "upcoming";
        return (
          <li key={s.owner} className="relative flex gap-3 pb-5 last:pb-0 lg:flex-col lg:gap-2.5 lg:pb-0">
            {/* connector */}
            {i < stages.length - 1 && (
              <span
                aria-hidden
                className={cn(
                  "absolute top-9 bottom-0 left-[17px] w-0.5 lg:top-[17px] lg:right-[-8px] lg:bottom-auto lg:left-9 lg:h-0.5 lg:w-auto",
                  s.status === "done" ? (nextDone ? "bg-ok" : "bg-gradient-to-b from-ok to-line lg:bg-gradient-to-r") : "bg-line",
                )}
              />
            )}
            <Node stage={s} index={i} />
            <div className="min-w-0 pt-0.5 lg:pt-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <OwnerChip owner={s.owner} />
                <span
                  className={cn(
                    "text-[11px] font-semibold",
                    s.status === "done" && "text-ok",
                    s.status === "current" && "text-blue",
                    s.status === "blocked" && "text-bad",
                    s.status === "upcoming" && "text-muted",
                  )}
                >
                  {statusText[s.status]}
                </span>
              </div>
              <div className="mt-1 text-[13.5px] leading-5 font-semibold">{s.label}</div>
              <div className="text-[12.5px] leading-[18px] text-muted">{s.detail}</div>
              {s.ref && <div className="mt-0.5 font-mono text-[11px] text-muted">{s.ref}</div>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
