# Coop business rules

These rules cover P04 applications and P05 matching. They preserve the recorded
P01/P03 and P06/P07 contracts in the data dictionary. The interview extension and
public discovery feed are implementation decisions for testing. Other teams have
not reviewed these additions.

## Source ownership

| Owner | Authoritative record | Current connection | Rule |
| --- | --- | --- | --- |
| P01 | Submitted student profiles and reviewed skills | Team file export | Read the latest submitted version. Ignore drafts. Preserve reviewed versus self-declared evidence. |
| P03 | Published university opportunities | Team file export | Only published, open records can be recommended or applied to internally. Keep original IDs and versions. |
| P04 | Applications, interviews, offers, placements | SQLite and application API | Record each transition, actor, time, and next step. |
| P05 | Recommendations and gap handoffs | SQLite and matching API | Keep rules and input versions with every result. Preserve earlier runs. |
| P06 | Preparation activities and demonstration outcomes | Team activity file | Completing a resource does not verify a skill. The P06 → P01 demonstration flow requires a new profile version. |
| P07 | Placement learning records | Local mock outbox | Send a confirmed placement once. Receipt currently represents a local mock, not confirmed remote delivery. |
| Canonical / Remotive / Arbeitnow / Remote OK / Jobicy | External job advertisements | Live public API | Attribute and link to the provider. Applications happen on the provider’s website. |

No live team endpoints or credentials were supplied. The app does not claim a
network connection to those teams. Existing exported fields and handoff IDs remain
compatible. To connect the teams, they need to supply the endpoints, authentication
method, version conflict policy, and acknowledgement contract. No approval has
been inferred and no messages have been sent to the teams.

## Discovery

1. Live Explore uses Canonical’s public board and Remotive advertisements with technology or research keywords,
   including data, software, machine learning, Python, cloud, and engineering.
   Clearly senior or managerial titles are excluded. Keyword filtering is a
   discovery aid, not an eligibility assessment or a guarantee of student fit.
2. Show the provider's actual candidate location restrictions. Remote work never
   implies worldwide eligibility. Missing country, degree, pay, or dates remain
   unknown. Never manufacture requirements, availability, or employer approval.
3. Provider content is converted to plain text. Only HTTPS URLs on each configured provider’s domain
   are accepted. Every external card links back to its provider and names its source.
4. Cache successful feed responses for six hours, respecting the provider's
   suggested maximum of four fetches per day. Failed refresh attempts are also
   cached for six hours. If a refresh fails, label the last successful feed stale,
   or show unavailable when there is no saved response.
5. Feed jobs remain external. Saving a card does not create an application.
   Opening an external application link does not imply submission, interview,
   acceptance, or placement within Coop.
6. University listings remain selectable for testing the internal application
   workflow. They are identified as a team export. Public listings never enter
   P03's approved set or the placement pipeline automatically.
7. Remove fabricated company vacancies from the catalogue. Retain historical
   image assets as appropriate, but never relabel samples as live jobs.

## Matching

1. Use rules-v3. Only published, open P03 listings enter the university matching run.
2. Availability coverage determines eligible, ineligible, or unknown. Missing dates
   never pass the mandatory date condition.
3. Sector preference adds 3 points. Each held required skill adds 2; each held
   desirable skill adds 1.
4. Required self-declared skills earn preference points but retain an evidence gap
   until reviewed. A completed P06 activity does not remove this gap.
5. The deterministic insight and term-matching helpers cannot change eligibility,
   the rules score, or stored ranking, and cannot invent qualifications.
6. A profile update creates a new version and a new matching run. Historical runs
   retain their original IDs, input versions, reasons, and method versions.

## Application lifecycle

| Current status | Action | Owner | Result |
| --- | --- | --- | --- |
| Draft | Submit with statement | Student | Submitted |
| Submitted | Begin review | Employer | Under review |
| Under review | Shortlist or decline with reason | Employer | Shortlisted or Declined |
| Shortlisted | Schedule an interview | Employer | Interview scheduled |
| Interview scheduled | Reschedule | Employer | Interview scheduled, event added |
| Interview scheduled | Record completion after the scheduled start | Employer | Interview completed |
| Interview scheduled / Interview completed | Decline with reason | Employer | Declined |
| Interview completed | Make offer | Employer | Offered |
| Shortlisted | Make offer without interview | Employer | Offered, retained for legacy callers and roles without interviews |
| Offered | Accept or decline | Student | Offer accepted or Offer declined |
| Offer accepted | Confirm | Coordinator | Confirmed placement and one P07 handoff |
| Submitted / Under review / Shortlisted / Interview scheduled / Interview completed | Withdraw | Student | Withdrawn |

Interviewing is optional because the existing contract allows an offer from a
shortlist. Once an interview is scheduled, an offer requires interview completion.
This additive policy keeps existing P04 callers usable and is proposed for
cross-team review.

1. Internal submission requires an existing student, a published open P03
   opportunity, and a nonempty statement. Draft submission converts the existing
   draft. One active application per student/opportunity is allowed.
2. Active duplicate checks include both interview states, Offered, and Offer
   accepted. Declined, Offer declined, and Withdrawn are terminal for that
   application, while the student may submit a fresh application if allowed.
3. Only the employer can schedule or complete an interview. Scheduling is allowed
   from Shortlisted or Interview scheduled. Use a future timezone-aware datetime,
   15–240 minute duration, online/in-person format, and a meeting location/link.
   Store UTC; display the user's local timezone. Keep rescheduling details in the
   event history. Completion before the scheduled start is rejected.
4. Employer decline requires a reason. Student withdrawal is allowed in the
   interview states. An offer cannot follow decline or withdrawal.
5. Interview records are P04-owned and never change P01 skill evidence, P03
   opportunity approval, P06 activity completion, or P07 placement records.
6. Accepting an offer sets Awaiting university confirmation. Only the coordinator
   confirms a placement. Repeat confirmation returns the existing placement and
   creates no additional P07 handoff.
7. Supervisor contact goes to P07 with confirmation and stays hidden from student
   listing responses.
8. Role controls are simulated for testing. They are not authenticated identity
   or production authorization.

## Proposed team review

| Team | Confirm before live integration |
| --- | --- |
| P01/P03 | Live URLs, authentication, stable IDs, revision precedence, degree/job-type fields, published/open semantics, and withdrawn listing behavior |
| P06 | Gap payload versions and demonstration evidence sent through P01; preparation completion must not verify a skill |
| P07 | One placement per application, idempotency key based on placement ID, acknowledgement/retry behavior, and interview fields remaining outside the placement payload |
| P04/P05 | Optional interview path, timezone and completion policy, legacy shortlist-to-offer compatibility, external application boundary |

Source documentation for the public feed:
https://github.com/remotive-com/remote-jobs-api

Canonical graduate/junior technology roles also use its public Greenhouse board. Each provider has an independent cache and freshness status.
https://docs.greenhouse.io/job-board.html


## Additional public sources

Arbeitnow, Remote OK, and Jobicy share the external discovery boundary: each job
retains its source and original link; application submission stays with that
provider. Arbeitnow's remote=false flag is not interpreted as an on-site or
hybrid guarantee. Remote-only feeds retain their candidate geography rather than
being labelled eligible worldwide. Unknown employment types remain unknown.
The Remote OK metadata/legal first row is excluded from listings. Every provider
has a separate six-hour cache, and independent refresh failures preserve the
other providers' successful responses. Jooble, Adzuna, and JSearch need account
credentials before they can be integrated.
