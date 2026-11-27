import { useQuery } from "@tanstack/react-query";
import { BookOpen, Bot, Inbox } from "lucide-react";
import { useState } from "react";
import { assistant } from "@/api/modules";
import { Field, Input, InlineForm, Loading, Notice, Section, StatusBadge, TextArea, fmtDate, useAction } from "@/components/kit";
import { Badge, Button, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui";
import { useUI } from "@/components/layout/UIContext";
import { useDemo } from "@/context/DemoContext";

export default function AssistantPage() {
  const { role } = useDemo();
  const status = useQuery({ queryKey: ["assistant-status"], queryFn: assistant.status });
  const faq = useQuery({ queryKey: ["assistant-faq"], queryFn: assistant.faq });
  const { openAssistant } = useUI();
  return (
    <Tabs defaultValue={role === "coordinator" ? "queue" : "faq"} className="space-y-4">
      <TabsList>
        {role === "coordinator" && <TabsTrigger value="queue">Coordinator queue</TabsTrigger>}
        <TabsTrigger value="faq">Approved answers ({faq.data?.length ?? "…"})</TabsTrigger>
      </TabsList>
      <Notice tone="ai">
        <Bot className="mr-1 inline h-4 w-4" aria-hidden />
        {status.data?.note ?? "Answers come only from approved entries."} Mode: <strong>{status.data?.mode ?? "…"}</strong>
        {status.data?.model && <> ({status.data.model})</>}. <button className="font-semibold text-ai underline" onClick={() => openAssistant()}>Open the chat</button>
      </Notice>
      {role === "coordinator" && <TabsContent value="queue"><CoordinatorQueue /></TabsContent>}
      <TabsContent value="faq">
        <Section icon={<BookOpen className="h-4 w-4" />} title="Approved FAQ" subtitle="Merged from Team P6/P7 and P01–P03; coordinator-approved additions appear here">
          {!faq.data ? <Loading /> : (
            <div className="divide-y divide-line">
              {faq.data.map((e) => (
                <details key={e.faq_id} className="py-2.5 text-[13px]">
                  <summary className="cursor-pointer"><span className="font-mono text-[11.5px] text-muted">{e.faq_id}</span> <strong>{e.question}</strong> <Badge tone="neutral" className="ml-1">{e.topic}</Badge> {e.team && <Badge tone="gold">{e.team}</Badge>}</summary>
                  <p className="mt-1.5">{e.answer}</p>
                  <p className="mt-1 text-[12px] text-muted">Source: {e.source}</p>
                  <Button size="sm" variant="ghost" className="mt-1" onClick={() => openAssistant(e.question)}>Ask this</Button>
                </details>
              ))}
            </div>
          )}
        </Section>
      </TabsContent>
    </Tabs>
  );
}

function CoordinatorQueue() {
  const questions = useQuery({ queryKey: ["assistant-q"], queryFn: () => assistant.questions() });
  const pending = useQuery({ queryKey: ["assistant-pending"], queryFn: () => assistant.entries("pending") });
  const action = useAction();
  const [draft, setDraft] = useState<{ question_id?: string; topic: string; question: string; answer: string } | null>(null);
  const open = (questions.data ?? []).filter((q) => q.status === "open");
  const closed = (questions.data ?? []).filter((q) => q.status !== "open");
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Section icon={<Inbox className="h-4 w-4" />} title={`Handed-over questions (${open.length})`} subtitle="No approved answer, a policy topic, or low confidence">
        {open.length === 0 && <p className="text-[13px] text-muted">Nothing waiting.</p>}
        <div className="space-y-3">
          {open.map((q) => (
            <div key={q.question_id} className="rounded-ctl border border-line p-3 text-[13px]">
              <div className="flex flex-wrap items-center gap-2"><strong>{q.question_id}</strong> “{q.question}” {q.count > 1 && <Badge tone="warn">asked {q.count}×</Badge>}</div>
              <p className="mt-1 text-[12px] text-muted">{q.asked_by_role}{q.student_id ? ` · ${q.student_id}` : ""} · {fmtDate(q.last_asked_at)} · {q.reason}</p>
              <div className="mt-2 grid gap-2">
                <InlineForm label="Reply to the student" button="Send reply" pending={action.pending} onSubmit={(t) => action.run(() => assistant.reply(q.question_id, t), "Reply sent")} />
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => setDraft({ question_id: q.question_id, topic: "", question: q.question, answer: "" })}>Write an approved answer</Button>
                  <Button size="sm" variant="ghost" onClick={() => action.run(() => assistant.dismiss(q.question_id), "Dismissed")}>Dismiss</Button>
                </div>
              </div>
            </div>
          ))}
        </div>
        {closed.length > 0 && <details className="mt-3 text-[13px]"><summary className="cursor-pointer text-muted">Closed ({closed.length})</summary>
          <ul className="mt-2 space-y-1">{closed.map((q) => <li key={q.question_id}><StatusBadge status={q.status} /> {q.question} {q.reply && <span className="text-muted">— {q.reply}</span>}</li>)}</ul></details>}
      </Section>
      <div className="space-y-5">
        {draft && (
          <Section title="New answer (pending until approved)" subtitle={draft.question_id ? `Answers ${draft.question_id}` : undefined}>
            <div className="space-y-2">
              <Field label="Topic"><Input value={draft.topic} onChange={(e) => setDraft({ ...draft, topic: e.target.value })} maxLength={40} /></Field>
              <Field label="Question"><Input value={draft.question} onChange={(e) => setDraft({ ...draft, question: e.target.value })} maxLength={150} /></Field>
              <Field label="Approved answer" hint="No personal information. Max 500 characters."><TextArea value={draft.answer} onChange={(e) => setDraft({ ...draft, answer: e.target.value })} maxLength={500} /></Field>
              <div className="flex gap-2">
                <Button variant="primary" size="sm" disabled={action.pending} onClick={() => action.run(() => assistant.addEntry(draft), "Saved as pending", () => setDraft(null))}>Save as pending</Button>
                <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>Cancel</Button>
              </div>
            </div>
          </Section>
        )}
        <Section title={`Pending answers (${pending.data?.length ?? 0})`} subtitle="The assistant never uses an answer until it is approved">
          {(pending.data ?? []).length === 0 && <p className="text-[13px] text-muted">None.</p>}
          <div className="space-y-2">
            {pending.data?.map((e) => (
              <div key={e.faq_id} className="rounded-ctl border border-line p-3 text-[13px]">
                <div><span className="font-mono text-[11.5px] text-muted">{e.faq_id}</span> <strong>{e.question}</strong> · {e.topic}</div>
                <p className="mt-1">{e.answer}</p>
                <div className="mt-2 flex gap-2">
                  <Button variant="primary" size="sm" disabled={action.pending} onClick={() => action.run(() => assistant.approve(e.faq_id), "Approved: the assistant uses it now")}>Approve</Button>
                  <Button size="sm" variant="ghost" onClick={() => action.run(() => assistant.discard(e.faq_id), "Discarded")}>Discard</Button>
                </div>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  );
}
