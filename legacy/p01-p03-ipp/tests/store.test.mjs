import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import '../src/store.js';

const SEED = JSON.parse(await readFile(new URL('../data/ipp_sample_data.json', import.meta.url), 'utf8'));
const { createStore, seedState, OPPORTUNITY_STATUS, PLACEMENT_STATUS, STORAGE_KEY } = globalThis.IPPStore;
const ELIGIBLE = ['OP-028', 'OP-031', 'OP-034'];
const VALID = { organization_name: 'Harbor Robotics', title: 'Controls Intern', description: 'Help test motion-control firmware on a lab rig.', location: 'Abu Dhabi', work_mode: 'On-site', duration: '8 weeks' };

function memoryStorage() {
  const data = new Map();
  return { getItem: (key) => data.get(key) ?? null, setItem: (key, value) => data.set(key, String(value)), removeItem: (key) => data.delete(key), raw: data };
}
const fresh = (seed = SEED) => createStore(memoryStorage(), seed);
const ids = (records) => records.map((record) => record.opportunity_id);
const noSupervisors = (value) => {
  assert.doesNotMatch(JSON.stringify(value), /supervisor_name|supervisor_contact|supervisor\.op\d+@example\.com/);
};

test('shared fixture retains five profile versions, five canonical listings, metadata and vocabulary', () => {
  const state = seedState(SEED);
  assert.equal(state.student_profiles.length, 5);
  assert.equal(state.published_listings.length, 5);
  assert.deepEqual(state.student_profiles, SEED.student_profiles);
  assert.deepEqual(state.published_listings, SEED.published_listings);
  assert.deepEqual(state.skills_vocabulary, SEED.skills_vocabulary);
  assert.deepEqual(state._meta, SEED._meta);
  assert.ok(!('students' in state));
  assert.ok(!('opportunities' in state));
  assert.ok(!('organization_name' in state.published_listings[0]));
  assert.ok(!('approval_status' in state.published_listings[0]));
});

test('store requires the shared seed rather than silently restoring the old hardcoded demo', () => {
  assert.throws(() => createStore(null), /ipp_sample_data/);
});

test('four students use their latest submitted versions; Layla uses reviewed SQL in version 2', () => {
  const store = fresh();
  assert.equal(store.listStudents().length, 4);
  assert.equal(store.getStudent('STU-001'), null);
  assert.deepEqual(store.getStudent('COOP-B001'), SEED.student_profiles[1]);
  assert.equal(store.getStudent('COOP-B001').skills[0].evidence_status, 'reviewed');
  assert.equal(store.getStudent('COOP-B001').skills[0].evidence_id, 'E-SQL-01');
  assert.deepEqual(store.getSkillsVocabulary(), SEED.skills_vocabulary);
});

test('latest submitted lookup ignores higher draft versions, ordering and draft-only students', () => {
  const seed = structuredClone(SEED);
  seed.student_profiles.reverse();
  seed.student_profiles.push({ ...SEED.student_profiles[1], profile_version: 10, profile_status: 'draft', display_name: 'Unsubmitted correction' });
  seed.student_profiles.push({ ...SEED.student_profiles[1], student_id: 'DRAFT-ONLY', profile_status: 'draft' });
  const store = fresh(seed);
  assert.equal(store.getStudent('COOP-B001').profile_version, 2);
  assert.equal(store.getStudent('COOP-B001').display_name, 'Layla Hassan');
  assert.equal(store.getStudent('DRAFT-ONLY'), null);
  assert.equal(store.listStudents().length, 4);
  assert.equal(store.submitApplication('DRAFT-ONLY', 'OP-028').code, 'not_found');
});

test('profile versions compare numerically rather than lexicographically', () => {
  const seed = structuredClone(SEED);
  seed.student_profiles.push({ ...SEED.student_profiles[1], profile_version: 10, display_name: 'Latest Layla' });
  assert.equal(fresh(seed).getStudent('COOP-B001').display_name, 'Latest Layla');
});

test('Noor retains unknown availability and no interests instead of fabricated matches or eligibility', () => {
  const student = fresh().getStudent('COOP-B004');
  assert.deepEqual(student.interests, []);
  assert.equal(student.availability_start, null);
  assert.equal(student.availability_end, null);
  assert.ok(!('eligibility_status' in student));
});

test('only the three published and open listings are searchable and counted as available', () => {
  const store = fresh();
  assert.deepEqual(ids(store.searchApproved('')), ELIGIBLE);
  assert.deepEqual(ids(store.searchApproved('')), SEED._meta.expected_test_results.eligible_for_recommendation);
  assert.equal(store.listOpportunities().length, 5);
  assert.equal(store.counts().approved, 3);
  assert.equal(store.counts().pending, 1);
  assert.deepEqual(ids(store.listOpportunities({ status: OPPORTUNITY_STATUS.PENDING })), ['OP-039']);
  assert.deepEqual(ids(store.listOpportunities({ status: OPPORTUNITY_STATUS.APPROVED })), ['OP-028', 'OP-031', 'OP-034', 'OP-036']);
});

test('search matches title or employer_name case-insensitively, with blank and no-match states', () => {
  const store = fresh();
  assert.deepEqual(ids(store.searchApproved('  EMIRATES ')), ['OP-028']);
  assert.deepEqual(ids(store.searchApproved('PRODUCT')), ['OP-034']);
  assert.deepEqual(ids(store.searchApproved(' intern ')), ELIGIBLE);
  assert.deepEqual(store.searchApproved('falcon'), []);
  assert.deepEqual(store.searchApproved('health'), []);
  assert.deepEqual(store.searchApproved('zzzz'), []);
});

test('student listing projection strips supervisor fields without removing them from shared records', () => {
  const store = fresh();
  noSupervisors(store.searchApproved(''));
  assert.equal(store.listOpportunities()[0].supervisor_name, 'R. Khan (synthetic)');
  assert.equal(SEED.published_listings[0].supervisor_contact, 'supervisor.op028@example.com');
});

test('direct applications to closed or unpublished IDs are blocked and create no records', () => {
  const store = fresh();
  for (const id of ['OP-036', 'OP-039']) {
    const result = store.submitApplication('COOP-B001', id);
    assert.equal(result.ok, false);
    assert.equal(result.code, 'not_approved');
    assert.match(result.message, /published and open/);
  }
  assert.equal(store.counts().applications, 0);
  assert.equal(store.listFacultyRecords().length, 0);
});

test('all three eligible seeded listings accept applications with linked review records', () => {
  const store = fresh();
  for (const id of ELIGIBLE) {
    const result = store.submitApplication('COOP-B001', id);
    assert.equal(result.ok, true);
    assert.equal(result.application.opportunity_id, id);
    assert.equal(result.application.student_id, 'COOP-B001');
    assert.equal(result.application.application_status, 'Submitted');
    assert.ok(Number.isFinite(Date.parse(result.application.submitted_at)));
    assert.equal(result.review.application_id, result.application.application_id);
    assert.equal(result.review.review_status, 'Not started');
  }
  assert.equal(store.counts().applications, 3);
});

test('duplicate applications are blocked per student and opportunity, while other students can apply', () => {
  const store = fresh();
  store.submitApplication('COOP-B001', 'OP-028');
  assert.equal(store.submitApplication('COOP-B001', 'OP-028').code, 'duplicate');
  assert.equal(store.submitApplication('COOP-B002', 'OP-028').ok, true);
  assert.equal(store.hasApplied('COOP-B001', 'OP-028'), true);
  assert.equal(store.hasApplied('COOP-B001', 'OP-031'), false);
  assert.equal(store.listStudentApplications('COOP-B001').length, 1);
  assert.equal(store.listStudentApplications('COOP-B002').length, 1);
  assert.equal(store.getApplicationFor('COOP-B001', 'OP-028').application_id, 'APP-001');
  assert.equal(store.getApplicationFor('COOP-B001', 'OP-031'), null);
});

test('unknown student or opportunity cannot receive an application', () => {
  const store = fresh();
  assert.equal(store.submitApplication('COOP-B999', 'OP-028').code, 'not_found');
  assert.equal(store.submitApplication('COOP-B001', 'OP-999').code, 'not_found');
  assert.equal(store.listFacultyRecords().length, 0);
});

test('application history excludes supervisors and separates application and placement status', () => {
  const store = fresh();
  store.submitApplication('COOP-B001', 'OP-028');
  const [mine] = store.listStudentApplications('COOP-B001');
  noSupervisors(mine);
  assert.equal(mine.opportunity.employer_name, 'Emirates Group');
  assert.equal(mine.opportunity.title, 'Aviation Analytics Intern');
  assert.equal(mine.application_status, 'Submitted');
  assert.equal(mine.placement_status, PLACEMENT_STATUS);
  assert.equal(PLACEMENT_STATUS, 'Not placed');
});

test('faculty records use the same IDs and latest submitted profile without supervisor handoff fields', () => {
  const store = fresh();
  store.submitApplication('COOP-B001', 'OP-028');
  const [record] = store.listFacultyRecords();
  noSupervisors(record);
  assert.equal(record.application.application_id, 'APP-001');
  assert.equal(record.opportunity.opportunity_id, 'OP-028');
  assert.equal(record.student.student_id, 'COOP-B001');
  assert.equal(record.student.profile_version, 2);
  assert.equal(record.review.review_id, 'REV-001');
  assert.equal(record.review.faculty_id, 'FAC-001');
  assert.equal(record.placement_status, 'Not placed');
});

test('profile corrections append a new submitted version and preserve old versions and evidence', () => {
  const storage = memoryStorage();
  const store = createStore(storage, SEED);
  const saved = store.updateDisplayName('COOP-B001', '  Layla H. ');
  assert.equal(saved.ok, true);
  assert.equal(saved.student.profile_version, 3);
  assert.equal(saved.student.profile_status, 'submitted');
  assert.equal(saved.student.display_name, 'Layla H.');
  const profiles = JSON.parse(storage.getItem(STORAGE_KEY)).student_profiles;
  assert.deepEqual(profiles.slice(0, 5), SEED.student_profiles);
  assert.equal(profiles.length, 6);
  assert.deepEqual(saved.student.skills, SEED.student_profiles[1].skills);
  assert.deepEqual(saved.student.interests, SEED.student_profiles[1].interests);
  assert.equal(saved.student.availability_start, '2027-01-01');
  assert.equal(store.getStudent('COOP-B001').profile_version, 3);
});

test('correction versions exceed drafts, and invalid display names create no version', () => {
  const seed = structuredClone(SEED);
  seed.student_profiles.push({ ...SEED.student_profiles[1], profile_version: 10, profile_status: 'draft' });
  const store = fresh(seed);
  assert.equal(store.updateDisplayName('COOP-B001', '  ').code, 'validation');
  assert.equal(store.updateDisplayName('COOP-B001', 'x'.repeat(61)).code, 'validation');
  assert.equal(store.getStudent('COOP-B001').profile_version, 2);
  assert.equal(store.updateDisplayName('COOP-B001', 'Layla New').student.profile_version, 11);
  assert.equal(store.updateDisplayName('COOP-B999', 'Name').code, 'not_found');
});

test('faculty view reflects a later immutable profile correction', () => {
  const store = fresh();
  store.submitApplication('COOP-B001', 'OP-028');
  store.updateDisplayName('COOP-B001', 'Layla New');
  assert.equal(store.listFacultyRecords()[0].student.display_name, 'Layla New');
});

test('valid HR submission uses canonical fields and unique OP IDs, unpublished until review', () => {
  const store = fresh();
  const first = store.submitOpportunity(VALID, { hrAuthorized: true });
  const second = store.submitOpportunity({ ...VALID, title: 'Second role' }, { hrAuthorized: true });
  assert.equal(first.ok, true);
  assert.equal(first.opportunity.opportunity_id, 'OP-040');
  assert.equal(second.opportunity.opportunity_id, 'OP-041');
  assert.equal(first.opportunity.publication_status, 'unpublished');
  assert.equal(first.opportunity.listing_status, 'open');
  assert.equal(first.opportunity.employer_name, 'Harbor Robotics');
  assert.equal(first.opportunity.work_mode, 'on-site');
  assert.equal(first.opportunity.version, 1);
  assert.equal(first.opportunity.submission_version, 1);
  assert.ok(!('organization_name' in first.opportunity));
  assert.ok(!('approval_status' in first.opportunity));
  assert.equal(store.counts().pending, 3);
  assert.deepEqual(store.searchApproved('harbor'), []);
});

test('canonical employer_name input is accepted at the HR form boundary', () => {
  const { organization_name, ...fields } = VALID;
  assert.equal(fresh().submitOpportunity({ ...fields, employer_name: organization_name }, { hrAuthorized: true }).opportunity.employer_name, organization_name);
});

test('HR authorization and required-field validation prevent records from being created', () => {
  const store = fresh();
  assert.equal(store.submitOpportunity(VALID, { hrAuthorized: false }).code, 'unauthorized');
  assert.equal(store.submitOpportunity(VALID).code, 'unauthorized');
  const invalid = store.submitOpportunity({ ...VALID, organization_name: ' ', title: '', description: '\n\t', location: ' ' }, { hrAuthorized: true });
  assert.equal(invalid.code, 'validation');
  assert.deepEqual(Object.keys(invalid.errors).sort(), ['description', 'location', 'organization_name', 'title']);
  assert.equal(store.listOpportunities().length, 5);
});

test('HR overlong fields are rejected and unsupported work modes fall back to hybrid', () => {
  const store = fresh();
  assert.match(store.submitOpportunity({ ...VALID, title: 'x'.repeat(101) }, { hrAuthorized: true }).errors.title, /100 characters or fewer/);
  assert.equal(store.submitOpportunity({ ...VALID, work_mode: 'unsupported' }, { hrAuthorized: true }).opportunity.work_mode, 'hybrid');
});

test('administrator publishes the same pending listing without changing shared fields', () => {
  const store = fresh();
  const before = store.listOpportunities().find((listing) => listing.opportunity_id === 'OP-039');
  assert.equal(store.approveOpportunity('OP-039').ok, true);
  assert.deepEqual(store.listOpportunities({ status: OPPORTUNITY_STATUS.PENDING }), []);
  const after = store.listOpportunities().find((listing) => listing.opportunity_id === 'OP-039');
  assert.deepEqual(after, { ...before, publication_status: 'published' });
  assert.deepEqual(ids(store.searchApproved('health')), ['OP-039']);
});

test('unknown or already-published listings cannot be approved; closed listings stay closed', () => {
  const store = fresh();
  assert.equal(store.approveOpportunity('OP-999').code, 'not_found');
  assert.equal(store.approveOpportunity('OP-028').code, 'already_approved');
  assert.equal(store.approveOpportunity('OP-036').code, 'already_approved');
  assert.equal(store.submitApplication('COOP-B001', 'OP-036').code, 'not_approved');
  const seed = structuredClone(SEED);
  seed.published_listings[4].listing_status = 'closed';
  const closed = fresh(seed);
  assert.equal(closed.approveOpportunity('OP-039').ok, true);
  assert.deepEqual(closed.searchApproved('health'), []);
  assert.equal(closed.submitApplication('COOP-B001', 'OP-039').code, 'not_approved');
});

test('read helpers and caller-owned seed cannot mutate stored shared records', () => {
  const seed = structuredClone(SEED);
  const store = fresh(seed);
  seed.published_listings[0].title = 'Changed outside';
  store.searchApproved('')[0].listing_status = 'closed';
  store.listOpportunities()[0].title = 'Hacked';
  store.getStudent('COOP-B001').skills[0].evidence_status = 'hacked';
  store.listStudents()[0].display_name = 'Hacked';
  store.getSkillsVocabulary()[0].label = 'Hacked';
  assert.deepEqual(ids(store.searchApproved('')), ELIGIBLE);
  assert.equal(store.getStudent('COOP-B001').skills[0].evidence_status, 'reviewed');
  assert.equal(store.listOpportunities()[0].title, 'Aviation Analytics Intern');
  assert.equal(store.getSkillsVocabulary()[0].label, SEED.skills_vocabulary[0].label);
});

test('records, immutable corrections and privacy projections persist across reloads', () => {
  const storage = memoryStorage();
  const first = createStore(storage, SEED);
  first.submitApplication('COOP-B001', 'OP-028');
  first.updateDisplayName('COOP-B001', 'Layla Updated');
  const reloaded = createStore(storage, SEED);
  assert.equal(reloaded.getStudent('COOP-B001').profile_version, 3);
  assert.equal(reloaded.listStudentApplications('COOP-B001')[0].opportunity.opportunity_id, 'OP-028');
  assert.equal(reloaded.isPersistent(), true);
  noSupervisors(reloaded.listStudentApplications('COOP-B001'));
});

test('old v1 browser data is isolated, and corrupt or foreign v2 storage resets safely', () => {
  const legacy = memoryStorage();
  legacy.setItem('ipp-demo-v1', JSON.stringify({ version: 1, students: [{ student_id: 'STU-001' }] }));
  assert.equal(createStore(legacy, SEED).getStudent('COOP-B001').profile_version, 2);
  assert.equal(STORAGE_KEY, 'ipp-demo-v2');
  for (const raw of ['not json', '{"version":99}', '[]', 'null', '{"version":1,"students":[]}']) {
    const storage = memoryStorage();
    storage.setItem(STORAGE_KEY, raw);
    assert.deepEqual(ids(createStore(storage, SEED).searchApproved('')), ELIGIBLE);
  }
});

test('blocked, unreadable or quota-limited storage keeps the demo usable and reports non-persistence', () => {
  const noStorage = createStore(null, SEED);
  assert.equal(noStorage.submitApplication('COOP-B001', 'OP-028').ok, true);
  assert.equal(noStorage.isPersistent(), false);
  const unreadable = createStore({ getItem() { throw new Error('blocked'); } }, SEED);
  assert.equal(unreadable.isPersistent(), false);
  const storage = memoryStorage();
  const store = createStore(storage, SEED);
  storage.setItem = () => { throw new Error('QuotaExceededError'); };
  assert.equal(store.submitApplication('COOP-B001', 'OP-028').ok, true);
  assert.equal(store.counts().applications, 1);
  assert.equal(store.isPersistent(), false);
});

test('reset restores exactly the shared seed, clears local activity and restarts IDs', () => {
  const storage = memoryStorage();
  const store = createStore(storage, SEED);
  store.submitOpportunity(VALID, { hrAuthorized: true });
  store.submitApplication('COOP-B001', 'OP-028');
  store.updateDisplayName('COOP-B001', 'Someone Else');
  store.reset();
  assert.deepEqual(store.listOpportunities(), SEED.published_listings);
  assert.deepEqual(store.getStudent('COOP-B001'), SEED.student_profiles[1]);
  assert.deepEqual(store.getSkillsVocabulary(), SEED.skills_vocabulary);
  assert.equal(store.listFacultyRecords().length, 0);
  assert.equal(createStore(storage, SEED).listOpportunities().length, 5);
  assert.equal(store.submitOpportunity(VALID, { hrAuthorized: true }).opportunity.opportunity_id, 'OP-040');
});

test('subscribers and refresh share changes across browser-local stores and unsubscribe cleanly', () => {
  const storage = memoryStorage();
  const a = createStore(storage, SEED);
  const b = createStore(storage, SEED);
  let calls = 0;
  const off = a.subscribe(() => calls++);
  a.submitOpportunity(VALID, { hrAuthorized: true });
  assert.equal(calls, 1);
  assert.equal(b.listOpportunities().length, 5);
  b.refresh();
  assert.equal(b.listOpportunities().length, 6);
  a.refresh();
  assert.equal(calls, 2);
  off();
  a.reset();
  assert.equal(calls, 2);
});

test('integrated Employer -> Admin -> Student -> Faculty journey keeps IDs and placement separate', () => {
  const storage = memoryStorage();
  const store = createStore(storage, SEED);
  const submitted = store.submitOpportunity(VALID, { hrAuthorized: true });
  const id = submitted.opportunity.opportunity_id;
  assert.equal(submitted.opportunity.publication_status, 'unpublished');
  assert.equal(store.submitApplication('COOP-B001', id).code, 'not_approved');
  assert.equal(store.searchApproved('harbor').length, 0);
  assert.ok(ids(store.listOpportunities({ status: OPPORTUNITY_STATUS.PENDING })).includes(id));
  store.approveOpportunity(id);
  assert.equal(store.searchApproved('harbor')[0].opportunity_id, id);
  const application = store.submitApplication('COOP-B001', id);
  assert.equal(application.ok, true);
  assert.equal(store.submitApplication('COOP-B001', id).code, 'duplicate');
  const [record] = createStore(storage, SEED).listFacultyRecords();
  assert.equal(record.opportunity.opportunity_id, id);
  assert.equal(record.student.student_id, 'COOP-B001');
  assert.equal(record.application.application_id, application.application.application_id);
  assert.equal(record.application.application_status, 'Submitted');
  assert.equal(record.placement_status, 'Not placed');
  assert.equal(store.listOpportunities().find((listing) => listing.opportunity_id === id).publication_status, 'published');
});

// ---- Activity feed, journey tracker, filter/sort (professional redesign) ----

test('activity feed records each hand-off, newest first, with the acting role', () => {
  const store = fresh();
  store.reset();
  const { opportunity } = store.submitOpportunity(VALID, { hrAuthorized: true });
  store.approveOpportunity(opportunity.opportunity_id);
  store.submitApplication('COOP-B001', opportunity.opportunity_id);
  store.updateDisplayName('COOP-B001', 'Layla H.');

  const feed = store.listActivity();
  assert.deepEqual(
    feed.map((entry) => entry.kind),
    ['profile_updated', 'application_submitted', 'opportunity_approved', 'opportunity_submitted', 'demo_reset'],
  );
  assert.deepEqual(feed.map((entry) => entry.role), ['student', 'student', 'admin', 'employer', 'system']);
  assert.match(feed[1].text, /Layla Hassan applied to “Controls Intern”/);
  assert.equal(feed[1].ref, 'APP-001');
  assert.equal(new Set(feed.map((entry) => entry.activity_id)).size, feed.length, 'activity IDs are unique');
  assert.ok(feed.every((entry) => !Number.isNaN(Date.parse(entry.at))));
  assert.equal(store.listActivity(2).length, 2, 'limit is honoured');
});

test('activity feed ignores failed actions and unchanged display names', () => {
  const store = fresh();
  store.submitOpportunity({ ...VALID, title: '' }, { hrAuthorized: true });
  store.submitOpportunity(VALID, { hrAuthorized: false });
  store.approveOpportunity('OP-028'); // already approved
  store.submitApplication('COOP-B001', 'OP-999');
  store.updateDisplayName('COOP-B001', 'Layla Hassan'); // same name
  assert.equal(store.listActivity().length, 0);
});

test('activity feed is capped so browser storage cannot grow without bound', () => {
  const store = fresh();
  for (let i = 0; i < 80; i += 1) store.submitOpportunity({ ...VALID, title: `Role ${i}` }, { hrAuthorized: true });
  assert.equal(store.listActivity().length, 60);
  assert.match(store.listActivity()[0].text, /Role 79/);
});

test('records saved before the activity feed existed still load', () => {
  const storage = memoryStorage();
  const legacy = JSON.parse(JSON.stringify(globalThis.IPPStore.seedState(SEED)));
  delete legacy.activity;
  storage.setItem(STORAGE_KEY, JSON.stringify(legacy));
  const store = createStore(storage, SEED);
  assert.equal(store.listOpportunities().length, 5);
  assert.deepEqual(store.listActivity(), []);
  store.submitOpportunity(VALID, { hrAuthorized: true });
  assert.equal(store.listActivity().length, 1);
});

test('journey: starts empty and advances one hand-off at a time while placement stays Not placed', () => {
  const store = fresh();
  let journey = store.getJourney();
  assert.equal(journey.opportunity, null);
  assert.deepEqual(journey.stages.map((s) => s.done), [false, false, false, false]);
  assert.equal(journey.complete, false);

  const { opportunity } = store.submitOpportunity(VALID, { hrAuthorized: true });
  journey = store.getJourney();
  assert.equal(journey.opportunity.opportunity_id, opportunity.opportunity_id);
  assert.equal(journey.opportunity.employer_name, 'Harbor Robotics');
  assert.deepEqual(journey.stages.map((s) => s.done), [true, false, false, false]);

  store.approveOpportunity(opportunity.opportunity_id);
  assert.deepEqual(store.getJourney().stages.map((s) => s.done), [true, true, false, false]);

  store.submitApplication('COOP-B001', opportunity.opportunity_id);
  journey = store.getJourney();
  assert.deepEqual(journey.stages.map((s) => s.done), [true, true, true, true]);
  assert.equal(journey.complete, true);
  assert.equal(journey.application.application_status, 'Submitted');
  assert.equal(journey.placement_status, 'Not placed');
  assert.deepEqual(journey.stages.map((s) => s.role), ['employer', 'admin', 'student', 'faculty']);
});

test('journey tracks the latest submitted record and ignores sample records', () => {
  const store = fresh();
  store.submitApplication('COOP-B001', 'OP-028'); // sample record: must not count as a demo journey
  assert.equal(store.getJourney().opportunity, null);
  store.submitOpportunity(VALID, { hrAuthorized: true });
  const second = store.submitOpportunity({ ...VALID, title: 'Second role' }, { hrAuthorized: true });
  assert.equal(store.getJourney().opportunity.opportunity_id, second.opportunity.opportunity_id);
});

test('searchApproved retains work-mode filters and newest/title sorts with shared canonical fields', () => {
  const store = fresh();
  const remote = store.submitOpportunity({ ...VALID, title: 'Alpha Remote Role', work_mode: 'Remote' }, { hrAuthorized: true });
  store.approveOpportunity(remote.opportunity.opportunity_id);
  assert.deepEqual(ids(store.searchApproved('', { workMode: 'Remote' })), ['OP-040']);
  assert.deepEqual(ids(store.searchApproved('', { workMode: 'remote' })), ['OP-040']);
  assert.deepEqual(ids(store.searchApproved('', { workMode: 'Hybrid' })), ['OP-034']);
  assert.equal(store.searchApproved('', { workMode: 'All' }).length, 4);
  assert.equal(store.searchApproved('', { workMode: 'bogus' }).length, 4);
  assert.deepEqual(ids(store.searchApproved('', { sort: 'newest' })), ['OP-040', 'OP-034', 'OP-031', 'OP-028']);
  assert.deepEqual(store.searchApproved('', { sort: 'title' }).map((listing) => listing.title), ['Alpha Remote Role', 'Aviation Analytics Intern', 'Energy Data Intern', 'Product Design Intern']);
  assert.deepEqual(ids(store.searchApproved('intern', { workMode: 'On-site', sort: 'title' })), ['OP-028', 'OP-031']);
  assert.deepEqual(ids(store.searchApproved('')), ['OP-028', 'OP-031', 'OP-034', 'OP-040']);
  noSupervisors(store.searchApproved('', { workMode: 'On-site', sort: 'title' }));
});

test('student applications include the linked review record; faculty reviewer is exposed read-only', () => {
  const store = fresh();
  store.submitApplication('COOP-B001', 'OP-031');
  const [mine] = store.listStudentApplications('COOP-B001');
  assert.equal(mine.review.review_id, 'REV-001');
  assert.equal(mine.review.review_status, 'Not started');
  assert.equal(store.getFaculty().faculty_id, 'FAC-001');
  store.getFaculty().display_name = 'Hacked';
  assert.equal(store.getFaculty().display_name, 'Dr. Sam Okafor');
});

// ---- Employer HR can view applications after a student applies ----

test('employer applications: empty until a student applies', () => {
  const store = fresh();
  assert.deepEqual(store.listEmployerApplications(), []);
  assert.deepEqual(store.applicantCounts(), {});
});

test('employer applications: after a student applies, HR sees the applicant, opportunity and statuses', () => {
  const store = fresh();
  const { opportunity } = store.submitOpportunity(VALID, { hrAuthorized: true });
  store.approveOpportunity(opportunity.opportunity_id);
  store.submitApplication('COOP-B001', opportunity.opportunity_id);

  const [entry] = store.listEmployerApplications();
  assert.equal(entry.application.application_id, 'APP-001');
  assert.equal(entry.application.application_status, 'Submitted');
  assert.equal(entry.application.opportunity_id, opportunity.opportunity_id);
  assert.equal(entry.opportunity.title, 'Controls Intern');
  assert.equal(entry.opportunity.employer_name, 'Harbor Robotics');
  assert.deepEqual(entry.student, { student_id: 'COOP-B001', display_name: 'Layla Hassan', profile_version: 2, profile_status: 'submitted' });
  assert.equal(entry.placement_status, 'Not placed', 'viewing an application is not a placement');
  assert.deepEqual(store.applicantCounts(), { [opportunity.opportunity_id]: 1 });
});

test('employer applications: data boundary, HR never receives faculty review records or extra student fields', () => {
  const store = fresh();
  store.submitApplication('COOP-B001', 'OP-028');
  const [entry] = store.listEmployerApplications();
  assert.deepEqual(Object.keys(entry).sort(), ['application', 'opportunity', 'placement_status', 'student']);
  assert.deepEqual(Object.keys(entry.student).sort(), ['display_name', 'profile_status', 'profile_version', 'student_id']);
  assert.equal('review' in entry, false);
  assert.equal(JSON.stringify(entry).includes('REV-001'), false, 'no review ID leaks to the employer view');
  assert.equal(JSON.stringify(entry).includes('FAC-001'), false, 'no faculty ID leaks to the employer view');
});

test('employer applications: newest first, counts per opportunity, and a later display-name change shows through', () => {
  const store = fresh();
  store.submitApplication('COOP-B001', 'OP-028');
  store.submitApplication('COOP-B001', 'OP-031');
  assert.deepEqual(store.listEmployerApplications().map((e) => e.application.application_id), ['APP-002', 'APP-001']);
  assert.deepEqual(store.applicantCounts(), { 'OP-028': 1, 'OP-031': 1 });

  store.updateDisplayName('COOP-B001', 'Layla H.');
  assert.ok(store.listEmployerApplications().every((e) => e.student.display_name === 'Layla H.'));
});

test('employer applications: failed or duplicate applications never show up for HR', () => {
  const store = fresh();
  const { opportunity } = store.submitOpportunity(VALID, { hrAuthorized: true });
  store.submitApplication('COOP-B001', opportunity.opportunity_id); // still Pending Review: rejected
  store.submitApplication('COOP-B001', 'OP-028');
  store.submitApplication('COOP-B001', 'OP-028'); // duplicate: rejected
  assert.equal(store.listEmployerApplications().length, 1);
  assert.deepEqual(store.applicantCounts(), { 'OP-028': 1 });
});

test('employer applications: results are copies, and reset clears them', () => {
  const store = fresh();
  store.submitApplication('COOP-B001', 'OP-028');
  store.listEmployerApplications()[0].student.display_name = 'Hacked';
  store.applicantCounts()['OP-028'] = 99;
  assert.equal(store.listEmployerApplications()[0].student.display_name, 'Layla Hassan');
  assert.equal(store.applicantCounts()['OP-028'], 1);
  store.reset();
  assert.deepEqual(store.listEmployerApplications(), []);
});

test('journey: the final hand-off names both Employer HR and Faculty as able to view the application', () => {
  const store = fresh();
  assert.equal(store.getJourney().stages[3].label, 'Visible to Employer HR and Faculty');
});


test('persisted empty, draft-only or malformed profiles fall back to selectable submitted seed profiles', () => {
  const invalidProfiles = [
    [],
    SEED.student_profiles.map((profile) => ({ ...profile, profile_status: 'draft' })),
    [{ ...SEED.student_profiles[1], interests: null }],
    [{ ...SEED.student_profiles[1], skills: 'SK-SQL' }],
    [{ ...SEED.student_profiles[1], availability_start: 123 }],
    [{ ...SEED.student_profiles[1], availability_end: {} }],
    [{ ...SEED.student_profiles[1], display_name: null }],
  ];
  for (const profiles of invalidProfiles) {
    const storage = memoryStorage();
    const persisted = seedState(SEED);
    persisted.student_profiles = profiles;
    storage.setItem(STORAGE_KEY, JSON.stringify(persisted));
    const store = createStore(storage, SEED);
    assert.equal(store.listStudents().length, 4);
    assert.deepEqual(store.getStudent('COOP-B001'), SEED.student_profiles[1]);
  }
});

test('journey safe projection excludes supervisors and closed listings never complete approval stage', () => {
  const seed = structuredClone(SEED);
  seed.published_listings[3].origin = 'demo';
  const journey = fresh(seed).getJourney();
  noSupervisors(journey);
  assert.equal(journey.opportunity.opportunity_id, 'OP-036');
  assert.equal(journey.stages[1].done, false);
  assert.equal(journey.complete, false);
});

test('activity history survives reload and optional-field migration caps oversized persisted history', () => {
  const storage = memoryStorage();
  const state = seedState(SEED);
  state.activity = Array.from({ length: 80 }, (_, index) => ({ activity_id: 'ACT-' + index, at: '2026-11-17T00:00:00Z', role: 'system', kind: 'test', text: 'Activity ' + index, ref: '' }));
  storage.setItem(STORAGE_KEY, JSON.stringify(state));
  const store = createStore(storage, SEED);
  assert.equal(store.listActivity().length, 60);
  assert.equal(store.listActivity()[0].text, 'Activity 79');
  assert.equal(store.listActivity().at(-1).text, 'Activity 20');
  store.submitApplication('COOP-B001', 'OP-028');
  const reloaded = createStore(storage, SEED);
  assert.equal(reloaded.listActivity().length, 60);
  assert.equal(reloaded.listActivity()[0].kind, 'application_submitted');
});
