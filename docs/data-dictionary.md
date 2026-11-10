# Data dictionary v1 (P04 / P05, Sprint 1)

All records are synthetic. P04 owns applications; P05 owns recommendations. P01 profiles and
P03 listings are **fixtures** until the interfaces with those teams are agreed.

## Student profile (owner: P01, read-only here; fixture `app/fixtures/students.json`)
| Field | Type | Meaning |
|---|---|---|
| student_id | string | e.g. `COOP-B001` (Layla Hassan) |
| profile_version | int | Version used by matching and applications |
| display_name | string | |
| interests | string[] | Sectors, e.g. `aviation`; empty = not provided |
| availability_start / availability_end | date or null | null = unknown, never assumed |
| skills | `{skill_id, evidence_status, reviewed_by, reviewed_at, evidence_id}`[] | `evidence_status`: `self_declared` or `reviewed`; the last three are null when `self_declared` (agreed with P01, 10 Nov) |

## Published listing (owner: P03, read-only here; fixture `app/fixtures/opportunities.json`)
| Field | Type | Meaning |
|---|---|---|
| opportunity_id | string | e.g. `OP-028` |
| version | int | P03 listing version; increases each time the listing is republished |
| submission_version | int | P02 employer submission this listing came from (traceability) |
| employer_name, title, sector, location | string | |
| work_mode | string | `on-site`, `hybrid`, `remote` |
| start_date / end_date | date or null | null = unknown |
| required_skills / desirable_skills | skill_id[] | From the shared skill vocabulary |
| supervisor_name, supervisor_contact | string | Workplace supervisor; passed on to P07 with a confirmed placement, **never shown to students** (stripped from `/api/opportunities`) |
| publication_status | string | `published` or `unpublished` |
| listing_status | string | `open` or `closed` |

Only `published` + `open` listings can be recommended or applied to.

Profiles: P05 reads the latest **submitted** profile version, never drafts. Corrections create a new
version in P01/P03; P04/P05 never edit those records. Fixtures are reloaded on every startup.

## Skill vocabulary (shared; `app/fixtures/skills.json`)
Shared list agreed with P01–P03 and P06 (10 Nov; full list to be confirmed at the next Scrum of Scrums):
`SK-JIRA`, `SK-SQL`, `SK-VIZ` (data visualisation, including Tableau), `SK-PY`, `SK-EXCEL`,
`SK-FIGMA`, `SK-COMM`, `SK-DMKT`.

## Recommendation (owner: P05; table `recommendations`)
| Field | Meaning |
|---|---|
| recommendation_id | `REC-xxxxxxxx` |
| run_id | Groups one matching run |
| student_id, profile_version | Input profile version used |
| opportunity_id, opportunity_version | Input listing version used |
| method_version | Rules version from `app/rules.json`, currently `rules-v2` |
| eligibility | `eligible`, `unknown` (needs checking), `ineligible` (mandatory conflict) |
| compatible | true only when eligibility is `eligible` |
| score | Preference score |
| reasons / gaps / unknowns | Explanation lists tied to named fields and skills |
| created_at | UTC timestamp |

## Application (owner: P04; table `applications`)
| Field | Meaning |
|---|---|
| application_id | `APP-0001`, … |
| student_id, profile_version | Profile version at submission |
| opportunity_id, opportunity_version | Listing version at submission |
| application_status | Sprint 1: `Submitted` |
| placement_status | Sprint 1: always `Not placed` (shown separately from application status) |
| submitted_at | UTC timestamp |

**Active statuses** (used for the duplicate check): `Submitted`. Later sprints add
`Under review` and `Shortlisted` to this list (see `ACTIVE_STATUSES` in `app/main.py`).

## API contract (FastAPI; full schema at `/docs` when running)
| Method & path | Purpose | Errors |
|---|---|---|
| GET `/api/students`, `/api/students/{id}` | Profiles | 404 unknown student |
| GET `/api/opportunities?q=&work_mode=` | Published, open listings; search title/employer | |
| GET `/api/opportunities/{id}` | One listing (any status) | 404 |
| GET `/api/skills`, `/api/rules` | Skill vocabulary, active rules | |
| POST `/api/students/{id}/recommendations` | Run and store matching | 404 |
| GET `/api/students/{id}/recommendations` | Latest stored run | |
| POST `/api/applications` `{student_id, opportunity_id}` | Submit | 400 unknown or closed/unpublished; 409 duplicate active; 422 missing field |
| GET `/api/students/{id}/applications` | The student's applications | |
