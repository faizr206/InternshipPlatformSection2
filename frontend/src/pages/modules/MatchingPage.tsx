import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Flag, History, RefreshCw, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { listings, p04, p05, type Listing, type Recommendation } from "@/api/modules";
import { InlineForm, Loading, NativeSelect, Notice, Section, StatusBadge, Timeline, fmtDate, useAction } from "@/components/kit";
import { Badge, Button, Card, EmptyState, buttonStyles } from "@/components/ui";
import { useDemo } from "@/context/DemoContext";
import { ApplyForm } from "./OpportunitiesPage";

const skillOf = (gap: string) => /\((SK-[A-Z]+)\)/.exec(gap)?.[1];

export default function MatchingPage() {
  const { role, studentId } = useDemo();
  const recs = useQuery({ queryKey: ["p05", studentId], queryFn: () => p05.latest(studentId) });
  const runs = useQuery({ queryKey: ["p05-runs", studentId], queryFn: () => p05.runs(studentId) });
  const all = useQuery({ queryKey: ["listings"], queryFn: listings.all });
  const action = useAction();
  const [showAll, setShowAll] = useState(false);
  const byId = new Map((all.data ?? []).map((o) => [o.opportunity_id, o]));
  // Backlog P5-01: three ranked recommendations (eligible first, then score); the rest stay one click away.
  const shown = showAll ? recs.data ?? [] : (recs.data ?? []).slice(0, 3);
  const hidden = (recs.data?.length ?? 0) - shown.length;

  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_320px]">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          {role === "student" && (
            <Button variant="primary" disabled={action.pending} onClick={() => action.run(() => p05.run(studentId), "Matching rerun on your latest profile")}>
              <RefreshCw className="h-4 w-4" />{recs.data?.length ? "Rerun matching" : "Find my matches"}
            </Button>
          )}
          <p className="text-[13px] text-muted">Rules baseline (rules-v3) decides eligibility, score and gaps. The AI panel only explains; it never changes them. A recommendation is not an application or a placement.</p>
        </div>
        {!recs.data ? <Loading /> : recs.data.length === 0 ? (
          <Card><EmptyState icon={<Sparkles className="h-6 w-6" />} title="No recommendations yet">{role === "student" ? "Run matching to see explained suggestions." : "The student has not run matching yet."}</EmptyState></Card>
        ) : (
          <>
            <h2 className="text-[15px] font-semibold">Your top {Math.min(3, recs.data.length)} recommendations</h2>
            {shown.map((r, i) => <RecCard key={r.recommendation_id} r={r} rank={i + 1} listing={byId.get(r.opportunity_id)} />)}
            {hidden > 0 && <Button variant="secondary" onClick={() => setShowAll(true)}>Show {hidden} more ranked listing{hidden > 1 ? "s" : ""}</Button>}
            {showAll && recs.data.length > 3 && <Button variant="ghost" onClick={() => setShowAll(false)}>Show top three only</Button>}
          </>
        )}
        {role === "coordinator" && <Corrections />}
      </div>
      <Section icon={<History className="h-4 w-4" />} title="Matching runs" subtitle="Earlier runs keep their profile version">
        {runs.data?.length ? (
          <Timeline items={[...runs.data].reverse().map((run) => ({
            title: <>Profile v{run.profile_version}</>, meta: `${fmtDate(run.created_at)} · run ${run.run_id}`,
            body: `${run.eligible} eligible of ${run.results}`,
          }))} />
        ) : <p className="text-[13px] text-muted">No runs yet.</p>}
      </Section>
    </div>
  );
}

function RecCard({ r, rank, listing }: { r: Recommendation; rank: number; listing?: Listing }) {
  const { role, studentId } = useDemo();
  const action = useAction();
  const mine = useQuery({ queryKey: ["p04-mine", studentId], queryFn: () => p04.mine(studentId), enabled: role === "student" });
  const [applying, setApplying] = useState(false);
  const [flagging, setFlagging] = useState(false);
  const [field, setField] = useState("availability");
  const applied = mine.data?.find((a) => a.opportunity_id === r.opportunity_id);
  const ai = r.ai_insights;
  const open = listing?.publication_status === "published" && listing.listing_status === "open";

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-start gap-4 p-5">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-navy text-sm font-bold text-white">{rank}</span>
        <div className="min-w-0 flex-1">
          <h3 className="text-[16px] font-semibold">{listing?.title ?? r.opportunity_id}</h3>
          <p className="text-[13px] text-muted">{listing?.employer_name} · {listing?.location} · {listing?.work_mode} · {r.opportunity_id} v{r.opportunity_version}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <StatusBadge status={r.eligibility} />
            {r.eligibility === "unknown" && <Badge tone="warn">Eligibility needs checking</Badge>}
            {r.gaps.length > 0 && <Badge tone="bad">{r.gaps.length} gap{r.gaps.length > 1 ? "s" : ""}</Badge>}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-gold-50 px-4 py-2 text-center"><div className="text-2xl font-bold text-navy">{r.score}</div><div className="text-[10.5px] font-semibold tracking-wide text-gold-ink uppercase">Rules score</div></div>
          {ai && (
            <div className="grid h-16 w-16 place-items-center rounded-full text-center" style={{ background: `conic-gradient(var(--color-ai) ${ai.relevance * 3.6}deg, var(--color-ai-50) 0)` }}>
              <div className="grid h-12 w-12 place-items-center rounded-full bg-surface"><span className="text-[13px] font-bold text-ai">{ai.relevance}%</span></div>
            </div>
          )}
        </div>
      </div>
      <div className="grid gap-4 border-t border-line px-5 py-4 md:grid-cols-2">
        <div>
          <div className="mb-1 text-[11.5px] font-semibold tracking-wide text-muted uppercase">Why it matches · {r.method_version}</div>
          <ul className="list-disc space-y-0.5 pl-5 text-[13px]">{r.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
        </div>
        <div className="space-y-3">
          <div>
            <div className="mb-1 text-[11.5px] font-semibold tracking-wide text-muted uppercase">Gaps</div>
            {r.gaps.length === 0 ? <p className="text-[13px] text-muted">No gaps</p> : (
              <ul className="space-y-1.5 text-[13px]">
                {r.gaps.map((g) => (
                  <li key={g} className="flex flex-wrap items-center justify-between gap-2">
                    <span>{g}</span>
                    {role === "student" && skillOf(g) && (
                      <Button size="sm" variant="secondary" disabled={action.pending}
                        onClick={() => action.run(() => p05.prepare(r.recommendation_id, skillOf(g)!), "Sent to your preparation plan (P06)")}>
                        Prepare <ArrowRight className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <div className="mb-1 text-[11.5px] font-semibold tracking-wide text-muted uppercase">Unknowns</div>
            {r.unknowns.length ? <ul className="list-disc pl-5 text-[13px]">{r.unknowns.map((u) => <li key={u}>{u}</li>)}</ul> : <p className="text-[13px] text-muted">Nothing missing</p>}
          </div>
        </div>
      </div>
      {ai && (
        <div className="mx-5 mb-4 rounded-card border border-ai-line bg-ai-50/60 p-4 text-[13px]">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <Sparkles className="h-4 w-4 text-ai" aria-hidden /><span className="font-semibold text-ai">AI assistant</span>
            <Badge tone="ai">simulated · deterministic</Badge>
            <span className="ml-auto font-mono text-[11px] text-muted">{r.ai_method_version} · {ai.version}</span>
          </div>
          <p>{ai.summary}</p>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            {r.ai_matches.length > 0 && (
              <div>
                <div className="mb-1 text-[11px] font-semibold tracking-wide text-ai uppercase">Skill terms it recognised</div>
                {r.ai_matches.map((m) => <p key={m.term}>“{m.term}” in the {m.field} ≈ your <strong>{m.skill_name ?? m.skill_id}</strong> ({m.evidence_status})</p>)}
              </div>
            )}
            {ai.next_steps.length > 0 && (
              <div>
                <div className="mb-1 text-[11px] font-semibold tracking-wide text-ai uppercase">Next steps to strengthen this match</div>
                {ai.next_steps.map((n) => <p key={n.skill_id + n.kind}>{n.score_gain > 0 && <Badge tone="ok" className="mr-1">+{n.score_gain}</Badge>}{n.tip}</p>)}
              </div>
            )}
          </div>
          {ai.similar.length > 0 && <p className="mt-2 text-muted">Similar open listings: {ai.similar.map((s) => s.title).join(", ")}</p>}
          <p className="mt-2 text-[11.5px] text-muted">Assistance only: it never changes eligibility, score, gaps or unknowns, and never invents a qualification.</p>
        </div>
      )}
      {role === "student" && (
        <div className="border-t border-line px-5 py-3">
          {applied ? <p className="text-[13px]">Applied: <StatusBadge status={applied.application_status} /> <Link to="/applications" className="text-blue underline">View</Link></p>
            : applying ? <ApplyForm opportunityId={r.opportunity_id} onDone={() => setApplying(false)} />
            : (
              <div className="flex flex-wrap gap-2">
                {open && <Button variant="primary" size="sm" onClick={() => setApplying(true)}>Apply</Button>}
                <Button size="sm" variant="ghost" onClick={() => setFlagging(!flagging)}><Flag className="h-3.5 w-3.5" />Something looks wrong</Button>
                <Link to="/preparation" className={buttonStyles("ghost", "sm")}>Preparation plan</Link>
              </div>
            )}
          {flagging && (
            <div className="mt-3 grid gap-2 sm:grid-cols-[180px_1fr]">
              <NativeSelect aria-label="Which input is wrong" value={field} onChange={(e) => setField(e.target.value)}>
                {["availability", "interests", "skills", "listing dates", "required skills", "listing status"].map((f) => <option key={f}>{f}</option>)}
              </NativeSelect>
              <InlineForm label="What should the coordinator check?" button="Send to coordinator" pending={action.pending}
                onSubmit={(t) => action.run(() => p05.flag(r.recommendation_id, t, field), "Correction request sent", () => setFlagging(false))} />
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function Corrections() {
  const c = useQuery({ queryKey: ["corrections"], queryFn: p05.corrections });
  const action = useAction();
  return (
    <Section title="Correction requests" subtitle="Students challenge a recommendation; the owning module (P01/P03) applies corrections as new versions">
      {!c.data?.length ? <p className="text-[13px] text-muted">No correction requests.</p> : (
        <div className="space-y-3">
          {c.data.map((x) => (
            <div key={x.correction_id} className="rounded-ctl border border-line p-3 text-[13px]">
              <div className="flex flex-wrap items-center gap-2"><strong>{x.correction_id}</strong> {x.student_name} · {x.affected_field} ({x.source_module}) <StatusBadge status={x.status} /></div>
              <p className="mt-1">{x.reason}</p>
              {x.status === "flagged" && <InlineForm label="Note for the owning module" button="Record request" variant="secondary" pending={action.pending}
                onSubmit={(t) => action.run(() => p05.record(x.correction_id, t), "Recorded for the owning module")} />}
              {x.note && <Notice>{x.note}</Notice>}
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}
