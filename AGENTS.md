# AGENTS.md: working on the Coop Platform

Read this first, whether you are a teammate or an AI coding agent (Claude Code, Codex, Cursor, …).
It says how the repo is organised, the rules every change must follow, and where to find the work
that is left. **Open tasks and their status live in [`docs/PLAN.md`](docs/PLAN.md).**

## What this is

One integrated app for the BUS2010 Internship Practicum Platform, merging three team prototypes:

| Team | Projects | Modules here |
|---|---|---|
| P01–P03 | Student profiles · employer submission · university review/publication | `profiles`, `submissions`, `review` |
| P04/P05 | Discovery and application tracking · AI-assisted matching | `applications`, `matching` |
| P06/P07 | Internship preparation (LMS) · co-op learning progress · co-op assistant | `preparation`, `progress`, `assistant` |
| Shared | Demo date, scenarios, people, handoff records · home journey/to-dos | `demo`, `home` |

The demo thread: Layla Hassan (`COOP-B001`) and the Emirates Group listing `OP-028`. All records are
**synthetic**; roles are **simulated** (no login).

## Repo layout

```
backend/            FastAPI + SQLite (Python ≥3.12, uv)
  app/main.py       app factory: includes each module router, serves frontend/dist
  app/db.py         ONE schema for all modules, seed loading, additive migrations
  app/core/         shared helpers: now(), require_role(), get_student(), get_opportunity(),
                    next_id(), log_event(), record_handoff(), today() (demo date), actor()
  app/modules/<m>/  router.py (+ service.py) per module, owned by its team (.github/CODEOWNERS)
  app/seed/         seed data: p01p03/ (P01–P03 export), p06/, fixtures/ (test set)
  tests/            pytest, one file per module/story group
frontend/           React 18 + Vite + TS + Tailwind v4 + TanStack Query (see frontend/README.md)
  src/api/          typed client; src/mocks/ is an in-memory API used while endpoints are missing
  src/lib/nav.ts    nav items, owner chips, which roles see what
  src/styles/tokens.css   the ONLY place colours/fonts are defined (Coop blue palette)
legacy/             the 3 original repos with full git history. READ-ONLY reference for porting.
docs/PLAN.md        roadmap, status and open tasks
```

## Commands

```bash
scripts/dev.sh                       # backend :8000 + frontend :5173 (add --reset for fresh data)
cd backend && uv sync && uv run pytest
cd backend && uv run uvicorn app.main:app --reload     # API docs at http://127.0.0.1:8000/docs
cd frontend && npm install && npm run dev               # mock API by default
cd frontend && VITE_USE_MOCKS=false npm run dev         # use the real backend
cd frontend && npm run typecheck && npm test && npm run build
```

CI (`.github/workflows/ci.yml`) runs the backend tests and the frontend typecheck/test/build on
every push and PR. **Both must be green before merging.**

## Rules for every change

These come from the course binder and the contracts the teams agreed at Scrum of Scrums. Breaking
one is a bug even if tests pass.

1. **Stay in your module.** Put code in `backend/app/modules/<module>/` and the matching frontend
   pages. Changes to `core/`, `db.py`, `main.py`, CI or `tokens.css` affect every team: say so in
   the PR and ask another team's owner to review.
2. **Never overwrite another module's records.** Changes are new versions:
   - profiles → new row in `profile_revisions` (`core.new_profile_version`);
   - listings → `listings` row + archived copy in `listing_versions`;
   - seed tables (`students`, `opportunities`) are reloaded from `app/seed/` on every start and
     must never be edited at runtime.
   Earlier versions, recommendation runs and decisions stay queryable.
3. **Simulated roles.** Every mutating endpoint takes `actor_role` (and optional `actor_name`) in the
   body and calls `require_role()`. Roles: `student`, `employer`, `coordinator`, `reviewer`
   (faculty/learning reviewer; `faculty` is still accepted for old tests), `supervisor`, `advisor`.
   Wrong role → 403 with a clear message.
4. **Log what happened.** Call `log_event(conn, module, actor_role, actor_name, action, text, ref)` on
   every state change so the activity feed (`GET /api/events`) shows who did what to which record.
5. **snake_case field names** from the shared data dictionary (`legacy/p04-p05-coop/docs/data-dictionary.md`,
   v3; becomes `docs/data-dictionary.md` v4). Shared skill IDs only: `SK-JIRA, SK-SQL, SK-VIZ, SK-PY,
   SK-EXCEL, SK-FIGMA, SK-COMM, SK-DMKT` (`app/seed/fixtures/skills.json`).
6. **Privacy:** `supervisor_name` / `supervisor_contact` never reach a student view
   (`core.student_view`). No real personal data, ever.
7. **Status rules are explicit.** Invalid transitions return 409 with the allowed next steps; missing
   required input returns 422 (field errors as `{"message", "errors": {field: text}}`).
8. **AI is bounded and labelled.** The rules result is the decision baseline; AI never changes
   eligibility, score, gaps or unknowns, and never invents qualifications. Label it in the UI.
9. **One test per acceptance criterion**, named after the story where possible
   (`test_p04_06_ac2_repeat_confirmation_is_idempotent`). Keep all existing tests green.
10. **Frontend:** colours and fonts only from `tokens.css` utilities (`bg-navy`, `text-muted`, …);
    every page shows its owner chip (`P01`…`P07`); the synthetic-data banner stays on every page;
    keep text contrast WCAG AA (gold is never text on white: use `text-gold-ink`).
11. **No secrets in git.** `.env` is ignored; commit only `.env.example`. The optional OpenRouter key
    for the assistant goes in `backend/.env` (see `backend/.env.example`). Tests must never call the real model.

## Gotchas

- **Demo date:** P06/P07 business dates (log dates, due dates, overdue, review periods) use `core.today(conn)`,
  the demo clock set by `PUT /api/demo/today` or a scenario, not the real date. Audit timestamps use `now()`.
- **Scenarios** (`POST /api/demo/reset?scenario=fresh|reviewed|midpoint|end`) are built in
  `modules/demo/scenarios.py` by calling the real endpoints. If you change a rule and a scenario stops
  loading, fix the scenario step or the rule; the integration tests will fail until you do.
- **Live handoffs** run in the caller's transaction and always write a `handoffs` record
  (`core.record_handoff`). Don't bypass them with direct inserts into another module's tables.

- The root `.gitignore` started as GitHub's Python template. Its `lib/` rule once hid
  `frontend/src/lib/` from git; it is now anchored to `/lib/`. If CI can't find a file you have
  locally, run `git check-ignore -v <path>`.
- `init_db()` reloads seed students/listings on every start. Platform changes live in their own
  tables (`profile_revisions`, `listings`, …) that take precedence when their version is ≥ the seed's.
- Tests use `DATA_SOURCE=fixtures` by default (`tests/conftest.py`, 6 students / 6 listings). Set
  `DATA_SOURCE=p01p03` in a test's client fixture for the real P01–P03 export (4 students, OP-028…OP-039).
- IDs are generated with `core.next_id()` (e.g. `OP-040` after the seed's `OP-039`), never by `COUNT(*)`
  in new code.
- `legacy/` is reference only: don't edit it or import from it.

## How to pick up work

1. Open [`docs/PLAN.md`](docs/PLAN.md) and choose an unchecked task in your module (or a shared one).
2. Put your name next to it in PLAN.md in the same PR (or tell the team) so two people don't take it.
3. Branch from `main` (or `integration/bootstrap` until it is merged): `git checkout -b p06/jira-module`.
4. Port the rules from `legacy/<team>/…` (PLAN.md gives the source file and lines), add tests, run CI
   locally, open a PR, get one review, merge when green.
5. Tick the task in PLAN.md and update the status table in `README.md` when a step completes.
