# Coop Platform: integrated IPP (P01–P07)

One app for the BUS2010 Internship Practicum Platform, built by three teams:

| Team | Projects | Original repository | Module folders |
|---|---|---|---|
| P01–P03 | Student profiles, employer submission, university review and publication | [ray-suton/ipp-walking-skeleton-demo](https://github.com/ray-suton/ipp-walking-skeleton-demo) | `backend/app/modules/profiles`, `submissions`, `review` |
| P04/P05 (S2 Team 3) | Discovery and application tracking, AI-assisted matching | [faizr206/ProjectManagement-AIRecommendation](https://github.com/faizr206/ProjectManagement-AIRecommendation) | `backend/app/modules/applications`, `matching` |
| P06/P07 | Internship preparation, co-op learning progress, co-op assistant | [Lizhengxi25/waypoint](https://github.com/Lizhengxi25/waypoint) | `backend/app/modules/preparation`, `progress`, `assistant` |

Each original repository is imported under `legacy/` with its full git history (`git subtree`), so
every team's work stays traceable. The integrated app is in `backend/` (FastAPI + SQLite) and
`frontend/` (React + Vite + TypeScript). One database means the handoffs between teams are live
calls instead of file exports.

All people, opportunities and records are synthetic. Roles are simulated: there is no login.

## Working on this repo

- **[AGENTS.md](AGENTS.md)**: layout, commands and the rules every change must follow (for teammates and AI agents).
- **[docs/PLAN.md](docs/PLAN.md)**: the integration plan, what is finished and the open tasks per team. Pick a task there.

## Run

Requires [uv](https://docs.astral.sh/uv/) and Node 22.

```bash
scripts/dev.sh            # API on :8000, frontend dev server on :5173
scripts/dev.sh --reset    # same, starting from fresh demo data
```

Or run the pieces yourself:

```bash
cd backend && uv sync && uv run uvicorn app.main:app --reload    # http://127.0.0.1:8000/docs
cd frontend && npm install && npm run dev                          # http://127.0.0.1:5173
```

`npm run build` in `frontend/` writes `frontend/dist`, which the backend serves at
http://127.0.0.1:8000, so the whole platform runs from one process.

**Demo data:** use the date/scenario menu in the top bar, or
`curl -X POST "http://127.0.0.1:8000/api/demo/reset?scenario=midpoint"`. Scenarios: `fresh` (23 Nov 2026),
`reviewed` (Jira demonstrated, profile v3), `midpoint` (PL-0001 at Emirates Group, week 7), `end` (ready for
the final review). **Assistant model (optional):** copy `backend/.env.example` to `backend/.env` and add an
OpenRouter key; without it the assistant quotes approved answers only.

## Test

```bash
cd backend && uv run pytest
cd frontend && npm run typecheck && npm test && npm run build
```

CI runs both on every push and pull request.

## Layout

| Path | What |
|---|---|
| `backend/app/main.py` | App factory: mounts each module's router and serves the built frontend |
| `backend/app/db.py` | One SQLite schema, seed loading and additive migrations |
| `backend/app/core/` | Shared helpers: simulated roles, profile and listing reads, time |
| `backend/app/modules/<module>/` | One folder per module, owned by its team (see `.github/CODEOWNERS`) |
| `backend/app/seed/` | Synthetic seed data: the P01–P03 export, P06 activities, our test fixtures |
| `backend/tests/` | pytest suites per module, plus cross-team journey tests |
| `frontend/` | The unified UI (Coop Platform blue palette) |
| `legacy/` | The three original team repositories, with history (reference only) |

## Integration status

Details and open tasks: [docs/PLAN.md](docs/PLAN.md).


| Step | Status |
|---|---|
| 1. Repo bootstrap: team histories, CI, CODEOWNERS | Done |
| 2. Backend core + P04/P05 moved into modules | Done |
| 3. P01–P03 rules ported to the backend (profiles, submission, review, publish, close) | Done |
| 4. P06/P07 rules ported to the backend + demo scenarios | Done |
| 5. Live handoffs + one co-op assistant + home endpoints | Done |
| 6. Frontend shell + design system | Done |
| 7. Frontend screens per module | First pass done (every page works on the real API) |
| 8. End-to-end tests, demo script, data dictionary v4 | Planned |
