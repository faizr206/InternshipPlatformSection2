import { useQuery } from "@tanstack/react-query";
import { History, Pencil, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { p01 } from "@/api/modules";
import { Field, Input, InlineForm, KeyValues, Loading, Notice, Section, SkillChip, StatusBadge, TextArea, Timeline, fmtDate, useAction, useSkillNames } from "@/components/kit";
import { Button } from "@/components/ui";
import { useDemo } from "@/context/DemoContext";

/** P01 student profile: draft, submit as a new version, coordinator clarification and review. */
export default function ProfilePage() {
  const { role, studentId } = useDemo();
  const state = useQuery({ queryKey: ["p01", studentId], queryFn: () => p01.state(studentId) });
  const versions = useQuery({ queryKey: ["p01-versions", studentId], queryFn: () => p01.versions(studentId) });
  const { data: names } = useSkillNames();
  const action = useAction();
  const [editing, setEditing] = useState(false);

  if (!state.data) return <Loading />;
  const { profile, review, draft } = state.data;

  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_340px]">
      <div className="space-y-5">
        {state.data.status === "clarification_requested" && review && (
          <Notice tone="warn"><strong>Clarification requested by {review.actor_name}:</strong> {review.comment}</Notice>
        )}
        <Section
          icon={<UserRound className="h-4 w-4" />}
          title={profile.display_name}
          subtitle={<>Profile v{profile.profile_version} · {profile.student_id} · the version P04 and P05 read</>}
          action={<StatusBadge status={state.data.status} />}
        >
          <KeyValues items={[
            ["Interests", profile.interests.length ? profile.interests.join(", ") : <span className="text-warn">Not given yet</span>],
            ["Availability", profile.availability_start ? `${fmtDate(profile.availability_start)} – ${fmtDate(profile.availability_end)}` : <span className="text-warn">Not known yet</span>],
            ["Goals", profile.goals],
            ["Preferred location", profile.preferred_location],
          ]} />
          <div className="mt-4">
            <div className="mb-1.5 text-[11.5px] font-semibold tracking-wide text-muted uppercase">Skills and evidence</div>
            <div className="flex flex-wrap gap-1.5">
              {profile.skills.map((s) => (
                <span key={s.skill_id} title={s.evidence_id ? `${s.evidence_id} · reviewed by ${s.reviewed_by} on ${fmtDate(s.reviewed_at)}` : "Self-declared: no reviewed evidence yet"}>
                  <SkillChip id={s.skill_id} names={names} status={s.evidence_status} />
                </span>
              ))}
            </div>
            <p className="mt-2 text-[12px] text-muted">Self-declared skills stay self-declared until a reviewer records evidence in Preparation (P06).</p>
          </div>
          {role === "student" && !editing && (
            <div className="mt-4 flex gap-2">
              <Button variant="primary" size="sm" onClick={() => setEditing(true)}><Pencil className="h-3.5 w-3.5" />{draft ? "Continue draft" : "Edit profile"}</Button>
              {draft && <Button size="sm" disabled={action.pending} onClick={() => action.run(() => p01.submit(studentId), "Profile submitted as a new version")}>Submit draft</Button>}
            </div>
          )}
        </Section>

        {role === "student" && editing && (
          <DraftForm
            initial={draft ?? { ...profile, skills: profile.skills.map((s) => s.skill_id) }}
            names={names ?? {}}
            pending={action.pending}
            onCancel={() => setEditing(false)}
            onSave={(values, submit) => action.run(async () => {
              await p01.saveDraft(studentId, values);
              if (submit) await p01.submit(studentId);
            }, submit ? "Profile submitted as a new version (existing matches are rerun on it)" : "Draft saved — P04/P05 still read the submitted version", () => setEditing(false))}
          />
        )}

        {role === "coordinator" && (
          <Section title="Coordinator review" subtitle={`Applies to profile v${profile.profile_version}`}>
            <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-end">
              <InlineForm label="Ask the student to clarify" placeholder="e.g. Which roles in aviation do you mean?" button="Request clarification"
                pending={action.pending} onSubmit={(t) => action.run(() => p01.review(studentId, "clarification_requested", t), "Clarification requested")} />
              <Button variant="secondary" disabled={action.pending} onClick={() => action.run(() => p01.review(studentId, "reviewed"), "Profile marked reviewed")}>Mark reviewed</Button>
            </div>
          </Section>
        )}
      </div>

      <Section icon={<History className="h-4 w-4" />} title="Version history" subtitle="Earlier versions are never edited">
        {versions.data ? (
          <Timeline items={[...versions.data].reverse().map((v) => ({
            title: <>v{v.profile_version} {v.profile_version === profile.profile_version && <StatusBadge status="submitted" className="ml-1" />}</>,
            meta: `${v.source.replace("P06:reviewed_skill:", "Reviewed evidence ")} · ${v.created_at ? fmtDate(v.created_at) : "P01–P03 export"}`,
            body: `${v.profile.skills.filter((s) => s.evidence_status === "reviewed").length} reviewed skill(s) · ${v.profile.interests.join(", ") || "no interests"}`,
            tone: v.source.startsWith("P06") ? "ok" : undefined,
          }))} />
        ) : <Loading />}
      </Section>
    </div>
  );
}

type DraftValues = { display_name?: string; goals?: string | null; interests?: string[]; preferred_location?: string | null; availability_start?: string | null; availability_end?: string | null; skills?: string[] };

function DraftForm({ initial, names, pending, onSave, onCancel }: {
  initial: DraftValues; names: Record<string, string>; pending: boolean; onSave: (v: DraftValues, submit: boolean) => void; onCancel: () => void;
}) {
  const [v, setV] = useState<DraftValues>(initial);
  const [interests, setInterests] = useState((initial.interests ?? []).join(", "));
  useEffect(() => setV((x) => ({ ...x, interests: interests.split(",").map((i) => i.trim()).filter(Boolean) })), [interests]);
  const toggle = (id: string) => setV((x) => ({ ...x, skills: x.skills?.includes(id) ? x.skills.filter((s) => s !== id) : [...(x.skills ?? []), id] }));
  return (
    <Section title="Edit profile" subtitle="Saving keeps a draft. Submitting creates the next version; reviewed evidence is kept.">
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Display name"><Input value={v.display_name ?? ""} onChange={(e) => setV({ ...v, display_name: e.target.value })} maxLength={60} /></Field>
        <Field label="Preferred location"><Input value={v.preferred_location ?? ""} onChange={(e) => setV({ ...v, preferred_location: e.target.value })} /></Field>
        <Field label="Interests" hint="Comma-separated sectors or roles, e.g. aviation, analytics"><Input value={interests} onChange={(e) => setInterests(e.target.value)} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Available from"><Input type="date" value={v.availability_start ?? ""} onChange={(e) => setV({ ...v, availability_start: e.target.value })} /></Field>
          <Field label="Available until"><Input type="date" value={v.availability_end ?? ""} onChange={(e) => setV({ ...v, availability_end: e.target.value })} /></Field>
        </div>
        <Field label="Goals" className="md:col-span-2"><TextArea value={v.goals ?? ""} onChange={(e) => setV({ ...v, goals: e.target.value })} placeholder="What do you hope to learn on your co-op?" /></Field>
      </div>
      <fieldset className="mt-4">
        <legend className="mb-1.5 text-[12.5px] font-semibold">Skills you can declare</legend>
        <div className="flex flex-wrap gap-2">
          {Object.entries(names).map(([id, name]) => (
            <label key={id} className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-[12.5px]">
              <input type="checkbox" checked={v.skills?.includes(id) ?? false} onChange={() => toggle(id)} /> {name}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="mt-5 flex flex-wrap gap-2">
        <Button variant="primary" disabled={pending} onClick={() => onSave(v, true)}>Submit as new version</Button>
        <Button disabled={pending} onClick={() => onSave(v, false)}>Save draft</Button>
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </Section>
  );
}
