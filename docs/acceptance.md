# Sprint 1 acceptance results (P04 / P05)

Sprint goal (from *Projects 4 and 5 User Stories and Story Map*): using six synthetic profiles
and six opportunities, Layla receives a rules-based recommendation with reasons, opens a
published opportunity, submits an application and sees **Submitted**. Links survive reload;
placement stays **Not placed**.

Source references are the story-map story IDs and catalogue acceptance evidence (AE). Sprint 0
R-numbers still need to be added from the team backlog.

Automated evidence: `uv run pytest` gives 31 passed.

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
| | AC2 Closed/unpublished, missing data or duplicate active application blocked; no extra record | Met | `test_walking_skeleton_thread`, `test_unknown_student_or_opportunity`, `test_missing_required_application_field_is_rejected` |

## Shared completion checks
- **Simulated, labelled in the UI:** student selection (no login), P01/P03 data (fixtures), AI (none yet).
- **Keyboard:** the core journey can be done by keyboard (Tab, Enter or Space; Esc closes the confirm dialog).
  Focus is clearly visible.
- **Accessibility gaps recorded:** tabs don't support arrow-key movement; colour contrast hasn't been
  measured with a tool; there's been no screen-reader test.

## Deferred (not Sprint 1)
Login and role permissions, drafts (P04-02), employer/coordinator decisions (P04-04 to P04-06),
withdrawal (P04-07), AI assistance (P05-04), correction requests (P05-05), P06/P07 handoffs, live
P01/P03 connections, deployment.
