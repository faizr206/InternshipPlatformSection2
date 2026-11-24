import { useCallback, useEffect, useMemo, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { Sheet } from "@/components/ui";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { AssistantDrawer } from "./AssistantDrawer";
import { DemoBanner } from "./DemoBanner";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { UICtx } from "./UIContext";

export function AppShell() {
  const [navOpen, setNavOpen] = useState(false);
  const [assistant, setAssistant] = useState<{ open: boolean; seed?: string }>({ open: false });
  const { pathname } = useLocation();

  useEffect(() => setNavOpen(false), [pathname]);

  const openAssistant = useCallback((seed?: string) => setAssistant({ open: true, seed }), []);
  const ui = useMemo(() => ({ openAssistant }), [openAssistant]);

  return (
    <UICtx.Provider value={ui}>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[70] focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2 focus:shadow-pop"
      >
        Skip to content
      </a>
      <div className="min-h-dvh nav:grid nav:grid-cols-[var(--spacing-sidebar)_1fr]">
        <aside className="sticky top-0 hidden h-dvh nav:block" aria-label="Sidebar">
          <Sidebar />
        </aside>
        <Sheet open={navOpen} onOpenChange={setNavOpen} side="left" title="Navigation">
          <Sidebar onNavigate={() => setNavOpen(false)} />
        </Sheet>

        <div className="flex min-w-0 flex-col">
          <div className="z-30 nav:sticky nav:top-0">
            <DemoBanner />
            <TopBar onMenu={() => setNavOpen(true)} />
          </div>
          <main id="main" className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-5 nav:px-7 nav:py-7">
            <ErrorBoundary resetKey={pathname}>
              <Outlet />
            </ErrorBoundary>
          </main>
          <footer className="px-4 pb-6 text-center text-[12px] text-muted nav:px-7">
            Coop Platform · BUS2010 Internship Practicum Platform · integrated build of P01–P07
          </footer>
        </div>
      </div>
      <ErrorBoundary>
        <AssistantDrawer
          open={assistant.open}
          seed={assistant.seed}
          onOpenChange={(open) => setAssistant((a) => ({ open, seed: open ? a.seed : undefined }))}
        />
      </ErrorBoundary>
    </UICtx.Provider>
  );
}
