# Coop Platform — frontend

React 18 + Vite + TypeScript UI for the unified BUS2010 Internship Practicum Platform (P01–P07).
FastAPI (`../backend`) serves the built files from `frontend/dist`.

## Quick start

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 (in-memory mock API by default)
```

| Script | What it does |
| --- | --- |
| `npm run dev` | Vite dev server. `/api/*` is proxied to `http://127.0.0.1:8000`. |
| `npm run typecheck` | `tsc` strict type check, no output. |
| `npm test` | Vitest + Testing Library (jsdom). `npm run test:watch` for watch mode. |
| `npm run build` | Type check, then build to `frontend/dist` for FastAPI to serve. |
| `npm run preview` | Serve the production build locally. |

## Mock API vs real backend

The typed client in `src/api/` sends every request through `request()` in `src/api/client.ts`.
`VITE_USE_MOCKS` picks where it goes:

- unset or `false` (default): real `fetch` to `/api/...`, proxied in dev to uvicorn on port 8000.
- `true`, and always in unit tests: `src/mocks/handlers.ts`, an in-memory fake built from
  `legacy/p01-p03-ipp/data/ipp_sample_data.json` plus per-scenario fixtures. No backend needed.

```bash
npm run dev                          # talk to the FastAPI backend (start it first)
VITE_USE_MOCKS=true npm run dev      # mock API only, no backend
```

Copy `.env.example` to `.env.local` to set it permanently. Endpoints the UI expects
(paths and shapes in `src/api/endpoints.ts` and `src/api/types.ts`):

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/students` | `StudentSummary[]` (latest submitted profile each) |
| GET | `/api/demo/settings` | `{ today, scenario }` |
| PUT | `/api/demo/today` | body `{ today }` → settings |
| POST | `/api/demo/reset?scenario=fresh\|reviewed\|midpoint\|end` | settings |
| GET | `/api/home/journey/{student_id}` | `{ student_id, display_name, stages[7] }` |
| GET | `/api/home/todos?role=&student_id=` | `Todo[]` |
| GET | `/api/home/counts?role=&student_id=` | `{ [navKey]: number }` for sidebar badges |
| GET | `/api/events?limit=&student_id=` | `ActivityEvent[]`, newest first |
| POST | `/api/assistant/ask` | body `{ question, role }` → `{ answer, source, mode, confident }` |

## Structure

```
src/
  styles/tokens.css     design tokens (single source, Tailwind v4 @theme) + contrast notes
  styles/index.css      Tailwind import and base styles
  components/ui/        small wrappers: Button, Badge/OwnerChip, Card, Select, DropdownMenu,
                        Tabs, Sheet (drawer), Toast, EmptyState, Skeleton, Avatar
  components/layout/    AppShell, Sidebar, TopBar, RoleSwitcher/StudentPicker, DemoMenu,
                        DemoBanner, AssistantDrawer
  context/DemoContext   simulated role + selected student, saved to localStorage (`coop-demo-v1`)
  lib/nav.ts            nav items: path, owner chip, roles that see it, journey group
  api/                  types, fetch client, endpoint functions, TanStack Query hooks
  mocks/                in-memory API + fixtures (synthetic only)
  pages/                Home (journey, to-dos, activity) and module placeholders
```

## Design notes

- Palette and type come only from `tokens.css` (`bg-navy`, `text-muted`, `rounded-card`, …).
  Text/background pairs used in the UI are checked against WCAG AA; the ratios are in the file header.
  Gold is never used as text on white (1.9:1); use `text-gold-ink` on light backgrounds.
- Sidebar is 264px; below 820px (`nav:` breakpoint) it becomes a left drawer opened from the top bar.
- Each page shows its owner chip (P01 … P07, or Core) next to the title.
- The "Synthetic data · simulated roles · demo only" banner is rendered by `AppShell`, so every
  route has it. A test checks this.
- Roles are simulated: there is no login. Switching role filters the nav and, if the current page
  isn't part of that role's view, returns to Home.
- Inter is bundled through `@fontsource/inter`, so the app works offline.
