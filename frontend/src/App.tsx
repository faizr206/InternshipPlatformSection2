import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ToastProvider } from "@/components/ui";
import { DemoProvider } from "@/context/DemoContext";
import { NAV_ITEMS } from "@/lib/nav";
import Home from "@/pages/Home";
import ModulePage from "@/pages/ModulePage";
import NotFound from "@/pages/NotFound";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Home />} />
        {NAV_ITEMS.filter((i) => i.path !== "/").map((item) => (
          <Route key={item.key} path={item.path.slice(1)} element={<ModulePage item={item} />} />
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
