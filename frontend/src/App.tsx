import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ToastProvider } from "@/components/ui";
import { DemoProvider } from "@/context/DemoContext";
import { NAV_ITEMS } from "@/lib/nav";
import Home from "@/pages/Home";
import ModulePage from "@/pages/ModulePage";
import ApplicationsPage from "@/pages/modules/ApplicationsPage";
import AssistantPage from "@/pages/modules/AssistantPage";
import MatchingPage from "@/pages/modules/MatchingPage";
import OpportunitiesPage from "@/pages/modules/OpportunitiesPage";
import PlacementPage from "@/pages/modules/PlacementPage";
import PreparationPage from "@/pages/modules/PreparationPage";
import ProfilePage from "@/pages/modules/ProfilePage";
import RecordsPage from "@/pages/modules/RecordsPage";
import type { NavKey } from "@/api/types";
import type { ComponentType } from "react";

/** The real page for each nav item; ModulePage guards access for roles that don't see the item. */
const PAGES: Partial<Record<NavKey, ComponentType>> = {
  profile: ProfilePage, opportunities: OpportunitiesPage, applications: ApplicationsPage, matching: MatchingPage,
  preparation: PreparationPage, placement: PlacementPage, assistant: AssistantPage, records: RecordsPage,
};
import NotFound from "@/pages/NotFound";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Home />} />
        {NAV_ITEMS.filter((i) => i.path !== "/").map((item) => (
          <Route key={item.key} path={item.path.slice(1)} element={<ModulePage item={item} page={PAGES[item.key]} />} />
        ))}
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

export function Providers({ children, client }: { children: ReactNode; client?: QueryClient }) {
  const [qc] = useState(
    () => client ?? new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 } } }),
  );
  return (
    <QueryClientProvider client={qc}>
      <DemoProvider>
        <ToastProvider>{children}</ToastProvider>
      </DemoProvider>
    </QueryClientProvider>
  );
}

export default function App() {
  return (
    <Providers>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppRoutes />
      </BrowserRouter>
    </Providers>
  );
}
