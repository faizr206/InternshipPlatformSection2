# Integration plan and task board

Merging the three team prototypes into one Coop Platform: one FastAPI + SQLite backend, one React UI,
live handoffs between modules. Rules for how to work are in [`../AGENTS.md`](../AGENTS.md).

**How to use this file:** pick an unchecked task, write your name in the `Owner` column (or after the
task) in the same PR, tick it when merged. Keep it short; details go in the PR.

_Last updated: 27 Nov 2026._

## Why

The binder says there is **one integrated IPP product**, Sprint 4 asks for an integrated
demonstration, and the professor asked that the app "look unified". Before this repo, P01–P03 and
P06/P07 were browser-only apps (localStorage) and handoffs were JSON files and mocks.

## Decisions (agreed 24 Nov)

- **One backend, one UI.** P01–P03 and P06/P07 rules move from browser JS into FastAPI modules on the
  shared SQLite database. Handoffs become calls inside one transaction, and each one still writes a
  handoff record that can be exported as JSON (contract evidence).
- **Frontend:** React 18 + Vite + TS + Tailwind v4, Coop blue palette (navy `#0C2840`, blue `#144673`,
  gold `#D9BA82`), navy sidebar layout, owner chip on every page.
- **History kept:** the three repos are under `legacy/` via `git subtree` (read-only).
- **Six simulated roles:** student, employer (P02 HR + P04 reviewer), coordinator (P03, P04 confirm,
  P05 corrections, P06 gaps, FAQ admin), reviewer (P06 evidence + P05 skill review), supervisor, advisor.

## Target demo: Layla's thread end to end

1. Employer submits OP-0xx → coordinator returns it → employer resubmits v2 → approve → publish (P02/P03)
2. Layla's profile v2 (P01) → OP-028 recommended with a Jira evidence gap (P05)
3. Applies → interview → offer → accepts: *awaiting university confirmation* (P04)
4. Gap → **Prepare** → Jira module, board task, evidence → reviewer asks for revision → demonstrated (P06)
5. → P01 profile v3 with reviewed Jira → matching reruns, gap closed, v2 run kept (P05-07)
6. Coordinator confirms PL-0001 → P07 placement appears → advisor assigned → agreement signed →
   log revised → midpoint action → final review (P07)
7. Assistant answers an FAQ, hands off a pay question, coordinator approves a new answer

## Status

| # | Step | Status | Owner |
|---|---|---|---|
| 1 | Repo bootstrap: team histories, CI, CODEOWNERS | ✅ Done | Faiz |
| 2 | Backend core + P04/P05 moved into modules (108 tests) | ✅ Done | Faiz |
| 3 | P01–P03 ported: profiles, submission, review, publish, close (37 tests) | ✅ Done | Faiz |
| 4 | P06/P07 ported to the backend + demo scenarios (22 + 7 tests) | ✅ Done | Faiz |
| 5 | Live handoffs + one co-op assistant + home endpoints (33 tests) | ✅ Done | Faiz |
| 6 | Frontend shell + design system (mock API, 22 tests) | ✅ Done | Faiz |
| 7 | Frontend screens per module | ⬜ Not started | |
| 8 | End-to-end tests, demo script, data dictionary v4, deploy | ⬜ Not started | |

Steps 4, 5 (backend) and 7 (frontend) can run in parallel per team. Step 7 pages can start on the
mock API (`src/mocks/handlers.ts`) and switch to the real endpoints when they land.

---

## Step 4: P06/P07 backend (Team P6/P7) ✅

Done 27 Nov: `backend/app/modules/preparation`, `progress`, `demo` (scenarios are built through the real
endpoints, so loading one is also a regression test). API: `/api/p06/*`, `/api/p07/*`, `/api/demo/*`,
`/api/people`, `/api/handoffs`. Tests: `tests/test_p06_preparation.py`, `tests/test_p07_progress.py`,
`tests/integration/test_layla_journey.py`. Remaining follow-up: frontend personas use different names than
the agreed demo people. Switch `frontend/src/lib/personas.ts` to `GET /api/people`.

Source: `legacy/p06-p07-waypoint/source/src/` (`app.js`, `data.js`, `ai_engine.js`, `ai_data.js`).
Waypoint keeps everything in one localStorage object and hard-codes COOP-B001: generalise to `student_id`,
use snake_case, and store records in new tables in `backend/app/db.py`.

### P06 preparation (`backend/app/modules/preparation/`)
| Task | Source | Owner |
|---|---|---|
| ✅ Module catalogue: MOD-JIRA-101 full (outcome, resource, practice task, checklist); SQL and VIZ outlines. Seed in `app/seed/p06/` | `data.js:17-57` | |
| ✅ Preparation plan per student: list of gaps (source P05 / manual / match), open/closed | `data.js:124-137`, `pagePlan` `app.js:193` | |
| ✅ Mark resource done. **Never** marks the skill demonstrated (P06 AC2) | `app.js:1087` | |
| ✅ Jira practice board: add item (≥8 chars), move with owner + reason (≥3 words) | `app.js:1137-1140` | |
| ✅ Evidence submission (≥25 words), versioned snapshots | `app.js:1142` | |
| ✅ Reviewer decision: demonstrated (all checklist items ticked) / revision / not_yet (comment required) | `app.js:1149` | |
| ✅ Coordinator manual gap; duplicate open gap for same skill blocked | `app.js:1159` | |
| ✅ Tests: port `source/tests/acceptance_test.py` P06-AC1..4, P06-X, P06-EXC as API tests | | |

### P07 co-op progress (`backend/app/modules/progress/`)
| Task | Source | Owner |
|---|---|---|
| ✅ Placement record (from P04 confirmation), assign academic advisor (coordinator) | `placementFromP04` `data.js:101-111`, `app.js:1217` | |
| ✅ Learning agreement: 3 goals → outcomes LO1–LO4; student/supervisor/advisor sign-off, locks when all signed; advisor can't sign before assignment | `app.js:513`, `app.js:1097` | |
| ✅ Logbook: submit (≥8 words, evidence refs), supervisor acknowledge / request detail, student revise (text must change), history kept | `app.js:540`, `1169-1180` | |
| ✅ Milestones (supervisor ticks) | `app.js:1129` | |
| ✅ Outcome judgements (evidence required unless level "none"); missing evidence shown | `app.js:582`, `1184` | |
| ✅ Actions with owner, due date, closure evidence; overdue uses the demo date | `app.js:1187-1191` | |
| ✅ Employer feedback (≥10 words) separate from advisor final review; no "achieved" without in-period or P06 evidence | `app.js:628`, `1194-1196` | |
| ✅ Tests: port acceptance P07-AC1..4, P07-X, P07-EXC | | |

### Demo scenarios and clock (`backend/app/modules/demo/`, shared)
| Task | Source | Owner |
|---|---|---|
| ✅ `GET /api/demo/settings`, `PUT /api/demo/today`, `POST /api/demo/reset?scenario=fresh\|reviewed\|midpoint\|end` (rebuild DB from seed + scenario fixtures) | `PRESETS` `data.js:139-305` | |
| ✅ Retire the `faculty` role alias once the frontend uses `reviewer` | `profiles/router.py` | |

## Step 5: live handoffs + assistant

| Task | Detail | Owner |
|---|---|---|
| ✅ **P05 → P06:** "Prepare →" on a gap creates the P06 gap/plan item directly (replaces file import + `seed/p06/p06_activities.json`). Keep waypoint's checks: versions current, skill has a module, no duplicate | `importGaps` `app.js:403-422`; `matching/router.py` `handoff_gap` | |
| ✅ **P06 → P01 → P05:** reviewer "demonstrated" → new P01 profile version with `evidence_status: reviewed`, `evidence_id`, reviewer, date → automatic rematch (P05-07) | `profiles/router.py` `update_profile` | |
| ✅ **P04 → P07:** confirming a placement creates the P07 placement once (idempotent); replaces the mock outbox but keeps `p07_handoffs` as the record | `applications/router.py` `confirm_placement`; `importPlacements` `app.js:423-442` | |
| ✅ **P06 → P07:** readiness summary shown in P07 progress | `readinessPayload` `app.js:1071` | |
| ✅ `GET /api/handoffs` + JSON export of every handoff record (Records page) | | |
| ✅ **Assistant** (`modules/assistant/`, P06-owned): port the retrieval engine (IDF ranking, threshold 0.45, privacy + sensitive-topic guards) to Python | `ai_engine.js`, `ai_data.js` | |
| ✅ Merge FAQ corpora: waypoint 12 entries + P01–P03 `data/faq.txt` 8 entries, de-duplicated, source noted | `legacy/p01-p03-ipp/data/faq.txt` | |
| ✅ Coordinator loop: unanswered questions → write answer (pending) → approve → used | `legacy/p01-p03-ipp/src/faq.js:285-443` | |
| ✅ Optional LLM via OpenRouter when `OPENROUTER_API_KEY` is in `.env` (strict JSON, cited FAQ IDs only); otherwise retrieval-only | `legacy/p06-p07-waypoint/source/server.py` | |
| ✅ `tests/integration/test_layla_journey.py`: the whole target demo above, plus negatives (closed listing, duplicate application, unconfirmed placement, gap for a skill without a module, stale profile version) | | |

## Step 7: frontend screens (each team builds its own pages)

The shell, nav, role switcher, Home and assistant drawer exist. Pages are placeholders in
`frontend/src/pages/ModulePage.tsx`. Add real pages under `frontend/src/pages/<module>/`, add types and
hooks in `src/api/`, and extend the mock handlers until the endpoint exists.

**Endpoints the shell already calls but the backend doesn't have yet** (shared, do first):
- [x] `GET /api/home/journey/{student_id}`: 7 stages P01→P07 for the tracker
- [x] `GET /api/home/todos?role=&student_id=`: per-role to-do list
- [x] `GET /api/home/counts?role=&student_id=`: sidebar badges
- [x] `GET /api/events?student_id=`: filter the feed by student
- [x] `/api/demo/*` (settings, today, reset) and `POST /api/assistant/ask`

| Team | Pages | Owner |
|---|---|---|
| P01–P03 | ⬜ Student profile editor with version history and evidence badges · ⬜ Coordinator profile review · ⬜ Employer opportunity form with live preview, versions, returned reason · ⬜ Coordinator review queue with checklist, publish, close | |
| P04/P05 | ⬜ Explore catalogue + filters · ⬜ Recommendation cards (rules score, AI ring, why/gaps/unknowns, AI panel; see `legacy/p04-p05-coop/artifacts/Sprint 2 - AI assistant.png`) · ⬜ Apply dialog with AI draft · ⬜ Application tracker + timeline · ⬜ Employer applicant queue (decisions, interview, offer) · ⬜ Coordinator: placement confirmation, corrections | |
| P06 | ⬜ Preparation plan · ⬜ Jira module + practice board · ⬜ Evidence submission · ⬜ Reviewer queue with checklist · ⬜ Coordinator gaps | |
| P07 | ⬜ Placement + advisor assignment · ⬜ Learning agreement + sign-off · ⬜ Logbook (student / supervisor) · ⬜ Progress, judgements, actions · ⬜ Final review | |
| Shared | ⬜ Records page (handoffs + events, JSON export) · ⬜ Assistant drawer on the real API · ⬜ Coordinator FAQ approvals | |

## Step 8: finish

- [ ] Playwright e2e for the target demo (both Sprint 3 journeys + P01–P03 + P06/P07), run in CI
- [ ] `docs/demo-script.md`: click-by-click script for the final presentation
- [ ] `docs/data-dictionary.md` v4: one dictionary for all modules (start from `legacy/p04-p05-coop/docs/data-dictionary.md`)
- [ ] `scripts/demo.sh`: build frontend → uvicorn serves it → ngrok (adapt `legacy/p04-p05-coop/scripts/demo.sh`)
- [ ] Accessibility pass: 375px width per role, keyboard, screen reader, contrast (open Sprint 3 retro action)
- [ ] Merge `integration/bootstrap` into `main`; protect `main` (CI required)

## Definition of done (every task)

- Code in the owning module; rules from the legacy source kept or a deliberate change noted in the PR
- Tests for each acceptance criterion; `uv run pytest` and frontend typecheck/test/build green in CI
- Actions logged with `log_event`; no seed record edited; no supervisor contact in student views
- UI uses tokens only, shows the owner chip, works at 375px
- PLAN.md ticked, README status updated when a step finishes

## Open questions (raise at Scrum of Scrums)

- Who is the tiebreaker for shared changes to `core/`, `db.py` and `tokens.css`? (proposal: one rep per team must approve)
- Keep the P04/P05 live job feeds (Remotive, Arbeitnow, Remote OK, Jobicy) in the integrated demo, or behind a toggle?
- Botpress chatbot: dropped in favour of the merged assistant. Confirm with P01–P03.
- Assistant: P01–P03's approved answers on remote work and working abroad (FAQ-13, FAQ-14) now answer those
  questions, so they are no longer handed to the coordinator as waypoint did. Confirm both teams agree.
- Final hosting: ngrok from one laptop, or a free host (Render/Fly) for the presentation?
