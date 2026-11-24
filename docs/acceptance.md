# Sprint acceptance results (P04 / P05)

## Sprint 3 — Exceptions, offers and confirmed-placement handoffs

Sprint goal (from *Projects 4 and 5 User Stories and Story Map*): Layla accepts an offer that
becomes a placement only when the coordinator confirms it, and P07 receives that placement;
she can withdraw an application and inspect its full history; her Jira gap on OP-028 links to
P06 preparation, and reviewed Jira evidence produces a new recommendation tied to the new
profile version, with the original still traceable.

Automated evidence: `uv run pytest` gives **98 passed** (66 Sprint 1–2 tests kept green, 32
added: `tests/test_sprint3.py`, `tests/test_p01p03_data.py`, rules-v3 checks). One Sprint 2 check changed on purpose: `Offer` is now a
valid employer action from `Shortlisted`, and still blocked (409, "never") after `Declined`.
Live browser walk-through in the main Coop UI (`/`, using **Demo as** to switch roles) on a fresh database: Jira gap → P06 activity → mark
done (recommendation unchanged) → offer → accept (Awaiting university confirmation) →
withdraw APP-0002 (cancel first, record unchanged) → coordinator confirms PL-0001 + H07-0001,
repeat confirm adds nothing → faculty reviews Jira → new profile version, rematch, OP-028 gap gone,
earlier run kept.

**Integration with P01–P03 data (24 Nov).** The app now reads the P01–P03 team's export.
Their built-in test cases pass (`tests/test_p01p03_data.py`): only OP-028/031/034 are listed and
recommended (OP-036 closed, OP-039 unpublished are excluded and cannot be applied to); Layla is
read at her latest submitted version (v2); COOP-B004 stays "unknown" with missing interests and
availability named; supervisor contact stays hidden. In their data Layla holds Jira as
*self-declared*, so **rules-v3** lists a self-declared required skill as an evidence gap: OP-028
shows the Jira gap on v2, and the faculty review creates v3 with the gap closed (score unchanged at 8),
checked in the browser and in `test_jira_story_with_p01_data_gap_prepare_review_rematch`.

| Story | Acceptance check | Result | Evidence |
|---|---|---|---|
| **P04-05** Respond to a simulated offer | AC1 Employer offers on a shortlisted application; student accepts or declines; each action records actor and time | Met | `test_p04_05_ac1_employer_offers_and_student_accepts_with_actor_and_time`, `test_p04_05_ac1_student_can_decline_an_offer`; Employer "Make offer", Student "Accept / Decline offer" |
| | AC2 Acceptance shows Awaiting university confirmation and creates no placement; accepting an absent or declined offer is blocked | Met | `test_p04_05_ac2_acceptance_is_awaiting_confirmation_not_a_placement`, `test_p04_05_ac2_accepting_absent_or_declined_offer_is_blocked`, `test_offer_guards` |
| **P04-06** Confirm a placement and hand it over | AC1 Confirming creates a unique placement ID linked to application, student and opportunity; records coordinator and time; P07 handoff contains it | Met | `test_p04_06_ac1_confirmation_creates_linked_placement_and_p07_handoff`; Coordinator "Accepted offers" queue and P07 mock outbox |
| | AC2 No confirmation without acceptance; repeating creates no second placement or handoff | Met | `test_p04_06_ac2_unaccepted_application_cannot_be_confirmed`, `test_p04_06_ac2_repeat_confirmation_is_idempotent`, `test_only_coordinator_confirms` |
| **P04-07** Withdraw and inspect history | AC1 From Submitted / Under review / Shortlisted, withdrawal sets Withdrawn with actor, time and next action; prior events kept after reload | Met | `test_p04_07_ac1_withdraw_from_agreed_states_keeps_history` (3 states); history timeline in My applications |
| | AC2 Cancelling leaves the record unchanged; withdrawal after confirmation and other invalid transitions are blocked with an explanation | Met | `test_p04_07_ac2_cancelled_withdrawal_leaves_record_unchanged`, `test_p04_07_ac2_invalid_withdrawals_are_blocked_with_explanation`; Cancel button sends no request |
| **P05-06** Connect a skill gap to preparation | AC1 A Jira gap passes student ID, skill ID, opportunity/version and recommendation ID to P06; the link shows the activity or a labelled fixture | Met | `test_p05_06_ac1_gap_passes_ids_and_versions_to_p06`; "Prepare →" on each gap opens Team P6/P7's activity (`MOD-JIRA-101` for Jira) |
| | AC2 No module → clear next action; completing a resource never changes the recommendation | Met | `test_p05_06_ac2_no_module_gives_clear_next_action` (Python has no P06 activity), `test_p05_06_ac2_completing_activity_never_changes_the_recommendation` |
| **P05-07** Rerun matching after a profile change | AC1 Reviewed Jira evidence or changed availability creates a recommendation tied to the new profile version; recorded test shows the expected change | Met | `test_p05_07_ac1_reviewed_jira_evidence_rematches_against_new_version` (fixture data: Jira missing → gap removed, +2 score; P01 data: self-declared Jira evidence gap removed), `test_p05_07_ac1_changing_availability_creates_a_new_versioned_run` |
| | AC2 Old recommendations keep their versions and reasons; same input and method versions give the same rules result; AI behaviour documented | Met | `test_p05_07_ac2_old_runs_keep_versions_and_same_inputs_give_same_rules_result`. AI here is deterministic (`ai-termmatch-v1`, `ai-insights-v1`), so it also repeats exactly; a future model-based AI would need its variability recorded |

### Shared completion checks (Sprint 3)
- **Simulated, labelled in the UI:** role switching; P01/P03 data (file export from the P01–P03 team + revisions, not a live API);
  P06 activities (Team P6/P7's list, file); P07 receipt ("mock outbox", `receipt_status: mock-received`).
- **Working:** offers and responses, withdrawal, placement confirmation with a single P07
  handoff, gap handoffs with source versions, profile updates as new versions with rematching.
- **Agreed with Team P6/P7 (24 Nov):** placement ID `PL-0001`; `academic_advisor` null (assigned by the coordinator in P07); gaps close only on outcome "demonstrated" (P06 → P01 new version → rematch; our faculty button simulates it); their co-op assistant is embedded behind our chat button.
- **Open:** live P01/P03/P06/P07
  interfaces; accessibility gaps carried from Sprint 2 (arrow-key tabs, contrast tool,
  screen reader).

---

## Sprint 2 — Response and revision

Sprint goal (from *Projects 4 and 5 User Stories and Story Map*): a student's world responds
and revises — Layla saves and refines an application draft, a simulated employer reviewer
decides on her application with visible actor/timestamp/next action, a bounded and labelled
AI term-matching feature runs alongside the unchanged rules baseline, and a coordinator can
inspect a flagged recommendation, record a correction and rematch against a new input
version with the original recommendation still traceable.

Automated evidence: `uv run pytest` gives **66 passed** (35 Sprint 1 tests kept green, 31 added).
Live smoke check of the full thread (draft → submit → decline → flag → accept → rematch) at
`127.0.0.1:8000`.

| Story | Acceptance check | Result | Evidence |
|---|---|---|---|
| **P04-02** Save and revise a draft | AC1 Draft links student, opportunity version and profile version; survives reload with its Draft label | Met | `test_draft_save_edit_and_submit_lifecycle`, `test_draft_upsert_one_per_student_and_opportunity` |
| | AC2 Editing/saving does not submit; submission with a missing required field gives a useful error and preserves entered data | Met | `test_statement_is_required_for_submission`, draft lifecycle test (422 keeps statement); apply dialog keeps the typed text |
| **P04-04** Review and decide | AC1 Submitted → Under review → Shortlisted/Declined; student sees decision, actor, timestamp, next action and decline reason | Met | `test_decision_flow_records_actor_timestamp_and_next_action`, `test_decline_requires_reason_and_is_shown_to_the_student`; My applications history |
| | AC2 Decline cannot move to an offer; unauthorised demo roles blocked; role simulation visibly labelled | Met | `test_invalid_transitions_and_unauthorised_roles_are_blocked` (Offer → 422, Declined terminal, 403 for student/coordinator/faculty); sidebar labels |
| **P05-04** Bounded AI assistance | AC1 Identifies the terms it used and records its method version alongside the separate rules result | Met | `ai_method_version = ai-termmatch-v1`, `ai_matches` cite term + field + skill + evidence status; `test_ai_terms_recorded_alongside_the_separate_rules_result`, tests/test_ai.py |
| | AC2 Cannot override a mandatory conflict or invent a qualification; labelled simulated; rules baseline still usable | Met | AI matches only map terms to held skills; eligibility/score/gaps byte-identical to the rules engine; "AI assistance — simulated, deterministic" box; `test_ai_never_changes_the_rules_result`, `test_ai_finds_nothing_when_the_student_has_no_relevant_skills` |
| **P05-05** Challenge and correct inputs | AC1 Student flags a result; coordinator sees reason, affected field and source version; records a correction request for the owning module | Met | `test_flag_correction_accept_and_rematch_stays_traceable`, `test_p03_and_skill_corrections_are_recorded_only`; Coordinator view |
| | AC2 Accepted correction uses a new input version and can be rematched; original recommendation stays traceable; P01/P03 records never silently overwritten | Met | correction acceptance → `profile_revisions` v+1 (fixture table untouched); rematch stores a new run; `recommendation-runs` endpoint lists both; guards in `test_correction_flow_guards` |
| **P05-04 extension** AI recommendation insights | Relevance %, summary, next steps, similar listings and a statement starter, stored as `ai-insights-v1` beside the rules result; never change eligibility, score, gaps, unknowns or the rules ranking; the statement starter cites only skills on the profile and saves nothing | Met | tests/test_ai_insights.py (8 tests: `test_insights_never_change_the_rules_result_or_order`, `test_statement_draft_only_cites_skills_on_the_profile`, …); AI assistant panel, "AI relevance" view-only sort, "Draft with AI" in the apply dialog |

### Shared completion checks (Sprint 2)
- **Simulated, labelled in the UI:** role switching (Student / Employer reviewer / Coordinator /
  Faculty — no login), P01/P03 data (fixtures + correction revisions as new versions), AI term
  matching (deterministic, labelled "simulated AI").
- **Working:** drafts, submissions, decision history, the duplicate and transition rules,
  bounded term matching, correction requests and version-traceable rematching, SQLite persistence.
- **Keyboard:** role switching, tabs, dialogs (Esc/Cancel) and all actions are keyboard-operable;
  focus is visible (gold outline in the sidebar, blue elsewhere).
- **Accessibility gaps still open (carried from Sprint 1):** tabs don't support arrow-key
  movement; contrast not measured with a tool; no screen-reader test yet.

### Sprint 2 additions to the contract
`statement` is now required at submission (P04-02 AC2 makes the missing-field case real).
Sprint 1's `POST /api/applications` checks were re-run with the new field and stay green.
`ACTIVE_STATUSES` extended to Submitted / Under review / Shortlisted as planned in v1.

---

## Sprint 1 — Walking skeleton

Sprint goal (from *Projects 4 and 5 User Stories and Story Map*): using six synthetic profiles
and six opportunities, Layla receives a rules-based recommendation with reasons, opens a
published opportunity, submits an application and sees **Submitted**. Links survive reload;
placement stays **Not placed**.

Source references are the story-map story IDs and catalogue acceptance evidence (AE). Sprint 0
R-numbers still need to be added from the team backlog.

| Story | Acceptance check | Result | Evidence |
|---|---|---|---|
| **P05-01** Shared synthetic inputs | AC1 ≥6 profiles and ≥6 opportunities with varied interests, availability, skills and missing values; IDs, versions, shared skill vocabulary | Met | fixtures; `test_fixtures_have_at_least_six_of_each` |
| | AC2 Unpublished/closed excluded from recommendations | Met | `test_closed_and_unpublished_listings_are_excluded` |
| | AC2 Missing field stays unknown | Met | `test_missing_dates_are_unknown_not_satisfied`, `test_each_missing_date_leaves_eligibility_unknown` |
| | AC2 Malformed record rejected or flagged | Met | `test_malformed_fixture_records_are_skipped` (skipped and logged) |
| **P05-02** Rules-based suggestions | AC1 Same inputs and rules version give the same ranking | Met | `test_same_input_gives_same_ranking` |
| | AC1 Editable rules separate mandatory conditions from preference scoring | Met | `app/rules.json`; `test_rules_config_separates_mandatory_from_preferences`, `test_mandatory_rule_can_be_switched_off_in_rules_config` |
| | AC2 Mandatory conflict flagged and excluded from compatible results | Met | `test_availability_conflict_is_flagged_and_ranked_last` |
| | AC2 Unknown condition labelled "Needs checking", never satisfied | Met | `test_missing_dates_are_unknown_not_satisfied` |
| **P05-03** Reasons, gaps, unknowns | AC1 Stores ID, timestamp, method version, input versions; shows reasons, gaps, unknowns | Met | `test_walking_skeleton_thread`; recommendation card |
| | AC2 Self-declared skill not described as verified | Met | `test_layla_op028_reasons_and_jira_gap` |
| | AC2 Open the same opportunity in P04 without creating an application | Met | "Open in catalogue" button; `test_walking_skeleton_thread` (GET creates no application) |
| **P04-01** Browse and compare | AC1 Only published, open listings available; no-match message | Met | `test_opportunity_list_only_shows_published_open`, `test_search_and_no_results` |
| | AC2 Compare two listings with requirements and approved versions | Met | Compare table in Browse; `test_two_listings_can_be_compared_with_versions_and_requirements` |
| | AC2 Opening a linked recommendation preserves the opportunity ID | Met | "View recommendation" link from a catalogue card (manual check) |
| **P04-03** Submit and see status | AC1 Unique application ID linked to student, opportunity version and profile version; Submitted / Not placed after reload | Met | `test_walking_skeleton_thread`; manual reload check |
| | AC2 Closed/unpublished, missing data or duplicate active application blocked; no extra record | Met | `test_walking_skeleton_thread`, `test_unknown_student_or_opportunity`, `test_missing_required_application_field_is_rejected` (re-run in Sprint 2 with the new required `statement`) |

## Deferred (not Sprint 2)
Login and real role permissions, offers and student acceptance (P04-05), university placement
confirmation + P07 handoff (P04-06), withdrawal (P04-07), skill-gap → P06 (P05-06), general
rematching after profile changes (P05-07), baseline evaluation (P05-08), applying P03 listing
corrections and P01/P06 skill-evidence corrections (need the live owning modules), live
P01/P03 connections, deployment.
