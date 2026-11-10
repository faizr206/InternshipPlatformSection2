# Coop Platform: P04 + P05 walking skeleton

Sprint 1 walking skeleton for **Project 4 (Discovery & Application Tracking)** and
**Project 5 (AI-assisted Matching)**. It's one thin slice that runs end to end
(screen → API → rules logic → SQLite):

> Layla (COOP-B001) gets rules-based recommendations with reasons, gaps and unknowns. She opens a
> published opportunity (OP-028), submits an application and sees **Submitted** /
> **Not placed**, and it's still there after a reload.

Stories: P05-01, P05-02, P05-03, P04-01, P04-03.

## Run

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. The API docs are at http://127.0.0.1:8000/docs.
To reset the demo data, stop the server and delete `app.db`.

## Test

```bash
uv run pytest
```

## Layout

| Path | What |
|---|---|
| `app/fixtures/*.json` | Synthetic profiles (stand-in for P01), listings (stand-in for P03), and the skill vocabulary |
| `app/db.py` | SQLite schema; loads the fixtures when the DB is empty |
| `app/matching.py` | Rules baseline engine |
| `app/rules.json` | Editable rules (`rules-v2`): mandatory conditions and preference weights |
| `docs/data-dictionary.md` | Records, statuses and API contract |
| `docs/acceptance.md` | Sprint 1 acceptance results per story |
| `app/main.py` | FastAPI routes |
| `app/static/index.html` | Minimal UI |

## Matching rules (rules-v2)
- Only `published` + `open` listings can be recommended.
- **Mandatory:** the student's availability must cover the opportunity dates. Eligibility is
  `eligible` when dates are covered, `ineligible` for a conflict, or `unknown` when any date is
  missing or empty. Only `eligible` results have `compatible: true`.
- Results rank by eligibility (`eligible`, then `unknown`, then `ineligible`), followed by score
  descending and opportunity ID. The interface shows unknown eligibility as "Eligibility needs checking".
- Existing databases migrate automatically on startup, preserving saved recommendation IDs and
  method versions while correcting eligibility from the original saved assessment.
- **Preferences:** a sector in the student's interests adds 3, each required skill held adds 2,
  each desirable skill held adds 1.
- Missing required skills are listed as **gaps**. Self-declared skills are never labelled as reviewed.

## Real vs simulated vs deferred
- **Real:** the rules engine, stored recommendations, application submission, the duplicate and
  closed-listing checks, and SQLite persistence.
- **Simulated:** student selection (no login). Profiles and listings come from fixtures, not from
  live P01/P03 modules.
- **Deferred:** authentication, drafts, employer/coordinator decisions, the
  AI matching feature (Sprint 2), rematching, the P06/P07 handoffs, and deployment.
