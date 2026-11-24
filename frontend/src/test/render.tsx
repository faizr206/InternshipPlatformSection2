import { QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AppRoutes, Providers } from "@/App";

export function renderApp(path = "/") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  return render(
    <Providers client={client}>
      <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppRoutes />
      </MemoryRouter>
    </Providers>,
  );
}
