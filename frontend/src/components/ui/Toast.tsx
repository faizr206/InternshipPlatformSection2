import * as RT from "@radix-ui/react-toast";
import { AlertCircle, CheckCircle2 } from "lucide-react";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

interface ToastMsg {
  id: number;
  title: string;
  description?: string;
  tone?: "ok" | "error";
}

const Ctx = createContext<(t: Omit<ToastMsg, "id">) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastMsg[]>([]);
  const push = useCallback((t: Omit<ToastMsg, "id">) => setToasts((xs) => [...xs, { ...t, id: Date.now() + Math.random() }]), []);
  return (
    <Ctx.Provider value={push}>
      <RT.Provider swipeDirection="right" duration={3500}>
        {children}
        {toasts.map((t) => (
          <RT.Root
            key={t.id}
            onOpenChange={(o) => !o && setToasts((xs) => xs.filter((x) => x.id !== t.id))}
            className="flex items-start gap-3 rounded-card border border-line bg-surface p-3.5 shadow-pop animate-fade-in"
          >
            {t.tone === "error" ? (
              <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-bad" aria-hidden />
            ) : (
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-ok" aria-hidden />
            )}
            <div>
              <RT.Title className="text-sm font-semibold">{t.title}</RT.Title>
              {t.description && <RT.Description className="text-[13px] text-muted">{t.description}</RT.Description>}
            </div>
          </RT.Root>
        ))}
        <RT.Viewport className="fixed right-4 bottom-4 z-[60] flex w-[340px] max-w-[calc(100vw-2rem)] flex-col gap-2 outline-none" />
      </RT.Provider>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
