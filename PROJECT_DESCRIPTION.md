# Project description

## Purpose and scope

The **Internship Practicum Platform (IPP)** Sprint 1 walking skeleton is a development project for the course demo: Employer HR → University Administrator → Student → Faculty Reviewer, using synthetic data only. This standalone reference is separate from the class's shared Lovable project and integrated repository.

Existing GitHub repository: <https://github.com/ray-suton/ipp-walking-skeleton-demo>. Existing Pages deployment: <https://ray-suton.github.io/ipp-walking-skeleton-demo/>.

## Shared data contract

The source of seed data is [data/ipp_sample_data.json](data/ipp_sample_data.json), supplied by P01–P03 for P04/P05 and P06/P07. The supplied _meta, skills_vocabulary, student_profiles and published_listings field names and record values are preserved. The metadata still identifies the format as proposed; confirmation must come from the teams.

The five student_profiles records represent four students. Reads select the highest numeric profile_version with profile_status = submitted for each student_id, ignoring drafts. Layla (COOP-B001) starts at version 2 with reviewed SQL evidence. Saving a display-name correction appends a new submitted version, preserving history. The UI exposes all four synthetic students through a demo selector.

Student listing reads and application submission require publication_status = published AND listing_status = open. The initial eligible IDs are OP-028, OP-031 and OP-034; OP-036 is closed and OP-039 is unpublished. Administrators can publish unpublished demo listings; publishing never reopens a closed listing. No recommendation scoring or AI integration is implemented.

Student-safe listing projections remove supervisor_name and supervisor_contact, including nested application records. Faculty projections also omit these P07-only fields. The public JSON retains the supplied synthetic values for the intended handoff; this static demo does not provide access control over the raw file.

Noor (COOP-B004) has no interests or known availability. The profile displays those gaps without inferring data. Skill labels come from skills_vocabulary. Eligibility and placement approval remain human decisions.

## Architecture

- index.html and styles.css: responsive page shell, persistent synthetic-data disclosure, dialogs and green/white course styling.
- src/app.js: fetches the JSON relative to the document URL (including GitHub Pages project paths), then starts the Overview and four hash-routed role views, with a live journey tracker and activity feed. Employer HR retains the read-only Applicants tab. A failed seed request shows a retry action. User text is rendered as text nodes.
- src/ui.js: reusable DOM builder, SVG icons, avatars and relative timestamps.
- scripts/stamp.mjs: content hashes in asset URLs prevent mixed cached script versions; run npm run stamp before committing source changes.
- src/store.js: shared business rules, latest-profile selection, append-only corrections, safe listing projections, duplicate prevention and localStorage persistence.
- scripts/serve.mjs: localhost static server with port fallback and an explicit demo-file allowlist, including the JSON endpoint.
- tests/: business rules, persistence and UI contracts/runtime checks using Node's built-in test runner.

The app uses plain HTML, CSS and classic JavaScript with no dependencies or build step. Runtime state includes copies of the shared records plus demo applications, reviews and one synthetic faculty reviewer. Storage is versioned as ipp-demo-v2; older ipp-demo-v1 data is not loaded or deleted. Reset restores a fresh copy of the shared seed. Browser-blocked storage falls back to memory with a warning.

## Run and demo

~~~bash
npm start
npm run stamp
npm test
~~~

Use HTTP hosting, not file://, because the app fetches its seed JSON. No offline guarantee is made.

1. Reset demo data. Open Student from the Overview: Layla starts at v2; there are three open published listings.
2. Open My profile to inspect skills and profile version. Select Noor to see missing interests and availability, then return to Layla.
3. Apply to OP-028 and confirm. A second application is blocked; My applications shows Submitted and Not placed separately.
4. Employer HR → Applicants shows the application without faculty review data. Switch to Faculty Reviewer: the same application/student/opportunity/review IDs appear read-only, with no supervisor information.
5. Employer HR: untick authorization to see submission blocked, then re-tick, fill sample data and submit. A new OP-040 listing starts unpublished/Pending Review.
6. Administrator: publish OP-040. It becomes visible to students because it is now published and open. OP-036 remains closed.
7. Reload to check persistence; reset when finished.

## Deferred work and constraints

Real authentication and permissions, central storage, AI recommendations, eligibility verification, return-for-revision, review outcomes, and placement decisions remain deferred. No new dependencies are required. Changes to the cross-team schema must be confirmed before changing the shared fixture. Course R-number traceability, prompt log and Scrum-of-Scrums evidence remain separate handoff work.
