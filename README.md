# Coop Platform: P04 + P05

Working prototype for **Project 4 (Discovery & Application Tracking)** and
**Project 5 (AI-assisted Matching)**. One app that runs end to end
(screen → API → rules + bounded-AI logic → SQLite), organised as four
**simulated role views**: Student, Employer reviewer, University coordinator
and Faculty reviewer.

> **Sprint 1 (walking skeleton):** Layla (COOP-B001) gets rules-based
> recommendations with reasons, gaps and unknowns, opens a published opportunity
> (OP-028), submits an application and sees **Submitted** / **Not placed** —
> still there after a reload.
>
> **Sprint 2 (response and revision):** Layla saves and refines a **draft** before
> submitting. A simulated **employer reviewer** moves her application through
> *Under review → Shortlisted/Declined* with visible actor, timestamp and next
> action (declines need a reason; a declined application can never receive an
> offer). A bounded, labelled **AI term-matching** feature runs *alongside* the
> unchanged rules baseline. A **coordinator** can inspect a flagged
> recommendation, record a **correction request** for the owning module (P01/P03)
> and apply profile corrections as a **new input version**, then rematch — the
> original recommendation stays traceable.

Stories: Sprint 1 — P05-01, P05-02, P05-03, P04-01, P04-03.
Sprint 2 — P05-04, P05-05, P04-02, P04-04.

## Run

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. The API docs are at http://127.0.0.1:8000/docs.
To reset the demo data, stop the server and delete `app.db`.

### Student design preview

Open http://127.0.0.1:8000/student-preview for the redesigned catalogue. It includes the
example employers, employer badges, listing photos, advanced filters, and the draggable
career assistant. All preview actions and chat input stay in the browser for the current
page session. The preview does not call an AI service or write to SQLite. The original
four-role app remains available at the root URL.


### Public demo (ngrok)

```bash
scripts/demo.sh            # runs the tests, starts the app, opens the ngrok tunnel
scripts/demo.sh --reset    # same, starting from fresh demo data
scripts/demo.sh --local    # app only, no ngrok
```

Needs ngrok set up once (`ngrok config add-authtoken <token>`). The public link is
`https://$NGROK_DOMAIN` (defaults to the static domain on the Sprint 1 slides). Ctrl+C stops both.

## Test

```bash
uv run pytest
```

## Layout

| Path | What |
|---|---|
| `app/fixtures/*.json` | Synthetic profiles (stand-in for P01), listings incl. descriptions (stand-in for P03), the shared skill vocabulary and the P05 alias map |
| `app/db.py` | SQLite schema + additive migrations; loads fixtures when the DB is empty/started |
| `app/matching.py` | Rules baseline engine (`rules-v2`) |
| `app/ai.py` | Bounded AI: skill-term matching (`ai-termmatch-v1`) and recommendation insights (`ai-insights-v1`) |
| `app/rules.json` | Editable rules: mandatory conditions and preference weights |
| `docs/data-dictionary.md` | Records, statuses, transitions and API contract (v2) |
| `docs/acceptance.md` | Sprint 1 + 2 acceptance results per story |
| `app/main.py` | FastAPI routes incl. drafts, decisions, corrections, role guards |
| `app/static/index.html` | UI: sidebar with the four simulated role views |

## Matching rules (rules-v2)
- Only `published` + `open` listings can be recommended.
- **Mandatory:** the student's availability must cover the opportunity dates. Eligibility is
  `eligible` when dates are covered, `ineligible` for a conflict, or `unknown` when any date is
  missing or empty. Only `eligible` results have `compatible: true`.
- Results rank by eligibility (`eligible`, then `unknown`, then `ineligible`), followed by score
  descending and opportunity ID. The interface shows unknown eligibility as "Eligibility needs checking".
- **Preferences:** a sector in the student's interests adds 3, each required skill held adds 2,
  each desirable skill held adds 1.
- Missing required skills are listed as **gaps**. Self-declared skills are never labelled as reviewed.

## Bounded AI assistance (ai-termmatch-v1)
- A deterministic, offline skill-term matcher: it finds terms in the listing title/description
  (e.g. "Tableau dashboards") that are equivalent to a skill the student already holds
  (e.g. `SK-VIZ`), using the alias map in `app/fixtures/skill_aliases.json` (P05-owned fallback
  pending Scrum-of-Scrums agreement on the shared vocabulary).
- Each match cites the **term**, the **field** it was found in, the **skill** and the student's
  **evidence status**; the method version is stored alongside the separate rules result.
- It **never** changes eligibility, score, gaps or unknowns, and never invents qualifications —
  it can only map terms to skills already on the profile. Labelled "simulated AI" in the UI;
  the rules baseline stays usable on its own.

## AI recommendation insights (ai-insights-v1)
Stored with each run in `recommendations.ai_insights`, under the same bounds (offline,
deterministic, labelled, never changes the rules result or ranking):
- **AI relevance (0–100%)** — TF-IDF cosine similarity between the profile text (interests,
  skills and their aliases) and the listing text, with the top contributing terms. The UI can
  order cards by it as a *view-only* option; the stored rules ranking is unchanged.
- **Summary** — a plain-language restatement of the rules result (a mandatory conflict is never softened).
- **Next steps** — missing skills ranked by the points the rules would add (and how many other
  open listings require them); self-declared required skills get a "get it reviewed" step.
- **Similar open listings** — Jaccard similarity on skills + sector.
- **Draft with AI** — `POST /api/ai/statement-draft` returns a starter statement for the apply
  dialog. It cites only skills already on the profile and saves or submits nothing.

## Application lifecycle (P04)
`Draft → Submitted → Under review → Shortlisted | Declined`
- Drafts keep the entered statement; the statement is required at submission (a missing one
  gives a useful error and preserves the draft).
- Active statuses (duplicate check): Submitted, Under review, Shortlisted.
- Every change stores an event with actor, reason (required for declines) and next action.
- `Declined` is terminal this sprint; offers (P04-05) arrive in Sprint 3 and never follow a decline.
- Placement status is shown separately and stays **Not placed** until a coordinator confirms
  (P04-06, Sprint 3).

## Corrections (P05-05)
A student flags a recommendation (reason + affected field). The coordinator sees the input
versions used, records the request for the owning module (P01/P03) and — for profile
corrections (availability, interests) — applies it as a **new profile version** (the fixture is
never overwritten). A rematch then stores a new run; earlier runs stay queryable
(`/api/students/{id}/recommendation-runs`). Listing and skill-evidence corrections stay
*recorded* until the live owning modules exist.

## Real vs simulated vs deferred
- **Real:** the rules engine, bounded term matching, stored recommendations and runs,
  drafts, submission, the duplicate/closed-listing checks, employer decisions with history and
  transition rules, correction requests with version-traceable rematching, SQLite persistence,
  simulated role enforcement at the API level (403 on the wrong role).
- **Simulated:** role switching (no login — labelled in the sidebar), employer/coordinator
  actors, AI assistance (deterministic, labelled). Profiles and listings come from fixtures,
  not live P01/P03 modules.
- **Deferred:** authentication, offers and acceptance (P04-05), placement confirmation and the
  P07 handoff (P04-06), withdrawal (P04-07), skill-gap → P06 (P05-06), rematching after any
  profile change (P05-07), evaluation against the baseline (P05-08), applying P03/P01-owned
  corrections, deployment.
