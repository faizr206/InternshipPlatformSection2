import { CalendarDays, ChevronDown, RotateCcw, FastForward } from "lucide-react";
import type { Scenario } from "@/api/types";
import { useDemoSettings, useResetScenario, useSetToday } from "@/api/hooks";
import {
  Button,
  DropdownContent,
  DropdownItem,
  DropdownLabel,
  DropdownMenu,
  DropdownRadioGroup,
  DropdownRadioItem,
  DropdownSeparator,
  DropdownTrigger,
  useToast,
} from "@/components/ui";
import { addDays, formatDate } from "@/lib/format";
import { cn } from "@/lib/cn";

const SCENARIOS: { value: Scenario; label: string; hint: string }[] = [
  { value: "fresh", label: "Fresh", hint: "23 Nov · recommendations just ran" },
  { value: "reviewed", label: "Reviewed", hint: "28 Nov · Jira demonstrated, offer accepted" },
  { value: "midpoint", label: "Midpoint", hint: "18 Mar · week 7 of the placement" },
  { value: "end", label: "End", hint: "4 Jun · final review submitted" },
];

export function DemoMenu({ className }: { className?: string }) {
  const { data } = useDemoSettings();
  const reset = useResetScenario();
  const setToday = useSetToday();
  const toast = useToast();
  const today = data?.today;

  return (
    <DropdownMenu>
      <DropdownTrigger asChild>
        <Button className={cn("pr-2.5", className)} aria-label="Demo date and scenario">
          <CalendarDays className="h-4 w-4 text-blue" aria-hidden />
          <span className="tabular-nums">{today ? formatDate(today) : "—"}</span>
          {data && (
            <span className="rounded-md bg-blue-50 px-1.5 text-[11px] leading-5 font-semibold text-blue capitalize max-[480px]:hidden">
              {data.scenario}
            </span>
          )}
          <ChevronDown className="h-4 w-4 text-muted" aria-hidden />
        </Button>
      </DropdownTrigger>
      <DropdownContent className="w-72">
        <DropdownLabel>Scenario</DropdownLabel>
        <DropdownRadioGroup
          value={data?.scenario}
          onValueChange={(v) =>
            reset.mutate(v as Scenario, {
              onSuccess: (s) => toast({ title: `Scenario: ${v}`, description: `Demo data rebuilt · today is ${formatDate(s.today)}` }),
            })
          }
        >
          {SCENARIOS.map((s) => (
            <DropdownRadioItem key={s.value} value={s.value} hint={s.hint}>
              {s.label}
            </DropdownRadioItem>
          ))}
        </DropdownRadioGroup>
        <DropdownSeparator />
        <DropdownLabel>Demo clock</DropdownLabel>
        {[1, 7].map((n) => (
          <DropdownItem
            key={n}
            disabled={!today}
            onSelect={() => today && setToday.mutate(addDays(today, n))}
          >
            <FastForward className="mt-0.5 h-4 w-4 text-muted" aria-hidden />
            Advance {n === 1 ? "1 day" : "1 week"}
          </DropdownItem>
        ))}
        <DropdownItem
          disabled={!data}
          onSelect={() => data && reset.mutate(data.scenario, { onSuccess: () => toast({ title: "Demo reset", description: `Back to the ${data.scenario} scenario.` }) })}
        >
          <RotateCcw className="mt-0.5 h-4 w-4 text-muted" aria-hidden />
          Reset this scenario
        </DropdownItem>
      </DropdownContent>
    </DropdownMenu>
  );
}
