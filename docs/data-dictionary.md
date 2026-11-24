# Data dictionary v3 (P04 / P05, Sprint 3)

All records are synthetic. P04 owns applications; P05 owns recommendations. P01 profiles and
P03 listings come from the **P01–P03 team's file export** (`app/data/p01p03/`, received 24 Nov,
same fields as below; extra `profile_status`: only `submitted` versions are read, the latest per
student). Our own synthetic set in `app/fixtures/` is used by the automated tests
(`DATA_SOURCE=fixtures`). Neither is a live interface yet.

Roles are **simulated** in the UI sidebar (Student, Employer reviewer, Coordinator, Faculty
reviewer). Mutating endpoints take an `actor_role` field and reject other roles with `403`.
There is no login; real access control is a recorded, deferred gap.

## Student profile (owner: P01; fixture `app/fixtures/students.json` + revisions)
| Field | Type | Meaning |
|---|---|---|
| student_id | string | e.g. `COOP-B001` (Layla Hassan) |
| profile_version | int | Version used by matching and applications |
| display_name | string | |
| interests | string[] | Sectors, e.g. `aviation`; empty = not provided |
| availability_start / availability_end | date or null | null = unknown, never assumed |
| skills | `{skill_id, evidence_status, reviewed_by, reviewed_at, evidence_id}`[] | `evidence_status`: `self_declared` or `reviewed`; the last three are null when `self_declared` (agreed with P01, 10 Nov) |

The effective profile is the **latest revision** (`profile_revisions`) if there is one, else
the fixture. P05 never edits the fixture table — every change is stored as a *new version*:
`correction:<CR-id>` (accepted correction, P05-05), `profile-update:availability` (student
changes availability, P05-07) or `profile-update:skill_evidence:<skill_id>` (faculty reviewer
marks a skill reviewed with `reviewed_by`, `reviewed_at`, `evidence_id`, P05-07). A profile
update re-runs matching against the new version; earlier runs keep their versions.

## Published listing (owner: P03; fixture `app/fixtures/opportunities.json`)
| Field | Type | Meaning |
|---|---|---|
| opportunity_id | string | e.g. `OP-028` |
| version | int | P03 listing version; increases each time the listing is republished |
| submission_version | int | P02 employer submission this listing came from (traceability) |
| employer_name, title, sector, location | string | |
| work_mode | string | `on-site`, `hybrid`, `remote` |
| description | string | Short role text (P02-supplied tasks stand-in); scanned by the AI term matcher |
| start_date / end_date | date or null | null = unknown |
| required_skills / desirable_skills | skill_id[] | From the shared skill vocabulary |
| supervisor_name, supervisor_contact | string | Workplace supervisor; passed on to P07 with a confirmed placement, **never shown to students** (stripped from `/api/opportunities`) |
| publication_status | string | `published` or `unpublished` |
| listing_status | string | `open` or `closed` |

Only `published` + `open` listings can be recommended, drafted or applied to.

Profiles: P05 reads the latest submitted profile version (including correction revisions),
never drafts. Corrections create a new version owned by P01/P03; P04/P05 never edit those
records. Fixtures are reloaded on every startup; stored records are never touched.

## Skill vocabulary (shared; `app/fixtures/skills.json`)
Shared list agreed with P01–P03 and P06 (10 Nov): `SK-JIRA`, `SK-SQL`, `SK-VIZ` (data
visualisation, including Tableau), `SK-PY`, `SK-EXCEL`, `SK-FIGMA`, `SK-COMM`, `SK-DMKT`.

**Alias map (P05-owned fallback, `app/fixtures/skill_aliases.json`)**: equivalent terms per
skill for the bounded AI feature. Extending the shared vocabulary itself needs Scrum of
Scrums agreement; this local map is the labelled fallback.

## Recommendation (owner: P05; table `recommendations`)
| Field | Meaning |
|---|---|
| recommendation_id | `REC-xxxxxxxx` |
| run_id | Groups one matching run |
| student_id, profile_version | Input profile version used |
| opportunity_id, opportunity_version | Input listing version used |
| method_version | Rules version from `app/rules.json`, currently `rules-v3` (adds evidence gaps: a required skill held only as `self_declared` is listed in `gaps` as "reviewed evidence needed"; the score is unchanged) |
| eligibility | `eligible`, `unknown` (needs checking), `ineligible` (mandatory conflict) |
| compatible | true only when eligibility is `eligible` |
| score | Preference score |
| reasons / gaps / unknowns | Explanation lists tied to named fields and skills |
| ai_method_version | Bounded AI method that ran alongside the rules, e.g. `ai-termmatch-v1` (null for rows saved before Sprint 2) |
| ai_matches | JSON list of `{term, field, skill_id, skill_name, evidence_status}` — terms in the listing text equivalent to skills the student already holds. **Never** changes eligibility, score, gaps or unknowns, and never invents skills (P05-04 AC2). |
| ai_insights | JSON `{version: "ai-insights-v1", relevance (0–100), top_terms, summary, next_steps[{kind, skill_id, skill_name, score_gain, unlocks, tip}], similar[{opportunity_id, title, employer_name, similarity}]}`; null for runs stored before Sprint 2's insights. Assistance only — never changes the rules result or ranking. |
| created_at | UTC timestamp |

Earlier runs stay stored and traceable: `GET /api/students/{id}/recommendation-runs` lists
every run with its input versions, even after a correction and rematch.

## Application (owner: P04; table `applications`)
| Field | Meaning |
|---|---|
| application_id | `APP-0001`, … |
| student_id, profile_version | Profile version at submission |
| opportunity_id, opportunity_version | Listing version at submission |
| application_status | `Draft` → `Submitted` → `Under review` → `Shortlisted` → `Offered` → `Offer accepted` \| `Offer declined`; also `Declined` (employer) and `Withdrawn` (student) |
| placement_status | `Not placed` → `Awaiting university confirmation` (student accepted the offer) → `Confirmed` (coordinator only). Shown separately from the application status |
| submitted_at | UTC timestamp (row creation for drafts; set again at submission) |
| statement | Short motivation text; may be empty while Draft, **required** at submission (422 otherwise, draft preserved) |
| updated_at | Last draft save / status change |

**Active statuses** (duplicate check): `Submitted`, `Under review`, `Shortlisted`, `Offered`,
`Offer accepted`. `Draft`, `Declined`, `Offer declined` and `Withdrawn` are not active. One draft per student+opportunity (saving again
updates it). A direct submission converts an existing draft — no orphan drafts.

**Employer transitions (P04-04, P04-05):** `Submitted → Under review`; `Under review →
Shortlisted | Declined`; `Shortlisted → Offered (action "Offer") | Declined`. Anything else is
blocked with `409`, including every action from `Declined` (an offer can never follow a
decline). Declining requires a `reason`.

**Student offer response (P04-05):** `Offered → Offer accepted` (placement becomes
`Awaiting university confirmation`, never `Confirmed`) or `Offered → Offer declined`
(terminal). Responding with no open offer, or accepting an already declined offer, gives `409`.

**Withdrawal (P04-07):** from `Submitted`, `Under review` or `Shortlisted` → `Withdrawn`
(terminal; reason optional). Blocked with an explanation (`409`) after placement confirmation
and from any other state (an offer is declined instead). Cancelling in the UI makes no call.

**Placement confirmation (P04-06):** coordinator only, from `Offer accepted`; see Placement.

## Application events (owner: P04; table `application_events`)
Every status change records `action`, `actor_role` (`student` / `employer` / …),
`actor_name`, `reason` (required for `Declined`), `next_action` and `created_at`. The
student sees this history (P04-04 AC1, P04-07). Actions: `Draft saved`, `Submitted`,
`Under review`, `Shortlisted`, `Declined`, `Offered`, `Offer accepted`, `Offer declined`,
`Withdrawn`, `Placement confirmed`.

## Placement (owner: P04; table `placements`)
| Field | Meaning |
|---|---|
| placement_id | `PL-0001`, … (format agreed with Team P6/P7, 24 Nov) |
| application_id | Unique — one placement per application |
| student_id, profile_version, opportunity_id, opportunity_version | Copied from the application |
| confirmed_by, confirmed_at | Coordinator and UTC time |

Repeating confirmation returns the existing placement (`already_confirmed: true`) and creates
neither a second placement nor a second handoff (P04-06 AC2).

## P07 handoff (owner: P04; table `p07_handoffs`, mock outbox)
One row per placement (`placement_id` unique): `handoff_id` (`H07-0001`), `sent_at`,
`receipt_status` (`mock-received` until P07 is live) and `payload`, named as P07 requested
(Zhengxi, 10 Nov): `{placement_id, status: "university_confirmed", student_id, opportunity_id,
employer_name, location, role, period_start, period_end, supervisor_name, supervisor_contact,
academic_advisor}` plus the fields we agreed to add: `application_id, opportunity_version,
confirmed_by, confirmed_at`. `academic_advisor` is null by agreement with Team P6/P7 (24 Nov): the coordinator assigns it in P07 when the placement arrives. Supervisor contact goes to P07 only, never to the student.

## Skill gap handoff (owner: P05; table `skill_gap_handoffs`)
| Field | Meaning |
|---|---|
| gap_id | `GAP-0001`, … (unique per recommendation + skill) |
| student_id, skill_id, opportunity_id, opportunity_version, recommendation_id, profile_version | Stored source IDs and versions (P05-06 AC1) |
| p06_payload (API) | What P06 receives, named as P06 requested (10 Nov): `gap_id, student_id, skill_id, opportunity_id, reason` (e.g. "OP-028 requires Jira; not yet demonstrated") plus the trace fields we added: `recommendation_id, opportunity_version, profile_version` |
| activity_id | P06 activity from Team P6/P7's list `app/data/p06/p06_activities.json` (24 Nov: Jira `MOD-JIRA-101` full module; SQL and VIZ outlines, `status: outline`), or null when they have no module (e.g. Excel, Figma, Python) — the student then sees a clear next action |
| created_at, completed_at | Completing an activity is recorded but **never** changes a recommendation or marks the skill reviewed (P05-06 AC2) |

## Correction request (owner: P05; table `correction_requests`)
| Field | Meaning |
|---|---|
| correction_id | `CR-0001`, … |
| recommendation_id | The flagged recommendation |
| student_id, reason | Who flagged and why |
| affected_field | `availability`, `interests`, `skills` (P01) or `listing dates`, `required skills`, `listing status` (P03) |
| source_module | `P01` or `P03` — the owning module the request is recorded for |
| source_version | Snapshot of the challenged inputs: profile version, opportunity id/version, method version |
| status | `flagged` → `recorded` → `accepted` |
| coordinator, note, decided_at | Coordinator who handled it, note to the owning module, decision time |

Accepted **profile** corrections (availability, interests) are applied as a new profile
version in `profile_revisions` and can be rematched. Listing (P03) and skill-evidence
corrections stay *recorded* — applying them needs the live owning module (deferred).

## API contract (FastAPI; full schema at `/docs` when running)
| Method & path | Purpose | Errors |
|---|---|---|
| GET `/api/students`, `/api/students/{id}` | Effective profiles (fixture + accepted corrections) | 404 unknown student |
| GET `/api/opportunities?q=&work_mode=` | Published, open listings; search title/employer | |
| GET `/api/opportunities/{id}` | One listing (any status) | 404 |
| GET `/api/skills`, `/api/rules` | Skill vocabulary, active rules | |
| POST `/api/students/{id}/recommendations` | Run and store matching (rules + AI alongside) | 404 |
| GET `/api/students/{id}/recommendations` | Latest stored run | |
| GET `/api/students/{id}/recommendation-runs` | Every stored run (traceability) | 404 |
| POST `/api/applications` `{student_id, opportunity_id, statement}` | Submit (converts an existing draft) | 400 unknown/closed; 409 duplicate active; 422 missing statement; 403 wrong role |
| POST `/api/applications/draft` `{student_id, opportunity_id, statement?}` | Save/update a draft (never submits) | 400/409 as above; 403 wrong role |
| PUT `/api/applications/{id}` `{statement}` | Edit a draft (stays Draft) | 404; 409 not a draft; 403 |
| POST `/api/applications/{id}/submit` `{statement?}` | Submit a draft | 422 missing statement (draft preserved); 409 not a draft/duplicate |
| GET `/api/students/{id}/applications` | The student's applications + history | |
| GET `/api/applications` | All applications + history (employer queue, faculty view) | |
| POST `/api/applications/{id}/decisions` `{action, actor_role, reason?}` | Employer decision | 403 non-employer; 409 invalid transition; 422 unknown action / missing decline reason |
| POST `/api/recommendations/{id}/flags` `{reason, affected_field}` | Student flags a result | 404; 422 missing reason/unknown field; 403 |
| GET `/api/corrections` | Coordinator queue | |
| POST `/api/corrections/{id}/record` `{note, actor_role}` | Record request for owning module | 403 non-coordinator; 409 wrong status |
| POST `/api/corrections/{id}/accept` `{actor_role, availability…/interests…}` | Apply as new input version | 403; 409 not recorded; 422 P03/skills deferred or missing values |
| POST `/api/applications/{id}/offer-response` `{response: accept\|decline, actor_role}` | Student answers an offer | 403 non-student; 409 no open offer / already declined; 422 bad response |
| POST `/api/applications/{id}/withdraw` `{actor_role, reason?}` | Student withdraws | 403; 409 not withdrawable / placement confirmed |
| POST `/api/applications/{id}/confirm-placement` `{actor_role, actor_name?}` | Coordinator confirms → placement + P07 handoff (idempotent) | 403 non-coordinator; 409 offer not accepted |
| GET `/api/placements`, `/api/p07/handoffs` | Confirmed placements; mock P07 outbox | |
| POST `/api/recommendations/{id}/gaps/{skill_id}/handoff` `{actor_role}` | Pass a gap to P06 | 403; 404; 422 not a gap in that recommendation |
| POST `/api/skill-gaps/{gap_id}/complete` `{actor_role}` | Record the P06 activity as done | 403; 404; 409 no activity |
| GET `/api/students/{id}/skill-gaps`, `/api/p06/activities` | Gap handoffs; Team P6/P7's activity list | |
| POST `/api/students/{id}/profile-updates` `{kind, actor_role, …, rematch?}` | `availability` (student) or `skill_evidence` (faculty) → new profile version + rematch | 403; 404; 422 missing/invalid values |
| GET `/api/students/{id}/profile-versions` | Every profile version with its source | 404 |
