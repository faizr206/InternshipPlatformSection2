import { useQuery } from "@tanstack/react-query";
import { BriefcaseBusiness, CalendarClock, CheckCircle2 } from "lucide-react";
import { useState } from "react";
import { p04, type Application } from "@/api/modules";
import { Field, Input, InlineForm, KeyValues, Loading, NativeSelect, Notice, StatusBadge, TextArea, Timeline, fmtDate, useAction } from "@/components/kit";
import { Button, Card, EmptyState, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui";
import { useDemo } from "@/context/DemoContext";

export default function ApplicationsPage() {
  const { role } = useDemo();
  if (role === "employer") return <EmployerQueue />;
  if (role === "coordinator") return <CoordinatorQueue />;
  return <StudentApplications />;
}

function AppCard({ a, children, showStudent }: { a: Application; children?: React.ReactNode; showStudent?: boolean }) {
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[15px] font-semibold">{a.opportunity_title}</h3>
            <span className="font-mono text-[11.5px] text-muted">{a.application_id}</span>
          </div>
          <p className="text-[13px] text-muted">
            {showStudent && <><strong className="text-ink">{a.student_name}</strong> · </>}
            {a.employer_name} · {a.opportunity_id} v{a.opportunity_version} · profile v{a.profile_version}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <StatusBadge status={a.application_status} />
          <span className="text-[11.5px] text-muted">Placement: <StatusBadge status={a.placement_status} /></span>
        </div>
      </div>
      {a.statement && <p className="mt-2 rounded-ctl bg-bg px-3 py-2 text-[13px] text-ink/85">“{a.statement}”</p>}
      {a.interview && (
        <Notice tone="ai">
          <CalendarClock className="mr-1 inline h-3.5 w-3.5" aria-hidden />
          Interview {a.interview.completed_at ? "completed" : "scheduled"}: {new Date(a.interview.starts_at).toLocaleString("en-GB")} · {a.interview.duration_minutes} min · {a.interview.mode} · {a.interview.location}
        </Notice>
      )}
      <details className="mt-3 text-[13px]">
        <summary className="cursor-pointer text-muted">History ({a.history.length})</summary>
        <div className="mt-2">
          <Timeline items={a.history.map((h) => ({
            title: h.action, meta: `${h.actor_name} (${h.actor_role}) · ${new Date(h.created_at).toLocaleString("en-GB")}`,
            body: <>{h.reason && <span>Reason: {h.reason}. </span>}<span className="text-muted">Next: {h.next_action}</span></>,
            tone: ["Declined", "Withdrawn", "Offer declined"].includes(h.action) ? "bad" : h.action.includes("confirmed") || h.action === "Offer accepted" ? "ok" : undefined,
          }))} />
        </div>
      </details>
      {children && <div className="mt-3 border-t border-line pt-3">{children}</div>}
    </Card>
  );
}

function StudentApplications() {
  const { studentId } = useDemo();
  const apps = useQuery({ queryKey: ["p04-mine", studentId], queryFn: () => p04.mine(studentId) });
  const action = useAction();
  if (!apps.data) return <Loading />;
  if (!apps.data.length) return <Card><EmptyState icon={<BriefcaseBusiness className="h-6 w-6" />} title="No applications yet">Apply from Opportunities or from a recommendation in Matching.</EmptyState></Card>;
  return (
    <div className="space-y-3">
      {apps.data.map((a) => (
        <AppCard key={a.application_id} a={a}>
          {a.application_status === "Draft" && <DraftSubmit a={a} />}
          {a.application_status === "Offered" && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[13px]">You have an offer.</span>
              <Button variant="primary" size="sm" disabled={action.pending} onClick={() => action.run(() => p04.respond(a.application_id, "accept"), "Offer accepted: awaiting university confirmation")}>Accept offer</Button>
              <Button size="sm" disabled={action.pending} onClick={() => action.run(() => p04.respond(a.application_id, "decline"), "Offer declined")}>Decline</Button>
            </div>
          )}
          {a.application_status === "Offer accepted" && a.placement_status !== "Confirmed" && (
            <Notice tone="warn">Accepting is not yet a placement. The university coordinator confirms it.</Notice>
          )}
          {["Submitted", "Under review", "Shortlisted", "Interview scheduled", "Interview completed"].includes(a.application_status) && (
            <InlineForm label="Withdraw (optional reason)" button="Withdraw application" variant="secondary" pending={action.pending}
              onSubmit={(t) => action.run(() => p04.withdraw(a.application_id, t), "Application withdrawn; its history is kept")} />
          )}
        </AppCard>
      ))}
    </div>
  );
}

function DraftSubmit({ a }: { a: Application }) {
  const [text, setText] = useState(a.statement ?? "");
  const action = useAction();
  return (
    <div className="space-y-2">
      <Field label="Statement"><TextArea value={text} onChange={(e) => setText(e.target.value)} /></Field>
      <Button variant="primary" size="sm" disabled={action.pending} onClick={() => action.run(() => p04.submitDraft(a.application_id, text), "Application submitted")}>Submit</Button>
    </div>
  );
}

function EmployerQueue() {
  const apps = useQuery({ queryKey: ["p04-all"], queryFn: p04.all });
  if (!apps.data) return <Loading />;
  const list = apps.data.filter((a) => a.application_status !== "Draft");
  const open = list.filter((a) => !["Declined", "Withdrawn", "Offer declined", "Offer accepted"].includes(a.application_status));
  const done = list.filter((a) => !open.includes(a));
  return (
    <Tabs defaultValue="open" className="space-y-4">
      <TabsList><TabsTrigger value="open">To decide ({open.length})</TabsTrigger><TabsTrigger value="done">Closed ({done.length})</TabsTrigger></TabsList>
      <TabsContent value="open" className="space-y-3">
        {open.length === 0 && <Card><EmptyState icon={<BriefcaseBusiness className="h-6 w-6" />} title="No applications waiting" /></Card>}
        {open.map((a) => <AppCard key={a.application_id} a={a} showStudent><EmployerActions a={a} /></AppCard>)}
      </TabsContent>
      <TabsContent value="done" className="space-y-3">{done.map((a) => <AppCard key={a.application_id} a={a} showStudent />)}</TabsContent>
    </Tabs>
  );
}

function EmployerActions({ a }: { a: Application }) {
  const action = useAction();
  const [mode, setMode] = useState<"" | "decline" | "interview">("");
  const decide = (act: string, ok: string, reason?: string) => action.run(() => p04.decide(a.application_id, act, reason), ok, () => setMode(""));
  const s = a.application_status;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {s === "Submitted" && <Button variant="primary" size="sm" onClick={() => decide("Under review", "Moved to under review")}>Start review</Button>}
        {s === "Under review" && <Button variant="primary" size="sm" onClick={() => decide("Shortlisted", "Shortlisted")}>Shortlist</Button>}
        {(s === "Shortlisted" || s === "Interview scheduled") && <Button size="sm" onClick={() => setMode("interview")}>{s === "Interview scheduled" ? "Reschedule interview" : "Schedule interview"}</Button>}
        {s === "Interview scheduled" && <Button size="sm" onClick={() => action.run(() => p04.completeInterview(a.application_id), "Interview completed")}>Mark interview done</Button>}
        {(s === "Shortlisted" || s === "Interview completed") && <Button variant="gold" size="sm" onClick={() => decide("Offer", "Offer made")}>Make offer</Button>}
        {["Under review", "Shortlisted", "Interview scheduled", "Interview completed"].includes(s) && <Button size="sm" className="text-bad" onClick={() => setMode("decline")}>Decline</Button>}
      </div>
      {mode === "decline" && <InlineForm label="Reason (required; the student sees it)" button="Decline application" pending={action.pending} onSubmit={(t) => decide("Declined", "Application declined", t)} />}
      {mode === "interview" && <InterviewForm a={a} onDone={() => setMode("")} />}
    </div>
  );
}

function InterviewForm({ a, onDone }: { a: Application; onDone: () => void }) {
  const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 16);
  const [v, setV] = useState({ when: tomorrow, duration: "30", mode: "online", location: "Teams link (synthetic)" });
  const action = useAction();
  return (
    <form className="grid gap-3 sm:grid-cols-4" onSubmit={(e) => {
      e.preventDefault();
      action.run(() => p04.interview(a.application_id, { starts_at: new Date(v.when).toISOString(), duration_minutes: Number(v.duration), mode: v.mode, location: v.location }), "Interview scheduled", onDone);
    }}>
      <Field label="Starts"><Input type="datetime-local" value={v.when} onChange={(e) => setV({ ...v, when: e.target.value })} /></Field>
      <Field label="Minutes"><Input type="number" min={15} max={240} value={v.duration} onChange={(e) => setV({ ...v, duration: e.target.value })} /></Field>
      <Field label="Mode"><NativeSelect value={v.mode} onChange={(e) => setV({ ...v, mode: e.target.value })}><option value="online">Online</option><option value="in-person">In person</option></NativeSelect></Field>
      <Field label="Link or place"><Input value={v.location} onChange={(e) => setV({ ...v, location: e.target.value })} /></Field>
      <div className="sm:col-span-4"><Button type="submit" variant="primary" size="sm" disabled={action.pending}>Save interview</Button></div>
    </form>
  );
}

function CoordinatorQueue() {
  const apps = useQuery({ queryKey: ["p04-all"], queryFn: p04.all });
  const action = useAction();
  if (!apps.data) return <Loading />;
  const waiting = apps.data.filter((a) => a.application_status === "Offer accepted" && a.placement_status !== "Confirmed");
  const confirmed = apps.data.filter((a) => a.placement_status === "Confirmed");
  return (
    <div className="space-y-5">
      <section className="space-y-3">
        <h2 className="text-[15px] font-semibold">Accepted offers awaiting university confirmation</h2>
        {waiting.length === 0 && <p className="text-[13px] text-muted">None right now.</p>}
        {waiting.map((a) => (
          <AppCard key={a.application_id} a={a} showStudent>
            <Button variant="primary" size="sm" disabled={action.pending}
              onClick={() => action.run(() => p04.confirm(a.application_id), "Placement confirmed and sent to P07 (Co-op placement)")}>
              <CheckCircle2 className="h-4 w-4" />Confirm placement
            </Button>
            <p className="mt-1.5 text-[12px] text-muted">Creates one placement ID and hands it to P07 in the same step. Confirming again creates nothing new.</p>
          </AppCard>
        ))}
      </section>
      <section className="space-y-3">
        <h2 className="text-[15px] font-semibold">Confirmed placements</h2>
        {confirmed.map((a) => (
          <AppCard key={a.application_id} a={a} showStudent>
            <KeyValues items={[["Placement", "Confirmed by the university"], ["Next", "Learning agreement in Co-op placement (P07)"]]} />
          </AppCard>
        ))}
        {confirmed.length === 0 && <p className="text-[13px] text-muted">No confirmed placements yet.</p>}
      </section>
      <p className="text-[12px] text-muted">All applications: {apps.data.length}. Last change {fmtDate(apps.data.at(-1)?.submitted_at)}.</p>
    </div>
  );
}
