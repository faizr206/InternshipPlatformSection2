/** Small building blocks shared by the module pages. Colours come only from tokens.css utilities. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Loader2 } from "lucide-react";
import { useState, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { p01 } from "@/api/modules";
import { Badge, Card, CardHeader, type Tone } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/lib/cn";

/**
 * Run a backend action: shows a toast and refetches every query on success (a change in one module can move
 * another module's records, e.g. a P06 review creates a P01 profile version), and an error toast on failure.
 */
export function useAction() {
  const qc = useQueryClient();
  const toast = useToast();
  const m = useMutation({
    mutationFn: async (v: { fn: () => Promise<unknown>; ok?: string; onDone?: (r: unknown) => void }) => {
      const result = await v.fn();
      return { result, v };
    },
    onSuccess: async ({ result, v }) => {
      await qc.invalidateQueries();
      if (v.ok) toast({ title: v.ok });
      v.onDone?.(result);
    },
    onError: (error: Error) => toast({ title: "Not done", description: error.message, tone: "error" }),
  });
  return {
    run: (fn: () => Promise<unknown>, ok?: string, onDone?: (r: unknown) => void) => m.mutate({ fn, ok, onDone }),
    pending: m.isPending,
  };
}

export const useSkillNames = () => useQuery({ queryKey: ["skills"], queryFn: p01.skills, staleTime: Infinity });

export function Section({ title, subtitle, action, icon, children, className, bodyClass }: {
  title: ReactNode; subtitle?: ReactNode; action?: ReactNode; icon?: ReactNode; children: ReactNode; className?: string; bodyClass?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader title={title} subtitle={subtitle} action={action} icon={icon} />
      <div className={cn("px-5 py-4", bodyClass)}>{children}</div>
    </Card>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 px-5 py-10 text-sm text-muted" role="status">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> {label}…
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div className="flex items-start gap-2 rounded-ctl border border-bad/20 bg-bad-50 px-3 py-2.5 text-[13px] text-bad" role="alert">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      {error instanceof Error ? error.message : String(error)}
    </div>
  );
}

export function Notice({ tone = "blue", children }: { tone?: "blue" | "warn" | "ok" | "ai"; children: ReactNode }) {
  const tones = { blue: "border-blue-100 bg-blue-50 text-ink", warn: "border-warn/20 bg-warn-50 text-warn", ok: "border-ok/20 bg-ok-50 text-ok", ai: "border-ai-line bg-ai-50 text-ink" };
  return <div className={cn("rounded-ctl border px-3.5 py-2.5 text-[13px]", tones[tone])}>{children}</div>;
}

export function Field({ label, hint, children, className }: { label: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={cn("block", className)}>
      <span className="mb-1 block text-[12.5px] font-semibold text-ink">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[12px] text-muted">{hint}</span>}
    </label>
  );
}

const control = "w-full rounded-ctl border border-line bg-surface px-3 text-sm text-ink outline-none placeholder:text-muted focus:border-blue focus:ring-2 focus:ring-blue/15";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn(control, "h-9", props.className)} />;
}
export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={3} {...props} className={cn(control, "py-2 leading-relaxed", props.className)} />;
}
export function NativeSelect(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cn(control, "h-9 pr-8", props.className)} />;
}

const STATUS_TONES: Record<string, Tone> = {
  // listings
  "Pending review": "warn", Approved: "blue", Published: "ok", Closed: "neutral", "Returned for revision": "warn", Declined: "bad",
  // applications
  Draft: "neutral", Submitted: "blue", "Under review": "blue", Shortlisted: "blue", "Interview scheduled": "ai",
  "Interview completed": "ai", Offered: "gold", "Offer accepted": "ok", "Offer declined": "neutral", Withdrawn: "neutral",
  "Not placed": "neutral", "Awaiting university confirmation": "warn", Confirmed: "ok",
  // profile, P06, P07
  submitted: "blue", clarification_requested: "warn", reviewed: "ok", draft: "neutral", agreed: "ok",
  open: "warn", closed: "ok", revision: "warn", not_yet: "bad", demonstrated: "ok", none: "neutral",
  feedback: "warn", revised: "blue", acknowledged: "ok", developing: "blue", achieved: "ok",
  eligible: "ok", unknown: "warn", ineligible: "bad", self_declared: "neutral", answered: "ok", dismissed: "neutral",
  pending: "warn", delivered: "ok", received: "ok",
};
const LABELS: Record<string, string> = {
  clarification_requested: "Clarification requested", not_yet: "Not yet demonstrated", self_declared: "Self-declared",
  inprogress: "In progress", todo: "To do",
};
export const statusLabel = (s: string) => LABELS[s] ?? (s.length && s === s.toLowerCase() ? s[0].toUpperCase() + s.slice(1) : s);

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  return <Badge tone={STATUS_TONES[status] ?? "neutral"} className={className}>{statusLabel(status)}</Badge>;
}

export function KeyValues({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid gap-x-6 gap-y-2.5 text-[13px] sm:grid-cols-2">
      {items.map(([k, v]) => (
        <div key={k} className="min-w-0">
          <dt className="text-[11.5px] font-semibold tracking-wide text-muted uppercase">{k}</dt>
          <dd className="mt-0.5 break-words">{v ?? <span className="text-muted">—</span>}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Timeline({ items }: { items: { title: ReactNode; meta: ReactNode; body?: ReactNode; tone?: Tone }[] }) {
  return (
    <ol className="relative space-y-3">
      {items.map((it, i) => (
        <li key={i} className="relative flex gap-3">
          {i < items.length - 1 && <span aria-hidden className="absolute top-5 bottom-[-12px] left-[5px] w-px bg-line" />}
          <span aria-hidden className={cn("mt-1.5 h-[11px] w-[11px] shrink-0 rounded-full border-2 border-surface ring-2",
            it.tone === "bad" ? "bg-bad ring-bad/30" : it.tone === "ok" ? "bg-ok ring-ok/30" : it.tone === "warn" ? "bg-warn ring-warn/30" : "bg-blue ring-blue/30")} />
          <div className="min-w-0 flex-1 text-[13px]">
            <div className="font-semibold">{it.title}</div>
            <div className="text-[12px] text-muted">{it.meta}</div>
            {it.body && <div className="mt-1 text-ink/90">{it.body}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}

/** A small inline form: one text field and a submit button (reasons, comments, replies). */
export function InlineForm({ label, placeholder, button, onSubmit, pending, multiline, minWords, variant = "primary" }: {
  label: string; placeholder?: string; button: string; onSubmit: (text: string) => void; pending?: boolean; multiline?: boolean;
  minWords?: number; variant?: "primary" | "secondary";
}) {
  const [text, setText] = useState("");
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  return (
    <form
      className="space-y-2"
      onSubmit={(e) => { e.preventDefault(); onSubmit(text); setText(""); }}
    >
      <Field label={label} hint={minWords ? `${words} of at least ${minWords} words` : undefined}>
        {multiline ? (
          <TextArea value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} />
        ) : (
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder={placeholder} />
        )}
      </Field>
      <button type="submit" disabled={pending || !text.trim()}
        className={cn("inline-flex h-8 items-center rounded-ctl px-3 text-[13px] font-medium disabled:opacity-50",
          variant === "primary" ? "bg-blue text-white hover:bg-navy-2" : "border border-line bg-surface hover:bg-bg")}>
        {button}
      </button>
    </form>
  );
}

export function SkillChip({ id, names, status }: { id: string; names?: Record<string, string>; status?: string }) {
  const tone: Tone = status === "reviewed" ? "ok" : status === "missing" ? "bad" : status ? "neutral" : "blue";
  return (
    <Badge tone={tone} title={id}>
      {names?.[id] ?? id}
      {status && status !== "missing" && <span className="font-normal opacity-80">· {statusLabel(status)}</span>}
    </Badge>
  );
}

export const fmtDate = (d?: string | null) => (d ? new Date(d.length === 10 ? `${d}T00:00:00` : d).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "—");
