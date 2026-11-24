import { Activity, ArrowRight, CalendarClock, CircleCheckBig, ListTodo, Route } from "lucide-react";
import { Link } from "react-router-dom";
import { useDemoSettings, useEvents, useJourney, useStudents, useTodos } from "@/api/hooks";
import type { ActivityEvent, Todo } from "@/api/types";
import { JourneyTracker } from "@/components/JourneyTracker";
import {
  Avatar,
  Badge,
  Card,
  CardHeader,
  EmptyState,
  OwnerChip,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui";
import { roleLabel, useDemo } from "@/context/DemoContext";
import { cn } from "@/lib/cn";
import { formatDate, formatDateTime, formatShort } from "@/lib/format";
import { PERSONAS } from "@/lib/personas";

function Hero() {
  const { role, studentId } = useDemo();
  const { data: settings } = useDemoSettings();
  const { data: students } = useStudents();
  const { data: todos } = useTodos({ role, student_id: studentId });
  const { data: journey } = useJourney(studentId);
  const student = students?.find((s) => s.student_id === studentId);
  const name = role === "student" ? student?.display_name.split(" ")[0] ?? "" : PERSONAS[role].name;
  const high = todos?.filter((t) => t.priority === "high").length ?? 0;
  const done = journey?.stages.filter((s) => s.status === "done").length ?? 0;
  const total = journey?.stages.length ?? 7;

  return (
    <section className="relative overflow-hidden rounded-card bg-navy-2 text-white shadow-card">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(600px_220px_at_100%_0%,rgb(217_186_130/0.28),transparent_60%),radial-gradient(500px_260px_at_0%_120%,rgb(20_70_115/0.9),transparent_70%)]"
      />
      <div className="relative flex flex-col gap-5 p-5 sm:p-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <p className="text-[12.5px] font-medium text-gold">
            Demo as {roleLabel(role)}
            {settings && <> · {formatDate(settings.today)}</>}
          </p>
          <h2 className="mt-1 text-[24px] leading-tight font-semibold tracking-tight text-white sm:text-[26px]">
            Welcome back, {name}
          </h2>
          <p className="mt-1.5 max-w-xl text-[14px] text-nav-ink">
            {todos ? (
              <>
                You have <strong className="text-white">{todos.length} open {todos.length === 1 ? "task" : "tasks"}</strong>
                {high > 0 && (
                  <>
                    , <strong className="text-gold">{high} high priority</strong>
                  </>
                )}
                .{" "}
                {role !== "student" && student && <>Following {student.display_name}'s placement journey.</>}
              </>
            ) : (
              "Loading your tasks…"
            )}
          </p>
        </div>
        <dl className="grid grid-cols-3 gap-2 sm:gap-3">
          {[
            { k: "Journey", v: `${done}/${total}`, sub: "stages done" },
            { k: "Tasks", v: todos?.length ?? "–", sub: "open" },
            { k: "Scenario", v: settings?.scenario ?? "–", sub: "demo state", cap: true },
          ].map((s) => (
            <div key={s.k} className="min-w-0 rounded-xl border border-white/10 bg-white/[0.06] px-3 py-2.5 sm:min-w-[104px]">
              <dt className="text-[11px] font-medium tracking-wide text-nav-muted uppercase">{s.k}</dt>
              <dd className={cn("truncate text-[18px] leading-7 font-semibold text-white", s.cap && "capitalize")}>{s.v}</dd>
              <dd className="text-[11.5px] text-nav-muted">{s.sub}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

function JourneyCard() {
  const { studentId } = useDemo();
  const { data: journey, isLoading } = useJourney(studentId);
  const { data: students } = useStudents();
  const student = students?.find((s) => s.student_id === studentId);
  const done = journey?.stages.filter((s) => s.status === "done").length ?? 0;
  const total = journey?.stages.length ?? 7;
  const pct = Math.round((done / total) * 100);

  return (
    <Card>
      <CardHeader
        icon={<Route className="h-4 w-4" aria-hidden />}
        title={journey ? `${journey.display_name}'s journey` : "Journey"}
        subtitle={
          student ? (
            <>
              <span className="font-mono">{student.student_id}</span> · {student.programme} · profile v{student.profile_version}
            </>
          ) : undefined
        }
        action={
          <div className="hidden w-40 sm:block" aria-label={`${pct}% complete`}>
            <div className="flex justify-between text-[12px] text-muted">
              <span>Progress</span>
              <span className="font-semibold text-ink tabular-nums">{pct}%</span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-line">
              <div className="h-full rounded-full bg-gradient-to-r from-ok to-[#2a9d6a] transition-[width] duration-500" style={{ width: `${pct}%` }} />
            </div>
          </div>
        }
      />
      <div className="px-5 py-5">
        {isLoading || !journey ? (
          <div className="grid gap-4 lg:grid-cols-7">
            {Array.from({ length: 7 }).map((_, i) => (
              <div key={i} className="flex gap-3 lg:flex-col">
                <Skeleton className="h-9 w-9 rounded-full" />
                <div className="flex-1 space-y-1.5">
                  <Skeleton className="h-3 w-12" />
                  <Skeleton className="h-3.5 w-24" />
                  <Skeleton className="h-3 w-20" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <JourneyTracker journey={journey} />
        )}
      </div>
    </Card>
  );
}

const priorityTone = { high: "bad", normal: "blue", low: "neutral" } as const;

function TodoRow({ t }: { t: Todo }) {
  return (
    <li>
      <Link
        to={t.href}
        className="group flex items-start gap-3 px-5 py-3.5 transition-colors hover:bg-bg focus-visible:bg-bg"
      >
        <span
          aria-hidden
          className={cn(
            "mt-1.5 h-2 w-2 shrink-0 rounded-full",
            t.priority === "high" ? "bg-bad" : t.priority === "normal" ? "bg-blue" : "bg-line-2",
          )}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-[14px] font-semibold">{t.title}</span>
            {t.count !== undefined && <Badge tone="gold">{t.count}</Badge>}
          </div>
          <p className="text-[13px] text-muted">{t.detail}</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <OwnerChip owner={t.owner} />
            {t.priority !== "normal" && <Badge tone={priorityTone[t.priority]}>{t.priority === "high" ? "High priority" : "Low"}</Badge>}
            {t.due && (
              <Badge tone="neutral">
                <CalendarClock className="h-3 w-3" aria-hidden />
                Due {formatShort(t.due)}
              </Badge>
            )}
          </div>
        </div>
        <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-muted opacity-0 transition group-hover:translate-x-0.5 group-hover:opacity-100" aria-hidden />
      </Link>
    </li>
  );
}

function TodoCard() {
  const { role, studentId } = useDemo();
  const { data: todos, isLoading } = useTodos({ role, student_id: studentId });
  return (
    <Card className="overflow-hidden">
      <CardHeader
        icon={<ListTodo className="h-4 w-4" aria-hidden />}
        title="To do"
        subtitle={`What needs you as ${roleLabel(role).toLowerCase()}`}
        action={todos && <Badge tone="blue">{todos.length} open</Badge>}
      />
      {isLoading ? (
        <div className="space-y-4 p-5">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : todos && todos.length > 0 ? (
        <ul className="divide-y divide-line">
          {todos.map((t) => (
            <TodoRow key={t.id} t={t} />
          ))}
        </ul>
      ) : (
        <EmptyState icon={<CircleCheckBig className="h-6 w-6" />} title="All caught up">
          Nothing needs you right now.
        </EmptyState>
      )}
    </Card>
  );
}

function EventList({ events }: { events?: ActivityEvent[] }) {
  if (!events) return <div className="space-y-3 p-5">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-10" />)}</div>;
  if (events.length === 0)
    return (
      <EmptyState icon={<Activity className="h-6 w-6" />} title="No activity yet" className="py-10">
        Events appear as people act on records.
      </EmptyState>
    );
  return (
    <ol className="relative px-5 py-4">
      {events.map((e, i) => (
        <li key={e.id} className="relative flex gap-3 pb-4 last:pb-0">
          {i < events.length - 1 && <span aria-hidden className="absolute top-8 bottom-0 left-4 w-px bg-line" />}
          <Avatar name={e.actor} />
          <div className="min-w-0 flex-1 text-[13px]">
            <p className="leading-5">
              <span className="font-semibold">{e.actor}</span> <span className="text-ink/85">{e.action}</span>
            </p>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted">
              <OwnerChip owner={e.owner} />
              {e.ref && <span className="font-mono">{e.ref}</span>}
              <span aria-hidden>·</span>
              <time dateTime={e.at}>{formatDateTime(e.at)}</time>
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function ActivityCard() {
  const { studentId } = useDemo();
  const { data: students } = useStudents();
  const first = students?.find((s) => s.student_id === studentId)?.display_name.split(" ")[0] ?? "Student";
  const all = useEvents();
  const mine = useEvents(studentId);
  return (
    <Card className="overflow-hidden">
      <Tabs defaultValue="all">
        <CardHeader
          icon={<Activity className="h-4 w-4" aria-hidden />}
          title="Activity"
          subtitle="Latest events across modules"
          action={
            <TabsList aria-label="Filter activity">
              <TabsTrigger value="all">All</TabsTrigger>
              <TabsTrigger value="student">{first}</TabsTrigger>
            </TabsList>
          }
        />
        <TabsContent value="all">
          <EventList events={all.data} />
        </TabsContent>
        <TabsContent value="student">
          <EventList events={mine.data} />
        </TabsContent>
      </Tabs>
    </Card>
  );
}

export default function Home() {
  return (
    <div className="space-y-5">
      <Hero />
      <JourneyCard />
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
        <TodoCard />
        <ActivityCard />
      </div>
    </div>
  );
}
