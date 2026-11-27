import { useQuery } from "@tanstack/react-query";
import { ClipboardList, FileSignature, Flag, NotebookPen, Target, Trophy } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { p07, type LogEntry, type P07Record } from "@/api/modules";
import type { Role } from "@/api/types";
import { Field, Input, InlineForm, KeyValues, Loading, NativeSelect, Notice, Section, StatusBadge, TextArea, Timeline, fmtDate, useAction } from "@/components/kit";
import { Badge, Button, Card, EmptyState, Tabs, TabsContent, TabsList, TabsTrigger, buttonStyles } from "@/components/ui";
import { useDemo } from "@/context/DemoContext";

export default function PlacementPage() {
  const { role, studentId } = useDemo();
  const rec = useQuery({ queryKey: ["p07", studentId, role], queryFn: () => p07.record(studentId, role) });
  if (!rec.data) return <Loading />;
  const r = rec.data;
  if (!r.placement) {
    return (
      <Card>
        <EmptyState icon={<ClipboardList className="h-6 w-6" />} title={`${r.display_name} has no confirmed placement yet`}
          action={<Link to="/applications" className={buttonStyles("secondary")}>Go to applications</Link>}>
          P07 starts when the university confirms a placement in P04. An accepted offer alone is not a placement.
        </EmptyState>
      </Card>
    );
  }
  return (
    <Tabs defaultValue="overview" className="space-y-4">
      <TabsList className="flex-wrap">
        <TabsTrigger value="overview">Placement</TabsTrigger>
        <TabsTrigger value="agreement">Learning agreement</TabsTrigger>
        <TabsTrigger value="logbook">Logbook{r.counts?.logs_awaiting_supervisor ? ` (${r.counts.logs_awaiting_supervisor})` : ""}</TabsTrigger>
        <TabsTrigger value="progress">Progress & actions{r.counts?.overdue_actions ? ` (${r.counts.overdue_actions} overdue)` : ""}</TabsTrigger>
        <TabsTrigger value="final">Final review</TabsTrigger>
      </TabsList>
      <TabsContent value="overview"><Overview r={r} role={role} /></TabsContent>
      <TabsContent value="agreement"><Agreement r={r} role={role} /></TabsContent>
      <TabsContent value="logbook"><Logbook r={r} role={role} /></TabsContent>
      <TabsContent value="progress"><Progress r={r} role={role} /></TabsContent>
      <TabsContent value="final"><Final r={r} role={role} /></TabsContent>
    </Tabs>
  );
}

function Overview({ r, role }: { r: P07Record; role: Role }) {
  const p = r.placement!;
  const action = useAction();
  const [advisor, setAdvisor] = useState(r.advisors[0]?.name ?? "");
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
      <Section icon={<ClipboardList className="h-4 w-4" />} title={`${p.role} · ${p.employer_name}`} subtitle={`${p.placement_id} · confirmed by ${p.confirmed_by ?? "the university"} · received ${fmtDate(p.received_at)}`}
        action={<Badge tone="ok">University confirmed</Badge>}>
        <KeyValues items={[
          ["Student", r.display_name], ["Location", p.location],
          ["Period 1", `${fmtDate(p.period_start)} – ${fmtDate(p.period_end)}`], ["Demo date", fmtDate(r.today)],
          ["Workplace supervisor", p.supervisor_name], ["Supervisor contact", role === "student" ? <span className="text-muted">Shared with staff only</span> : p.supervisor_contact],
          ["Academic advisor", p.academic_advisor ?? <span className="text-warn">Not assigned yet</span>], ["From", `${p.application_id} · ${p.opportunity_id}`],
        ]} />
        {!p.academic_advisor && role === "coordinator" && (
          <div className="mt-4 flex flex-wrap items-end gap-2">
            <Field label="Assign academic advisor"><NativeSelect value={advisor} onChange={(e) => setAdvisor(e.target.value)}>{r.advisors.map((a) => <option key={a.id}>{a.name}</option>)}</NativeSelect></Field>
            <Button variant="primary" disabled={action.pending} onClick={() => action.run(() => p07.assignAdvisor(p.placement_id, advisor), `${advisor} assigned`)}>Assign</Button>
          </div>
        )}
      </Section>
      <Section title="Preparation readiness (from P06)" subtitle="Reviewed evidence can support outcomes">
        {r.readiness.demonstrated.length === 0 ? <p className="text-[13px] text-muted">No demonstrated skills yet.</p> : (
          <ul className="space-y-1 text-[13px]">{r.readiness.demonstrated.map((d) => <li key={d.evidence_id}><Badge tone="ok">{d.skill_id}</Badge> {d.evidence_id} · reviewed {fmtDate(d.review_date)}</li>)}</ul>
        )}
        {r.readiness.in_progress.length > 0 && <p className="mt-2 text-[13px] text-muted">Still preparing: {r.readiness.in_progress.join(", ")}</p>}
      </Section>
    </div>
  );
}

function Agreement({ r, role }: { r: P07Record; role: Role }) {
  const a = r.agreement!;
  const p = r.placement!;
  const action = useAction();
  const [text, setText] = useState("");
  const [los, setLos] = useState<string[]>([]);
  const agreed = a.status === "agreed";
  const outcomeName = (id: string) => r.outcomes.find((o) => o.outcome_id === id)?.name ?? id;
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
      <Section icon={<Target className="h-4 w-4" />} title="Three goals for Period 1" subtitle="Each goal maps to at least one programme outcome" action={<StatusBadge status={a.status} />}>
        {a.goals.length === 0 && <p className="text-[13px] text-muted">No goals yet. The student drafts three; the supervisor and advisor then agree them.</p>}
        <ul className="space-y-3">
          {a.goals.map((g) => (
            <li key={g.goal_id} className="rounded-ctl border border-line p-3 text-[13px]">
              <div className="flex items-start justify-between gap-2"><div><span className="font-mono text-[11.5px] text-muted">{g.goal_id}</span> <strong>{g.text}</strong></div>
                {!agreed && role === "student" && <Button size="sm" variant="ghost" onClick={() => action.run(() => p07.removeGoal(p.placement_id, g.goal_id), "Goal removed")}>Remove</Button>}</div>
              <div className="mt-1.5 flex flex-wrap gap-1">{g.outcomes.map((o) => <Badge key={o} tone="blue">{o} · {outcomeName(o)}</Badge>)}</div>
            </li>
          ))}
        </ul>
        {!agreed && role === "student" && a.goals.length < 3 && (
          <div className="mt-4 space-y-2">
            <Field label={`Goal ${a.goals.length + 1} of 3`}><Input value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. Build a weekly on-time-performance dashboard the team uses" /></Field>
            <div className="flex flex-wrap gap-2">{r.outcomes.map((o) => (
              <label key={o.outcome_id} className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-[12.5px]">
                <input type="checkbox" checked={los.includes(o.outcome_id)} onChange={() => setLos(los.includes(o.outcome_id) ? los.filter((x) => x !== o.outcome_id) : [...los, o.outcome_id])} />{o.outcome_id} {o.name}
              </label>))}</div>
            <Button variant="primary" size="sm" disabled={action.pending} onClick={() => action.run(() => p07.addGoal(p.placement_id, text, los), "Goal added", () => { setText(""); setLos([]); })}>Add goal</Button>
          </div>
        )}
      </Section>
      <Section icon={<FileSignature className="h-4 w-4" />} title="Sign-off" subtitle="Locks when all three have agreed">
        <ul className="space-y-2 text-[13px]">
          {(["student", "supervisor", "advisor"] as const).map((who) => (
            <li key={who} className="flex items-center justify-between gap-2">
              <span className="capitalize">{who === "student" ? r.display_name : who === "supervisor" ? p.supervisor_name ?? "Supervisor" : p.academic_advisor ?? "Academic advisor"}<span className="block text-[11.5px] text-muted">{who}</span></span>
              {a.signoffs[who] ? <Badge tone="ok">Agreed {fmtDate(a.signoffs[who])}</Badge>
                : who === "advisor" && !p.academic_advisor ? <Badge tone="warn">Advisor not assigned</Badge>
                : role === who && a.goals.length === 3 ? <Button size="sm" variant="primary" disabled={action.pending} onClick={() => action.run(() => p07.sign(p.placement_id, role), "Agreement recorded")}>Agree</Button>
                : <Badge tone="neutral">Waiting</Badge>}
            </li>
          ))}
        </ul>
        {a.goals.length < 3 && <p className="mt-2 text-[12px] text-muted">Sign-off opens when three goals are drafted.</p>}
      </Section>
    </div>
  );
}

function Logbook({ r, role }: { r: P07Record; role: Role }) {
  const p = r.placement!;
  const action = useAction();
  const [v, setV] = useState({ text: "", goal_id: r.agreement?.goals[0]?.goal_id ?? "", evidence: "", newEvidence: "" });
  return (
    <div className="space-y-4">
      {role === "student" && (
        <Section icon={<NotebookPen className="h-4 w-4" />} title="New log entry" subtitle={`Dated ${fmtDate(r.today)} (demo date)`}>
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="What did you do and learn?" className="md:col-span-2" hint="At least eight words"><TextArea value={v.text} onChange={(e) => setV({ ...v, text: e.target.value })} /></Field>
            <Field label="Goal it supports"><NativeSelect value={v.goal_id} onChange={(e) => setV({ ...v, goal_id: e.target.value })}><option value="">None</option>{r.agreement?.goals.map((g) => <option key={g.goal_id} value={g.goal_id}>{g.goal_id} · {g.text}</option>)}</NativeSelect></Field>
            <Field label="Link existing evidence"><NativeSelect value={v.evidence} onChange={(e) => setV({ ...v, evidence: e.target.value })}><option value="">None</option>{r.evidence?.map((e) => <option key={e.evidence_id} value={e.evidence_id}>{e.evidence_id} · {e.title}</option>)}</NativeSelect></Field>
            <Field label="…or add new evidence (title)" className="md:col-span-2"><Input value={v.newEvidence} onChange={(e) => setV({ ...v, newEvidence: e.target.value })} placeholder="e.g. Dashboard v1 screenshot and notes" /></Field>
          </div>
          <Button className="mt-3" variant="primary" size="sm" disabled={action.pending} onClick={() => action.run(() => p07.addLog(p.placement_id, {
            text: v.text, goal_id: v.goal_id || undefined, evidence_ids: v.evidence ? [v.evidence] : [], new_evidence_title: v.newEvidence || undefined,
          }), "Log entry sent to the supervisor", () => setV({ ...v, text: "", newEvidence: "" }))}>Submit entry</Button>
        </Section>
      )}
      {(r.logs ?? []).length === 0 && <Card><EmptyState icon={<NotebookPen className="h-6 w-6" />} title="No log entries yet" /></Card>}
      {[...(r.logs ?? [])].reverse().map((l) => <LogCard key={l.log_id} l={l} role={role} />)}
    </div>
  );
}

function LogCard({ l, role }: { l: LogEntry; role: Role }) {
  const action = useAction();
  const [revising, setRevising] = useState(false);
  const [text, setText] = useState(l.versions.at(-1)!.text);
  const items: { at: string; title: string; body: React.ReactNode; tone?: "warn" | "ok" }[] = [
    ...l.versions.map((x) => ({ at: x.at, title: `Version ${x.v}`, body: <>{x.text}{x.evidence.length > 0 && <span className="text-muted"> · evidence {x.evidence.join(", ")}</span>}</> })),
    ...l.feedback.map((f) => ({ at: f.at, title: `${f.by}: ${f.type === "request" ? "asked for more detail" : "note"}`, body: <>{f.text}</>, tone: f.type === "request" ? "warn" as const : "ok" as const })),
  ].sort((a, b) => a.at.localeCompare(b.at));
  return (
    <Section title={<>{l.log_id} · week {l.week}{l.period === "P2" && <Badge tone="neutral" className="ml-2">Period 2 · not counted for Period 1</Badge>}</>}
      subtitle={`${fmtDate(l.date)}${l.goal_id ? ` · supports ${l.goal_id}` : ""}`} action={<StatusBadge status={l.status} />}>
      <Timeline items={items.map((i) => ({ title: i.title, meta: fmtDate(i.at), body: i.body, tone: i.tone }))} />
      {role === "supervisor" && ["submitted", "revised"].includes(l.status) && (
        <div className="mt-3 grid gap-3 md:grid-cols-[auto_1fr] md:items-end">
          <Button variant="primary" size="sm" disabled={action.pending} onClick={() => action.run(() => p07.acknowledge(l.log_id), `${l.log_id} acknowledged`)}>Acknowledge</Button>
          <InlineForm label="Or ask for more detail (4+ words)" button="Request detail" variant="secondary" pending={action.pending}
            onSubmit={(t) => action.run(() => p07.requestDetail(l.log_id, t), "Feedback request sent")} />
        </div>
      )}
      {role === "student" && ["submitted", "feedback"].includes(l.status) && (revising ? (
        <div className="mt-3 space-y-2">
          <Field label="Revised entry (must change the text)"><TextArea value={text} onChange={(e) => setText(e.target.value)} /></Field>
          <Button variant="primary" size="sm" disabled={action.pending} onClick={() => action.run(() => p07.revise(l.log_id, text), "Revision sent", () => setRevising(false))}>Send revision</Button>
        </div>
      ) : <Button className="mt-3" size="sm" variant={l.status === "feedback" ? "primary" : "secondary"} onClick={() => setRevising(true)}>Revise</Button>)}
    </Section>
  );
}

function Progress({ r, role }: { r: P07Record; role: Role }) {
  const p = r.placement!;
  const action = useAction();
  const [judging, setJudging] = useState<string | null>(null);
  const [level, setLevel] = useState("developing");
  const [ev, setEv] = useState<string[]>([]);
  const [act, setAct] = useState({ text: "", owner: "student", due: r.today });
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
      <div className="space-y-5">
        <Section icon={<Target className="h-4 w-4" />} title="Outcome judgements" subtitle="Each judgement is linked to evidence, or shown as missing evidence">
          <ul className="space-y-3">
            {r.judgements?.map((j) => (
              <li key={j.outcome_id} className="rounded-ctl border border-line p-3 text-[13px]">
                <div className="flex flex-wrap items-center gap-2"><strong>{j.outcome_id}</strong> {j.name} <StatusBadge status={j.level} />
                  {j.evidence_missing && <Badge tone="warn">Evidence missing</Badge>}
                  {role === "advisor" && <Button size="sm" variant="ghost" className="ml-auto" onClick={() => { setJudging(j.outcome_id); setLevel(j.level === "none" ? "developing" : j.level); setEv(j.evidence); }}>Record judgement</Button>}
                </div>
                {j.evidence.length > 0 && <p className="mt-1 text-muted">Evidence: {j.evidence.join(", ")} · {j.by}, {fmtDate(j.at)}</p>}
                {judging === j.outcome_id && (
                  <div className="mt-2 space-y-2">
                    <NativeSelect aria-label="Level" value={level} onChange={(e) => setLevel(e.target.value)}><option value="none">Not yet evidenced</option><option value="developing">Developing</option><option value="achieved">Achieved</option></NativeSelect>
                    <div className="flex flex-wrap gap-2">{r.evidence?.map((e) => (
                      <label key={e.evidence_id} className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-[12px]">
                        <input type="checkbox" checked={ev.includes(e.evidence_id)} onChange={() => setEv(ev.includes(e.evidence_id) ? ev.filter((x) => x !== e.evidence_id) : [...ev, e.evidence_id])} />
                        {e.evidence_id}{!e.in_period && e.source !== "P06" && " (outside period)"}
                      </label>))}</div>
                    <Button size="sm" variant="primary" disabled={action.pending} onClick={() => action.run(() => p07.judge(p.placement_id, j.outcome_id, level, ev), `${j.outcome_id} recorded`, () => setJudging(null))}>Save</Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </Section>
        <Section icon={<Flag className="h-4 w-4" />} title="Support actions" subtitle="Owner, due date and closure evidence; overdue uses the demo date">
          {(r.actions ?? []).length === 0 && <p className="text-[13px] text-muted">No actions yet.</p>}
          <ul className="space-y-2">
            {r.actions?.map((a) => (
              <li key={a.action_id} className="rounded-ctl border border-line p-3 text-[13px]">
                <div className="flex flex-wrap items-center gap-2"><strong>{a.action_id}</strong> {a.text} <StatusBadge status={a.status} />{a.overdue && <Badge tone="bad">Overdue</Badge>}</div>
                <p className="text-muted">Owner: {a.owner} · due {fmtDate(a.due)} · set by {a.created_by}</p>
                {a.status === "closed" && <p className="mt-1">Closure: {a.closure} ({fmtDate(a.closed_at)})</p>}
                {a.status === "open" && (role === a.owner || role === "advisor") && (
                  <InlineForm label="Closure evidence" button="Close action" variant="secondary" pending={action.pending}
                    onSubmit={(t) => action.run(() => p07.closeAction(a.action_id, role, t), `${a.action_id} closed`)} />
                )}
              </li>
            ))}
          </ul>
          {role === "advisor" && (
            <div className="mt-4 grid gap-2 sm:grid-cols-[1fr_140px_150px_auto] sm:items-end">
              <Field label="New action"><Input value={act.text} onChange={(e) => setAct({ ...act, text: e.target.value })} /></Field>
              <Field label="Owner"><NativeSelect value={act.owner} onChange={(e) => setAct({ ...act, owner: e.target.value })}>{["student", "supervisor", "advisor", "coordinator"].map((o) => <option key={o}>{o}</option>)}</NativeSelect></Field>
              <Field label="Due"><Input type="date" value={act.due} onChange={(e) => setAct({ ...act, due: e.target.value })} /></Field>
              <Button variant="primary" disabled={action.pending} onClick={() => action.run(() => p07.addAction(p.placement_id, act.text, act.owner, act.due), "Action added", () => setAct({ ...act, text: "" }))}>Add</Button>
            </div>
          )}
        </Section>
      </div>
      <div className="space-y-5">
        <Section title="Host milestones" subtitle="Completing a milestone alone does not demonstrate an outcome">
          <ul className="space-y-1.5 text-[13px]">
            {r.milestones?.map((m) => (
              <li key={m.milestone_id} className="flex items-center gap-2">
                <input type="checkbox" aria-label={m.text} checked={m.done} disabled={role !== "supervisor" || action.pending}
                  onChange={(e) => action.run(() => p07.setMilestone(m.milestone_id, e.target.checked))} />
                {m.text}{m.done_at && <span className="text-muted">· {fmtDate(m.done_at)}</span>}
              </li>
            ))}
          </ul>
          {role === "supervisor" && <div className="mt-3"><InlineForm label="Add milestone" button="Add" variant="secondary" pending={action.pending} onSubmit={(t) => action.run(() => p07.addMilestone(p.placement_id, t), "Milestone added")} /></div>}
        </Section>
        <Section title="Evidence" subtitle={`Period 1: ${fmtDate(r.period?.start)} – ${fmtDate(r.period?.end)}`}>
          <ul className="space-y-1.5 text-[13px]">
            {r.evidence?.map((e) => (
              <li key={e.evidence_id}><span className="font-mono text-[12px]">{e.evidence_id}</span> {e.title} <span className="text-muted">· {e.source} · {fmtDate(e.date)}</span>
                {!e.in_period && <Badge tone={e.source === "P06" ? "ok" : "neutral"} className="ml-1">{e.source === "P06" ? "Reviewed in P06" : "Outside Period 1"}</Badge>}</li>
            ))}
          </ul>
        </Section>
      </div>
    </div>
  );
}

function Final({ r, role }: { r: P07Record; role: Role }) {
  const p = r.placement!;
  const action = useAction();
  const [fb, setFb] = useState({ text: "", host: "yes" });
  const [fin, setFin] = useState({ summary: "", next: "", outcomes: Object.fromEntries((r.judgements ?? []).map((j) => [j.outcome_id, j.level])) as Record<string, string> });
  const ended = r.today > p.period_end;
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Section icon={<Trophy className="h-4 w-4" />} title="Employer feedback" subtitle="Kept separate from the academic judgement">
        {r.final?.employer ? (
          <div className="text-[13px]"><p>{r.final.employer.text}</p><p className="mt-1 text-muted">{r.final.employer.by} · {fmtDate(r.final.employer.at)} · would host again: {r.final.employer.would_host}</p></div>
        ) : role === "supervisor" ? (
          <div className="space-y-2">
            <Field label="Feedback (10+ words)"><TextArea value={fb.text} onChange={(e) => setFb({ ...fb, text: e.target.value })} /></Field>
            <Field label="Would you host another student?"><NativeSelect value={fb.host} onChange={(e) => setFb({ ...fb, host: e.target.value })}><option>yes</option><option>maybe</option><option>no</option></NativeSelect></Field>
            <Button variant="primary" size="sm" disabled={action.pending} onClick={() => action.run(() => p07.employerFeedback(p.placement_id, fb.text, fb.host), "Employer feedback recorded")}>Submit feedback</Button>
          </div>
        ) : <p className="text-[13px] text-muted">Not given yet.</p>}
      </Section>
      <Section icon={<Trophy className="h-4 w-4" />} title="Academic advisor's final review" subtitle="An outcome is achieved only with evidence from this period (or reviewed P06 evidence)">
        {r.final?.advisor ? (
          <div className="space-y-2 text-[13px]">
            <div className="flex flex-wrap gap-1.5">{Object.entries(r.final.advisor.outcomes).map(([lo, lv]) => <Badge key={lo} tone={lv === "achieved" ? "ok" : lv === "developing" ? "blue" : "neutral"}>{lo}: {lv}</Badge>)}</div>
            <p>{r.final.advisor.summary}</p><p><strong>Next period goal:</strong> {r.final.advisor.next_goal}</p>
            <p className="text-muted">{r.final.advisor.by} · {fmtDate(r.final.advisor.at)}</p>
          </div>
        ) : role === "advisor" ? (
          <div className="space-y-3">
            {!ended && <Notice tone="warn">Period 1 ends {fmtDate(p.period_end)}. Set the demo date later to record the final review at the end of the period.</Notice>}
            <div className="grid gap-2 sm:grid-cols-2">{r.outcomes.map((o) => (
              <Field key={o.outcome_id} label={`${o.outcome_id} · ${o.name}`}>
                <NativeSelect value={fin.outcomes[o.outcome_id] ?? "none"} onChange={(e) => setFin({ ...fin, outcomes: { ...fin.outcomes, [o.outcome_id]: e.target.value } })}>
                  <option value="none">Not yet evidenced</option><option value="developing">Developing</option><option value="achieved">Achieved</option>
                </NativeSelect>
              </Field>))}</div>
            <Field label="Summary (10+ words)"><TextArea value={fin.summary} onChange={(e) => setFin({ ...fin, summary: e.target.value })} /></Field>
            <Field label="Goal for the next period"><Input value={fin.next} onChange={(e) => setFin({ ...fin, next: e.target.value })} /></Field>
            <Button variant="primary" size="sm" disabled={action.pending} onClick={() => action.run(() => p07.finalReview(p.placement_id, fin.outcomes, fin.summary, fin.next), "Final review recorded")}>Record final review</Button>
          </div>
        ) : <p className="text-[13px] text-muted">Not recorded yet. Official grading follows university process.</p>}
      </Section>
    </div>
  );
}
