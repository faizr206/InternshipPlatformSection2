import { useQuery } from "@tanstack/react-query";
import { Building2, CalendarDays, ClipboardCheck, MapPin, Search, Send } from "lucide-react";
import { useState } from "react";
import { listings, p04, type Listing } from "@/api/modules";
import { Field, Input, InlineForm, Loading, NativeSelect, Notice, Section, SkillChip, StatusBadge, TextArea, Timeline, fmtDate, useAction, useSkillNames } from "@/components/kit";
import { Badge, Button, Card, EmptyState, OwnerChip, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui";
import { useDemo } from "@/context/DemoContext";

export default function OpportunitiesPage() {
  const { role } = useDemo();
  if (role === "employer") return <EmployerView />;
  if (role === "coordinator") return <CoordinatorView />;
  return <StudentCatalogue />;
}

function ListingCard({ o, children, names }: { o: Listing; children?: React.ReactNode; names?: Record<string, string> }) {
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-start gap-3">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue"><Building2 className="h-5 w-5" aria-hidden /></div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[15px] font-semibold">{o.title}</h3>
            {o.status && <StatusBadge status={o.status} />}
            <span className="font-mono text-[11.5px] text-muted">{o.opportunity_id} · v{o.version}</span>
          </div>
          <p className="text-[13px] text-muted">{o.employer_name}</p>
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-muted">
            <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5" aria-hidden />{o.location} · {o.work_mode}</span>
            <span className="inline-flex items-center gap-1"><CalendarDays className="h-3.5 w-3.5" aria-hidden />{o.start_date ? `${fmtDate(o.start_date)} – ${fmtDate(o.end_date)}` : "Dates not set"}</span>
            {o.sector && <span>Sector: {o.sector}</span>}
          </div>
          {o.description && <p className="mt-2 text-[13px] text-ink/85">{o.description}</p>}
          {(o.required_skills.length > 0 || o.desirable_skills.length > 0) && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[12px]">
              {o.required_skills.map((s) => <SkillChip key={s} id={s} names={names} />)}
              {o.desirable_skills.map((s) => <Badge key={s} tone="neutral">{names?.[s] ?? s} · desirable</Badge>)}
            </div>
          )}
          {o.review_reason && <Notice tone="warn"><strong>Coordinator:</strong> {o.review_reason}</Notice>}
        </div>
      </div>
      {children && <div className="mt-3 border-t border-line pt-3">{children}</div>}
    </Card>
  );
}

// ---------------- Student (P04 discovery) ----------------
function StudentCatalogue() {
  const { studentId } = useDemo();
  const [q, setQ] = useState("");
  const open = useQuery({ queryKey: ["open-listings", q], queryFn: () => listings.open(q) });
  const mine = useQuery({ queryKey: ["p04-mine", studentId], queryFn: () => p04.mine(studentId) });
  const { data: names } = useSkillNames();
  const [applying, setApplying] = useState<string | null>(null);
  const applied = new Map((mine.data ?? []).map((a) => [a.opportunity_id, a.application_status]));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute top-2.5 left-3 h-4 w-4 text-muted" aria-hidden />
          <Input aria-label="Search opportunities" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title or employer" className="pl-9" />
        </div>
        <p className="text-[13px] text-muted">Only listings that are published and open (P03) are shown. See Matching for explained recommendations.</p>
      </div>
      {!open.data ? <Loading /> : open.data.length === 0 ? (
        <Card><EmptyState icon={<Building2 className="h-6 w-6" />} title="No open listings match" /></Card>
      ) : open.data.map((o) => (
        <ListingCard key={o.opportunity_id} o={o} names={names}>
          {applied.has(o.opportunity_id) ? (
            <p className="text-[13px]">Your application: <StatusBadge status={applied.get(o.opportunity_id)!} /></p>
          ) : applying === o.opportunity_id ? (
            <ApplyForm opportunityId={o.opportunity_id} onDone={() => setApplying(null)} />
          ) : (
            <Button variant="primary" size="sm" onClick={() => setApplying(o.opportunity_id)}><Send className="h-3.5 w-3.5" />Apply</Button>
          )}
        </ListingCard>
      ))}
    </div>
  );
}

export function ApplyForm({ opportunityId, onDone }: { opportunityId: string; onDone: () => void }) {
  const { studentId } = useDemo();
  const [statement, setStatement] = useState("");
  const action = useAction();
  return (
    <div className="space-y-2">
      <Field label="Why this role fits you" hint="Required to submit. Your latest submitted profile version is attached.">
        <TextArea value={statement} onChange={(e) => setStatement(e.target.value)} />
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" size="sm" disabled={action.pending} onClick={() => action.run(() => p04.apply(studentId, opportunityId, statement), "Application submitted", onDone)}>Submit application</Button>
        <Button size="sm" disabled={action.pending} onClick={() => action.run(() => p04.draft(studentId, opportunityId, statement), "Draft saved (not submitted)", onDone)}>Save draft</Button>
        <Button variant="ai" size="sm" disabled={action.pending} onClick={() => action.run(async () => setStatement((await p04.statementDraft(studentId, opportunityId)).statement))}>Draft with AI</Button>
        <Button variant="ghost" size="sm" onClick={onDone}>Cancel</Button>
      </div>
      <p className="text-[11.5px] text-muted">The AI draft cites only skills already on your profile. Edit it before submitting.</p>
    </div>
  );
}

// ---------------- Employer (P02 submission) ----------------
const EMPTY = { organization_name: "Emirates Group (fictional)", title: "", description: "", location: "Dubai", work_mode: "on-site", sector: "", start_date: "", end_date: "", duration: "", required_skills: [] as string[], desirable_skills: [] as string[], supervisor_name: "", supervisor_contact: "" };

function ListingForm({ initial, submitLabel, onSubmit, pending }: { initial: typeof EMPTY; submitLabel: string; onSubmit: (v: typeof EMPTY) => void; pending: boolean }) {
  const [v, setV] = useState(initial);
  const { data: names } = useSkillNames();
  const set = (k: keyof typeof EMPTY) => (e: { target: { value: string } }) => setV({ ...v, [k]: e.target.value });
  const toggle = (k: "required_skills" | "desirable_skills", id: string) => setV({ ...v, [k]: v[k].includes(id) ? v[k].filter((s) => s !== id) : [...v[k], id] });
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); onSubmit(v); }}>
      <div className="grid gap-3 md:grid-cols-2">
        <Field label="Organization"><Input value={v.organization_name} onChange={set("organization_name")} maxLength={80} /></Field>
        <Field label="Role title"><Input value={v.title} onChange={set("title")} maxLength={100} placeholder="e.g. Network Planning Intern" /></Field>
        <Field label="Description" className="md:col-span-2" hint="Tasks and learning opportunities (max 600 characters)"><TextArea value={v.description} onChange={set("description")} maxLength={600} /></Field>
        <Field label="Location"><Input value={v.location} onChange={set("location")} /></Field>
        <Field label="Work mode"><NativeSelect value={v.work_mode} onChange={set("work_mode")}><option value="on-site">On-site</option><option value="hybrid">Hybrid</option><option value="remote">Remote</option></NativeSelect></Field>
        <Field label="Start date"><Input type="date" value={v.start_date} onChange={set("start_date")} /></Field>
        <Field label="End date"><Input type="date" value={v.end_date} onChange={set("end_date")} /></Field>
        <Field label="Sector"><Input value={v.sector} onChange={set("sector")} placeholder="e.g. aviation" /></Field>
        <Field label="Duration"><Input value={v.duration} onChange={set("duration")} placeholder="e.g. 4 months" /></Field>
        <Field label="Workplace supervisor" hint="Sent to P07 with a confirmed placement; never shown to students"><Input value={v.supervisor_name} onChange={set("supervisor_name")} /></Field>
        <Field label="Supervisor contact"><Input value={v.supervisor_contact} onChange={set("supervisor_contact")} /></Field>
      </div>
      {(["required_skills", "desirable_skills"] as const).map((k) => (
        <fieldset key={k}>
          <legend className="mb-1.5 text-[12.5px] font-semibold">{k === "required_skills" ? "Required skills" : "Desirable skills"}</legend>
          <div className="flex flex-wrap gap-2">
            {Object.entries(names ?? {}).map(([id, name]) => (
              <label key={id} className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-[12.5px]">
                <input type="checkbox" checked={v[k].includes(id)} onChange={() => toggle(k, id)} /> {name}
              </label>
            ))}
          </div>
        </fieldset>
      ))}
      <Button type="submit" variant="primary" disabled={pending}><Send className="h-4 w-4" />{submitLabel}</Button>
    </form>
  );
}

function EmployerView() {
  const all = useQuery({ queryKey: ["listings"], queryFn: listings.all });
  const action = useAction();
  const { data: names } = useSkillNames();
  const [revising, setRevising] = useState<string | null>(null);
  const own = all.data ?? []; // one synthetic employer in the demo: every listing is theirs
  return (
    <Tabs defaultValue="mine" className="space-y-4">
      <TabsList><TabsTrigger value="mine">My listings</TabsTrigger><TabsTrigger value="new">Submit a listing</TabsTrigger></TabsList>
      <TabsContent value="new">
        <Section title="New opportunity" subtitle={<>Submitting creates an ID and version 1. It is <strong>not public</strong> until the university approves and publishes it. <OwnerChip owner="P02" /></>}>
          <ListingForm initial={EMPTY} submitLabel="Submit for review" pending={action.pending} onSubmit={(v) => action.run(() => listings.submit(v), "Submitted for university review")} />
        </Section>
      </TabsContent>
      <TabsContent value="mine" className="space-y-3">
        {!all.data ? <Loading /> : own.map((o) => (
          <ListingCard key={o.opportunity_id} o={o} names={names}>
            {o.status === "Returned for revision" && (revising === o.opportunity_id ? (
              <ListingForm initial={{ ...EMPTY, ...Object.fromEntries(Object.entries(o).filter(([, x]) => x !== null)), organization_name: o.employer_name } as typeof EMPTY}
                submitLabel={`Resubmit as version ${o.version + 1}`} pending={action.pending}
                onSubmit={(v) => action.run(() => listings.resubmit(o.opportunity_id, v), "Resubmitted as a new version", () => setRevising(null))} />
            ) : <Button variant="primary" size="sm" onClick={() => setRevising(o.opportunity_id)}>Revise and resubmit</Button>)}
            <Versions id={o.opportunity_id} />
          </ListingCard>
        ))}
      </TabsContent>
    </Tabs>
  );
}

function Versions({ id }: { id: string }) {
  const [open, setOpen] = useState(false);
  const d = useQuery({ queryKey: ["decisions", id], queryFn: () => listings.decisions(id), enabled: open });
  return (
    <details className="mt-2 text-[13px]" onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer text-muted">Decision history</summary>
      <div className="mt-2">
        {d.data?.length ? <Timeline items={d.data.map((x) => ({ title: `${x.decision} · v${x.version}`, meta: `${x.actor_name} · ${fmtDate(x.created_at)}`, body: x.reason, tone: x.decision === "declined" ? "bad" : x.decision === "returned" ? "warn" : "ok" }))} />
          : <p className="text-muted">No decisions yet.</p>}
      </div>
    </details>
  );
}

// ---------------- Coordinator (P03 review and publication) ----------------
function CoordinatorView() {
  const all = useQuery({ queryKey: ["listings"], queryFn: listings.all });
  const checklist = useQuery({ queryKey: ["checklist"], queryFn: listings.checklist });
  const { data: names } = useSkillNames();
  const by = (s: string) => (all.data ?? []).filter((o) => o.status === s);
  if (!all.data) return <Loading />;
  return (
    <Tabs defaultValue="queue" className="space-y-4">
      <TabsList>
        <TabsTrigger value="queue">Review queue ({by("Pending review").length})</TabsTrigger>
        <TabsTrigger value="approved">Approved ({by("Approved").length})</TabsTrigger>
        <TabsTrigger value="published">Published ({by("Published").length})</TabsTrigger>
        <TabsTrigger value="other">Returned, declined, closed</TabsTrigger>
      </TabsList>
      <TabsContent value="queue" className="space-y-3">
        {by("Pending review").length === 0 && <Card><EmptyState icon={<ClipboardCheck className="h-6 w-6" />} title="Nothing waiting for review" /></Card>}
        {by("Pending review").map((o) => (
          <ListingCard key={o.opportunity_id} o={o} names={names}><ReviewForm o={o} checklist={checklist.data ?? []} /></ListingCard>
        ))}
      </TabsContent>
      <TabsContent value="approved" className="space-y-3">
        {by("Approved").map((o) => <ListingCard key={o.opportunity_id} o={o} names={names}><PublishButtons o={o} /></ListingCard>)}
        {by("Approved").length === 0 && <p className="text-[13px] text-muted">Approved listings wait here until published. Approval and publication are separate decisions.</p>}
      </TabsContent>
      <TabsContent value="published" className="space-y-3">
        {by("Published").map((o) => <ListingCard key={o.opportunity_id} o={o} names={names}><PublishButtons o={o} /></ListingCard>)}
      </TabsContent>
      <TabsContent value="other" className="space-y-3">
        {[...by("Returned for revision"), ...by("Declined"), ...by("Closed")].map((o) => <ListingCard key={o.opportunity_id} o={o} names={names}><Versions id={o.opportunity_id} /></ListingCard>)}
      </TabsContent>
    </Tabs>
  );
}

function ReviewForm({ o, checklist }: { o: Listing; checklist: string[] }) {
  const [checked, setChecked] = useState<string[]>([]);
  const [reason, setReason] = useState("");
  const action = useAction();
  const decide = (d: string) => action.run(() => listings.decide(o.opportunity_id, d, reason, checked),
    d === "approve" ? "Approved (publish it when ready)" : d === "return" ? "Returned to the employer" : "Declined");
  return (
    <div className="space-y-3">
      <fieldset>
        <legend className="mb-1 text-[12.5px] font-semibold">Review checklist <span className="font-normal text-muted">(recorded with the decision; ticking alone never approves)</span></legend>
        <div className="grid gap-1 sm:grid-cols-2">
          {checklist.map((c) => (
            <label key={c} className="flex items-center gap-2 text-[13px]">
              <input type="checkbox" checked={checked.includes(c)} onChange={() => setChecked(checked.includes(c) ? checked.filter((x) => x !== c) : [...checked, c])} />{c}
            </label>
          ))}
        </div>
      </fieldset>
      <Field label="Reason (required to return or decline, max 300 characters)"><Input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} /></Field>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" size="sm" disabled={action.pending} onClick={() => decide("approve")}>Approve</Button>
        <Button size="sm" disabled={action.pending} onClick={() => decide("return")}>Return for revision</Button>
        <Button size="sm" disabled={action.pending} onClick={() => decide("decline")} className="text-bad">Decline</Button>
      </div>
    </div>
  );
}

function PublishButtons({ o }: { o: Listing }) {
  const action = useAction();
  const [closing, setClosing] = useState(false);
  if (o.status === "Approved")
    return <Button variant="primary" size="sm" disabled={action.pending} onClick={() => action.run(() => listings.publish(o.opportunity_id), `${o.opportunity_id} is now visible to students`)}>Publish v{o.version}</Button>;
  return closing ? (
    <InlineForm label="Why close it? (optional)" button="Close listing" variant="secondary" pending={action.pending}
      onSubmit={(t) => action.run(() => listings.close(o.opportunity_id, t), "Listing closed: no new applications")} />
  ) : (
    <div className="flex items-center gap-2">
      <Button size="sm" onClick={() => setClosing(true)}>Close listing</Button>
      <Versions id={o.opportunity_id} />
    </div>
  );
}
