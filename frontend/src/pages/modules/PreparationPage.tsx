import { useQuery } from "@tanstack/react-query";
import { BookOpen, Check, ClipboardCheck, GraduationCap, KanbanSquare, Plus } from "lucide-react";
import { useState } from "react";
import { p06, type Board, type ChainStep, type Module, type Submission } from "@/api/modules";
import { Field, Input, InlineForm, Loading, NativeSelect, Notice, Section, StatusBadge, TextArea, Timeline, fmtDate, useAction, useSkillNames } from "@/components/kit";
import { Badge, Button, Card, EmptyState, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui";
import { useDemo } from "@/context/DemoContext";
import { cn } from "@/lib/cn";

export default function PreparationPage() {
  const { role } = useDemo();
  if (role === "reviewer") return <ReviewQueue />;
  if (role === "coordinator" || role === "advisor") return <StaffGaps />;
  return <StudentPlan />;
}

function Chain({ steps }: { steps: ChainStep[] }) {
  return (
    <ol className="grid gap-2 sm:grid-cols-5" aria-label="From gap to demonstrated skill">
      {steps.map((s) => (
        <li key={s.key} className={cn("rounded-ctl border px-3 py-2 text-[12px]",
          s.reached ? "border-ok/30 bg-ok-50" : s.blocked ? "border-warn/30 bg-warn-50" : s.current ? "border-blue bg-blue-50" : "border-line bg-surface")}>
          <div className="flex items-center gap-1.5 font-semibold">
            {s.reached && <Check className="h-3.5 w-3.5 text-ok" aria-hidden />}{s.label}
            <span className="sr-only">{s.reached ? "(done)" : s.blocked ? "(needs action)" : s.current ? "(current step)" : ""}</span>
          </div>
          <div className="text-muted">{s.detail}</div>
        </li>
      ))}
    </ol>
  );
}

function StudentPlan() {
  const { studentId } = useDemo();
  const plan = useQuery({ queryKey: ["p06-plan", studentId], queryFn: () => p06.plan(studentId) });
  const modules = useQuery({ queryKey: ["p06-modules"], queryFn: p06.modules });
  const [moduleId, setModuleId] = useState<string | null>(null);
  if (!plan.data || !modules.data) return <Loading />;
  const current = modules.data.find((m) => m.module_id === (moduleId ?? plan.data.next_step.module_id ?? "MOD-JIRA-101"))!;
  return (
    <div className="space-y-5">
      <Notice tone={plan.data.next_step.kind === "done" ? "ok" : plan.data.next_step.kind === "revise" ? "warn" : "blue"}>
        <strong>Next step:</strong> {plan.data.next_step.text}
      </Notice>
      <Section icon={<GraduationCap className="h-4 w-4" />} title="Preparation plan" subtitle="Gaps arrive from P05 matching (Prepare →) or from the coordinator">
        {plan.data.gaps.length === 0 ? <p className="text-[13px] text-muted">No skill gaps yet. Use “Prepare →” on a gap in Matching.</p> : (
          <div className="space-y-4">
            {plan.data.gaps.map((g) => (
              <div key={g.gap_id} className="space-y-2">
                <div className="flex flex-wrap items-center gap-2 text-[13px]">
                  <strong>{g.skill_name}</strong><span className="font-mono text-[11.5px] text-muted">{g.gap_id}</span>
                  <StatusBadge status={g.status} /><StatusBadge status={g.skill_status} />
                  <span className="text-muted">{g.reason}</span>
                  <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setModuleId(g.module_id)}>Open {g.module_title}</Button>
                </div>
                <Chain steps={g.chain} />
              </div>
            ))}
          </div>
        )}
      </Section>
      <ModulePanel module={current} resourceDone={plan.data.resources[current.module_id]} submission={plan.data.submissions.find((s) => s.module_id === current.module_id)} />
    </div>
  );
}

function ModulePanel({ module: m, resourceDone, submission }: { module: Module; resourceDone?: string; submission?: Submission }) {
  const { studentId } = useDemo();
  const action = useAction();
  if (m.status !== "full")
    return <Section icon={<BookOpen className="h-4 w-4" />} title={m.title} subtitle="Outline · in development"><p className="text-[13px]">{m.outcome}</p><p className="mt-2 text-[13px] text-muted">{m.task}</p></Section>;
  return (
    <Tabs defaultValue="learn" className="space-y-4">
      <TabsList>
        <TabsTrigger value="learn">1 · Learn</TabsTrigger><TabsTrigger value="board">2 · Practise on the board</TabsTrigger><TabsTrigger value="submit">3 · Submit evidence</TabsTrigger>
      </TabsList>
      <TabsContent value="learn">
        <Section icon={<BookOpen className="h-4 w-4" />} title={m.resource?.title ?? m.title} subtitle={`${m.title} · about ${m.resource?.minutes} minutes`}
          action={resourceDone ? <Badge tone="ok">Completed {fmtDate(resourceDone)}</Badge> : undefined}>
          <p className="mb-3 text-[13px]"><strong>Learning outcome:</strong> {m.outcome}</p>
          <div className="grid gap-3 md:grid-cols-2">
            {m.resource?.parts.map((p) => <div key={p.heading} className="rounded-ctl bg-bg p-3 text-[13px]"><div className="font-semibold">{p.heading}</div><p className="mt-1 text-ink/85">{p.text}</p></div>)}
          </div>
          {!resourceDone && <Button className="mt-4" variant="primary" size="sm" disabled={action.pending} onClick={() => action.run(() => p06.completeResource(studentId, m.module_id), "Activity complete. The skill is not demonstrated until it is reviewed.")}>Mark resource complete</Button>}
          <p className="mt-2 text-[12px] text-muted">Finishing the reading is recorded as activity only. It never marks the skill as demonstrated.</p>
        </Section>
      </TabsContent>
      <TabsContent value="board"><JiraBoard task={m.task} /></TabsContent>
      <TabsContent value="submit"><EvidenceForm module={m} submission={submission} /></TabsContent>
    </Tabs>
  );
}

const COLUMNS: { key: Board["items"][number]["status"]; label: string }[] = [{ key: "todo", label: "To do" }, { key: "inprogress", label: "In progress" }, { key: "done", label: "Done" }];

function JiraBoard({ task }: { task: string }) {
  const { studentId } = useDemo();
  const board = useQuery({ queryKey: ["p06-board", studentId], queryFn: () => p06.board(studentId) });
  const action = useAction();
  const [moving, setMoving] = useState<{ key: string; to: string } | null>(null);
  const [summary, setSummary] = useState("");
  if (!board.data) return <Loading />;
  const people = board.data.people ?? ["Layla Hassan", "Omar Saleh", "Priya Nair"];
  return (
    <Section icon={<KanbanSquare className="h-4 w-4" />} title="Practice board (simulated Jira)" subtitle={task}>
      <div className="grid gap-3 md:grid-cols-3">
        {COLUMNS.map((col, ci) => (
          <div key={col.key} className="rounded-card bg-bg p-2.5">
            <div className="mb-2 px-1 text-[12px] font-semibold tracking-wide text-muted uppercase">{col.label}</div>
            <div className="space-y-2">
              {board.data.items.filter((i) => i.status === col.key).map((it) => (
                <div key={it.key} className="rounded-ctl border border-line bg-surface p-2.5 text-[13px] shadow-sm">
                  <div className="font-mono text-[11px] text-muted">{it.key}</div>
                  <div className="font-medium">{it.summary}</div>
                  <NativeSelect aria-label={`Owner of ${it.key}`} className="mt-2 h-8 text-[12.5px]" value={it.assignee}
                    onChange={(e) => action.run(() => p06.assign(studentId, it.key, e.target.value))}>
                    <option value="">Unassigned</option>{people.map((p) => <option key={p}>{p}</option>)}
                  </NativeSelect>
                  <div className="mt-2 flex gap-1.5">
                    {ci > 0 && <Button size="sm" variant="ghost" onClick={() => setMoving({ key: it.key, to: COLUMNS[ci - 1].key })}>← {COLUMNS[ci - 1].label}</Button>}
                    {ci < 2 && <Button size="sm" variant="secondary" onClick={() => setMoving({ key: it.key, to: COLUMNS[ci + 1].key })}>{COLUMNS[ci + 1].label} →</Button>}
                  </div>
                  {moving?.key === it.key && (
                    <div className="mt-2"><InlineForm label="Why does it move? (3+ words)" button="Move" pending={action.pending}
                      onSubmit={(t) => action.run(() => p06.move(studentId, it.key, moving.to, t), `${it.key} moved`, () => setMoving(null))} /></div>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); action.run(() => p06.addItem(studentId, summary), "Item created. Give it an owner.", () => setSummary("")); }}>
        <Input aria-label="New work item summary" value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="New work item, e.g. Check missing gate-time values" />
        <Button type="submit" size="md" disabled={action.pending}><Plus className="h-4 w-4" />Add</Button>
      </form>
      {board.data.log.length > 0 && (
        <details className="mt-3 text-[13px]"><summary className="cursor-pointer text-muted">Move log ({board.data.log.length})</summary>
          <ul className="mt-2 space-y-1">{board.data.log.map((l, i) => <li key={i}><span className="font-mono">{l.key}</span> {l.from} → {l.to}: {l.reason} <span className="text-muted">({fmtDate(l.at)})</span></li>)}</ul>
        </details>
      )}
    </Section>
  );
}

function EvidenceForm({ module: m, submission }: { module: Module; submission?: Submission }) {
  const { studentId } = useDemo();
  const [text, setText] = useState("");
  const action = useAction();
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  const canSubmit = !submission || ["revision", "not_yet"].includes(submission.status);
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Section icon={<ClipboardCheck className="h-4 w-4" />} title="What the reviewer checks" subtitle={m.module_id}>
        <ul className="space-y-1.5 text-[13px]">{m.checklist.map((c) => <li key={c} className="flex gap-2"><Check className="mt-0.5 h-4 w-4 shrink-0 text-ok" aria-hidden />{c}</li>)}</ul>
        {canSubmit ? (
          <div className="mt-4 space-y-2">
            <Field label="Explain your board" hint={`${words} of at least 25 words. A snapshot of your board is attached.`}><TextArea rows={5} value={text} onChange={(e) => setText(e.target.value)} /></Field>
            <Button variant="primary" size="sm" disabled={action.pending} onClick={() => action.run(() => p06.submit(studentId, m.module_id, text), "Sent for review", () => setText(""))}>
              {submission ? `Submit version ${submission.versions.length + 1}` : "Submit for review"}
            </Button>
          </div>
        ) : <Notice tone={submission?.status === "demonstrated" ? "ok" : "blue"}>{submission?.status === "demonstrated" ? "Demonstrated: sent to your profile as reviewed evidence." : "With the reviewer."}</Notice>}
      </Section>
      <Section title="Submission history" subtitle={submission ? `${submission.evidence_id} · ${submission.status_label}` : "Nothing submitted yet"}>
        {submission ? <SubmissionHistory s={submission} /> : <p className="text-[13px] text-muted">Your versions and the reviewer's comments will appear here.</p>}
      </Section>
    </div>
  );
}

function SubmissionHistory({ s }: { s: Submission }) {
  const items = [
    ...s.versions.map((v) => ({ at: v.at, title: `Version ${v.v} submitted`, body: v.explanation, tone: undefined })),
    ...s.reviews.map((r) => ({ at: r.at, title: `${r.by}: ${r.decision.replace("_", " ")}`, body: `${r.comment} (${r.checklist.filter(Boolean).length}/${r.checklist.length} criteria)`, tone: r.decision === "demonstrated" ? "ok" as const : "warn" as const })),
  ].sort((a, b) => a.at.localeCompare(b.at));
  return <Timeline items={items.map((i) => ({ title: i.title, meta: fmtDate(i.at), body: i.body, tone: i.tone }))} />;
}

function ReviewQueue() {
  const q = useQuery({ queryKey: ["p06-queue"], queryFn: p06.queue });
  if (!q.data) return <Loading />;
  if (!q.data.length) return <Card><EmptyState icon={<ClipboardCheck className="h-6 w-6" />} title="No evidence waiting for review" /></Card>;
  return <div className="space-y-4">{q.data.map((s) => <ReviewCard key={s.evidence_id} s={s} />)}</div>;
}

function ReviewCard({ s }: { s: Submission }) {
  const m = s.module!;
  const [checks, setChecks] = useState<boolean[]>(m.checklist.map(() => false));
  const [comment, setComment] = useState("");
  const action = useAction();
  const latest = s.versions.at(-1)!;
  const decide = (d: string) => action.run(() => p06.review(s.evidence_id, d, checks, comment),
    d === "demonstrated" ? "Demonstrated: the profile gets reviewed evidence and matching reruns" : d === "revision" ? "Revision requested" : "Recorded as not yet demonstrated");
  return (
    <Section title={`${s.evidence_id} · ${s.display_name}`} subtitle={`${m.title} · version ${latest.v} · ${fmtDate(latest.at)}`}>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-3 text-[13px]">
          <p className="rounded-ctl bg-bg p-3">{latest.explanation}</p>
          <div>
            <div className="mb-1 text-[11.5px] font-semibold tracking-wide text-muted uppercase">Board snapshot</div>
            <ul className="space-y-0.5">{latest.board.items.map((i) => <li key={i.key}><span className="font-mono text-[11.5px]">{i.key}</span> {i.summary} · <em>{i.assignee || "no owner"}</em> · {i.status}</li>)}</ul>
            <p className="mt-1 text-muted">{latest.board.log.length} status change(s) with reasons</p>
          </div>
          {s.reviews.length > 0 && <SubmissionHistory s={s} />}
        </div>
        <div className="space-y-3">
          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-[12.5px] font-semibold">Checklist (all must be met to record demonstrated)</legend>
            {m.checklist.map((c, i) => (
              <label key={c} className="flex items-start gap-2 text-[13px]">
                <input type="checkbox" className="mt-1" checked={checks[i]} onChange={() => setChecks(checks.map((x, j) => (j === i ? !x : x)))} />{c}
              </label>
            ))}
          </fieldset>
          <Field label="Comment (required for a revision or not yet)"><TextArea value={comment} onChange={(e) => setComment(e.target.value)} /></Field>
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" size="sm" disabled={action.pending} onClick={() => decide("demonstrated")}>Demonstrated</Button>
            <Button size="sm" disabled={action.pending} onClick={() => decide("revision")}>Request revision</Button>
            <Button size="sm" disabled={action.pending} onClick={() => decide("not_yet")}>Not yet</Button>
          </div>
        </div>
      </div>
    </Section>
  );
}

function StaffGaps() {
  const { role, studentId } = useDemo();
  const gaps = useQuery({ queryKey: ["p06-gaps"], queryFn: () => p06.gaps() });
  const { data: names } = useSkillNames();
  const action = useAction();
  const [skill, setSkill] = useState("SK-VIZ");
  return (
    <div className="space-y-5">
      {role === "coordinator" && (
        <Section title="Enter a gap by hand" subtitle={`For the selected student (${studentId}). P06 has modules for Jira, SQL and data visualisation.`}>
          <div className="grid gap-3 sm:grid-cols-[200px_1fr] sm:items-end">
            <Field label="Skill"><NativeSelect value={skill} onChange={(e) => setSkill(e.target.value)}>{["SK-JIRA", "SK-SQL", "SK-VIZ"].map((s) => <option key={s} value={s}>{names?.[s] ?? s}</option>)}</NativeSelect></Field>
            <InlineForm label="Why it matters" placeholder="e.g. Desirable for OP-028; self-declared only" button="Add gap" pending={action.pending}
              onSubmit={(t) => action.run(() => p06.addGap(studentId, skill, t), "Gap added to the student's plan")} />
          </div>
        </Section>
      )}
      <Section title="All skill gaps">
        {!gaps.data ? <Loading /> : gaps.data.length === 0 ? <p className="text-[13px] text-muted">No gaps yet.</p> : (
          <table className="w-full text-left text-[13px]">
            <thead className="text-[11.5px] tracking-wide text-muted uppercase"><tr><th className="py-1.5">Gap</th><th>Student</th><th>Skill</th><th>Source</th><th>Reason</th><th>Status</th></tr></thead>
            <tbody>{gaps.data.map((g) => (
              <tr key={g.gap_id} className="border-t border-line"><td className="py-2 font-mono text-[12px]">{g.gap_id}</td><td>{g.display_name}</td><td>{g.skill_name}</td><td>{g.source}</td><td>{g.reason}</td><td><StatusBadge status={g.status} /></td></tr>
            ))}</tbody>
          </table>
        )}
      </Section>
    </div>
  );
}
