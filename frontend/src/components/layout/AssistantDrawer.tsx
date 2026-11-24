import { ArrowUp, BookOpen, Sparkles } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useAskAssistant } from "@/api/hooks";
import type { AssistantAnswer } from "@/api/types";
import { useDemo, roleLabel } from "@/context/DemoContext";
import { Badge, OwnerChip, Sheet, SheetClose } from "@/components/ui";
import { cn } from "@/lib/cn";

type Msg = { id: number; from: "user"; text: string } | { id: number; from: "bot"; answer: AssistantAnswer };

const SUGGESTIONS = [
  "Are placements on site?",
  "Does applying mean I got the placement?",
  "How is an opportunity approved?",
  "Who enters my final grade?",
];

export function AssistantDrawer({
  open,
  onOpenChange,
  seed,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  seed?: string;
}) {
  const { role } = useDemo();
  const ask = useAskAssistant();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  const send = (q: string) => {
    const question = q.trim();
    if (!question || ask.isPending) return;
    setMsgs((m) => [...m, { id: Date.now(), from: "user", text: question }]);
    setText("");
    ask.mutate(
      { question, role },
      { onSuccess: (answer) => setMsgs((m) => [...m, { id: Date.now() + 1, from: "bot", answer }]) },
    );
  };

  useEffect(() => {
    if (open && seed) send(seed);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, seed]);

  useEffect(() => {
    // Braces matter: newer browsers return a Promise from scrollIntoView, and an
    // effect must not return anything but a cleanup function.
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [msgs, ask.isPending]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    send(text);
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange} side="right" title="Assistant" description="Answers from the approved programme FAQ">
      <div className="flex items-center gap-3 border-b border-line px-5 py-4">
        <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-ai to-[#8a5cf6] text-white shadow-sm">
          <Sparkles className="h-[18px] w-[18px]" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="text-[15px] font-semibold">Assistant</h2>
            <OwnerChip owner="P03 · P07" />
          </div>
          <p className="text-[12.5px] text-muted">Approved FAQ answers · asking as {roleLabel(role)}</p>
        </div>
        <SheetClose label="Close assistant" />
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto bg-bg/60 px-5 py-5">
        {msgs.length === 0 && (
          <div className="rounded-card border border-ai-line bg-ai-50 p-4">
            <p className="text-sm font-semibold text-ai">Ask about placements, reviews or grading</p>
            <p className="mt-1 text-[13px] text-ink/80">
              Answers come only from the coordinator-approved FAQ. Anything else is passed to the coordinator — I never guess.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-full border border-ai-line bg-surface px-3 py-1 text-[12.5px] font-medium text-ai hover:bg-ai hover:text-white"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m) =>
          m.from === "user" ? (
            <div key={m.id} className="ml-10 rounded-2xl rounded-br-md bg-blue px-3.5 py-2.5 text-sm text-white">
              {m.text}
            </div>
          ) : (
            <div key={m.id} className="mr-6 rounded-2xl rounded-bl-md border border-line bg-surface px-3.5 py-3 text-sm shadow-sm">
              <p>{m.answer.answer}</p>
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {m.answer.source ? (
                  <Badge tone="blue" className="max-w-full rounded-lg whitespace-normal">
                    <BookOpen className="h-3 w-3 shrink-0" aria-hidden />
                    {m.answer.source}
                  </Badge>
                ) : (
                  <Badge tone="warn">Sent to coordinator</Badge>
                )}
                {!m.answer.confident && m.answer.source && <Badge tone="neutral">Closest match</Badge>}
              </div>
            </div>
          ),
        )}
        {ask.isPending && (
          <div className="mr-6 inline-flex gap-1 rounded-2xl rounded-bl-md border border-line bg-surface px-4 py-3" aria-label="Assistant is typing">
            {[0, 1, 2].map((i) => (
              <span key={i} className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted" style={{ animationDelay: `${i * 120}ms` }} />
            ))}
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form onSubmit={onSubmit} className="border-t border-line bg-surface p-3">
        <div className="flex items-end gap-2 rounded-card border border-line bg-surface p-1.5 focus-within:border-blue">
          <label htmlFor="assistant-input" className="sr-only">
            Your question
          </label>
          <input
            id="assistant-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Ask a question…"
            autoComplete="off"
            className="h-9 min-w-0 flex-1 bg-transparent px-2 text-sm outline-none placeholder:text-muted"
          />
          <button
            type="submit"
            disabled={!text.trim() || ask.isPending}
            aria-label="Send question"
            className={cn("grid h-9 w-9 place-items-center rounded-ctl bg-ai text-white transition-opacity disabled:opacity-40")}
          >
            <ArrowUp className="h-4 w-4" aria-hidden />
          </button>
        </div>
        <p className="mt-1.5 px-1 text-[11.5px] text-muted">Retrieval-only mode · no personal data leaves the demo.</p>
      </form>
    </Sheet>
  );
}
