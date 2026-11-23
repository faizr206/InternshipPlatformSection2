import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const read = (path) => readFile(new URL('../' + path, import.meta.url), 'utf8');
const [storeCode, uiCode, faqCode, appCode, json, faqText, html] = await Promise.all([read('src/store.js'), read('src/ui.js'), read('src/faq.js'), read('src/app.js'), read('data/ipp_sample_data.json'), read('data/faq.txt'), read('index.html')]);
const seed = JSON.parse(json);

// A bounded DOM substitute exercises rendering and event handlers, not browser layout.
class Element {
  constructor(tag, text = '') {
    this.tagName = tag;
    this.nodeType = tag === '#text' ? 3 : 1;
    this.children = [];
    this.attributes = {};
    this.listeners = {};
    this.dataset = {};
    this.text = text;
    this.hidden = false;
    this.classList = { add() {}, remove() {}, toggle() {} };
  }
  setAttribute(key, value) {
    this.attributes[key] = String(value);
    if (key === 'hidden') this.hidden = true;
    if (key.startsWith('data-')) this.dataset[key.slice(5)] = String(value);
  }
  removeAttribute(key) { delete this.attributes[key]; }
  getAttribute(key) { return this.attributes[key] ?? null; }
  querySelectorAll(selector) { return descendants(this).slice(1).filter((node) => matches(node, selector)); }
  get id() { return this.attributes.id; }
  get value() {
    if (this.currentValue !== undefined) return this.currentValue;
    if (this.tagName === 'select') return (this.children.find((node) => 'selected' in node.attributes) || this.children[0])?.value;
    return this.attributes.value || '';
  }
  set value(value) { this.currentValue = value; }
  append(node) { this.children.push(node); }
  replaceChildren(...nodes) { this.children = nodes; this.text = ''; }
  get textContent() { return this.text + this.children.map((node) => node.textContent).join(' '); }
  set textContent(text) { this.text = String(text); this.children = []; }
  addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener); }
  async fire(type) {
    for (const listener of this.listeners[type] || []) await listener({ target: this, currentTarget: this, preventDefault() {} });
  }
  focus() {}
  showModal() { this.open = true; }
  close() { this.open = false; return this.fire('close'); }
}
const matches = (node, selector) => {
  if (selector.startsWith('#')) return node.id === selector.slice(1);
  const attribute = /^(\w+)?\[([^=\]]+)(?:="([^"]*)")?\]$/.exec(selector);
  if (attribute) return (!attribute[1] || node.tagName === attribute[1]) && attribute[2] in node.attributes && (attribute[3] === undefined || node.attributes[attribute[2]] === attribute[3]);
  return node.tagName === selector;
};
const descendants = (element) => [element, ...element.children.flatMap(descendants)];
const settle = () => new Promise((resolve) => setImmediate(resolve));

async function boot({ fail = false, faqFail = false, hash = '#student', prepare, stored = new Map() } = {}) {
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
  const roots = ids.map((id) => { const element = new Element('div'); element.setAttribute('id', id); return element; });
  const all = () => roots.flatMap(descendants);
  const document = {
    baseURI: 'https://ray-suton.github.io/ipp-walking-skeleton-demo/',
    createElement: (tag) => new Element(tag),
    createElementNS: (namespace, tag) => new Element(tag),
    createTextNode: (text) => new Element('#text', text),
    getElementById: (id) => all().find((node) => node.id === id),
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; },
    querySelectorAll(selector) {
      const [rootSelector, childSelector] = selector.split(' ');
      const containers = all().filter((node) => matches(node, rootSelector));
      if (!childSelector) return containers;
      return containers.flatMap((node) => descendants(node).slice(1)).filter((node) => matches(node, childSelector));
    },
  };
  const requests = [];
  let shouldFail = fail;
  let faqShouldFail = faqFail;
  const context = vm.createContext({
    document, URL, console,
    location: { hash },
    history: { replaceState() {} },
    localStorage: { getItem: (key) => stored.get(key) || null, setItem: (key, value) => stored.set(key, value), removeItem: (key) => stored.delete(key) },
    addEventListener() {},
    scrollTo() {},
    setInterval() {},
    fetch: async (url) => {
      requests.push(String(url));
      const failed = String(url).endsWith('faq.txt') ? faqShouldFail : shouldFail;
      return { ok: !failed, status: failed ? 404 : 200, json: async () => JSON.parse(json), text: async () => faqText };
    },
  });
  context.window = context;
  vm.runInContext(storeCode, context, { filename: 'src/store.js' });
  if (prepare) {
    const state = context.IPPStore.seedState(seed);
    prepare(state);
    stored.set(context.IPPStore.STORAGE_KEY, JSON.stringify(state));
  }
  vm.runInContext(uiCode, context, { filename: 'src/ui.js' });
  vm.runInContext(faqCode, context, { filename: 'src/faq.js' });
  vm.runInContext(appCode, context, { filename: 'src/app.js' });
  await settle();
  return { document, requests, stored, recover: () => { shouldFail = false; }, failFaq: (on) => { faqShouldFail = on; }, get: (id) => document.getElementById(id) };
}

function assertNoSupervisorData(text) {
  for (const listing of seed.published_listings) {
    assert.ok(!text.includes(listing.supervisor_name), 'supervisor name leaked');
    assert.ok(!text.includes(listing.supervisor_contact), 'supervisor contact leaked');
  }
}

test('UI loads the shared seed relative to the GitHub Pages path and renders only three eligible listings', async () => {
  const app = await boot();
  assert.deepEqual(app.requests, ['https://ray-suton.github.io/ipp-walking-skeleton-demo/data/ipp_sample_data.json']);
  const text = app.get('results').textContent;
  for (const id of ['OP-028', 'OP-031', 'OP-034']) assert.ok(text.includes(id));
  for (const id of ['OP-036', 'OP-039']) assert.ok(!text.includes(id));
  assert.match(app.get('page-title').textContent, /Layla Hassan/);
  assert.equal(app.get('demo-student').children.length, 4);
  assert.equal(app.get('demo-student').value, 'COOP-B001');
  assert.match(app.get('demo-student').textContent, /Layla Hassan · COOP-B001 · v2/);
  assert.match(app.get('panel-profile').textContent, /SQL \(reviewed\)/);
  assertNoSupervisorData(app.get('view').textContent);
});

test('UI shows unknown interests and availability when selecting Noor instead of inventing values', async () => {
  const app = await boot();
  app.get('demo-student').value = 'COOP-B004';
  await app.get('demo-student').fire('change');
  assert.match(app.get('page-title').textContent, /Noor Al Hashimi/);
  assert.match(app.get('panel-profile').textContent, /Missing: interests not provided/);
  assert.match(app.get('panel-profile').textContent, /Missing: availability unknown/);
  assert.match(app.get('panel-profile').textContent, /Excel \(self_declared\)/);
  assertNoSupervisorData(app.get('view').textContent);
});

test('application confirmation, resulting student application and duplicate prevention never render supervisors', async () => {
  const app = await boot();
  const listing = descendants(app.get('results')).find((node) => node.tagName === 'article' && node.textContent.includes('OP-028'));
  const apply = descendants(listing).find((node) => node.tagName === 'button' && /^\s*Apply\b/.test(node.textContent));
  await apply.fire('click');
  assert.equal(app.get('apply-dialog').open, true);
  assert.match(app.get('apply-facts').textContent, /OP-028/);
  assert.match(app.get('apply-facts').textContent, /Layla Hassan/);
  assertNoSupervisorData(app.get('apply-facts').textContent);
  await app.get('apply-confirm').fire('click');
  assert.equal(app.get('apply-dialog').open, false);
  assert.match(app.get('panel-applications').textContent, /APP-001/);
  assert.match(app.get('panel-applications').textContent, /OP-028/);
  assert.match(app.get('panel-applications').textContent, /Not placed/);
  assert.match(app.get('applied-OP-028').textContent, /Application submitted/);
  assert.equal(descendants(app.get('results')).filter((node) => node.tagName === 'button' && /^\s*Apply\b/.test(node.textContent)).length, 2);
  assertNoSupervisorData(app.get('view').textContent + app.get('toast').textContent);
});

test('seed-load failure is visible and retry initializes the real app', async () => {
  const app = await boot({ fail: true });
  assert.match(app.get('view').textContent, /Unable to load synthetic demo data/);
  const retry = descendants(app.get('view')).find((node) => node.tagName === 'button');
  assert.equal(retry.textContent, 'Retry loading data');
  app.recover();
  await retry.fire('click');
  await settle();
  assert.match(app.get('page-title').textContent, /Layla Hassan/);
  assert.equal(app.requests.length, 2);
});

function withApplications(state) {
  state.applications = [
    { application_id: 'APP-001', opportunity_id: 'OP-028', student_id: 'COOP-B001', application_status: 'Submitted', submitted_at: '2026-11-17T08:00:00Z' },
    { application_id: 'APP-002', opportunity_id: 'OP-031', student_id: 'COOP-B002', application_status: 'Submitted', submitted_at: '2026-11-17T08:01:00Z' },
  ];
  state.reviews = state.applications.map((application, index) => ({ review_id: 'REV-00' + (index + 1), application_id: application.application_id, faculty_id: 'FAC-001', review_status: 'Not started' }));
}

test('student journey and activity exclude unavailable listings and other students while retaining allowed activity', async () => {
  for (const trackedId of ['OP-039', 'OP-036']) {
    const app = await boot({ prepare(state) {
      withApplications(state);
      state.published_listings.find((listing) => listing.opportunity_id === trackedId).origin = 'demo';
      state.activity = [
        ['OP-039', 'employer', 'Health Data Intern'],
        ['OP-036', 'employer', 'BI Dashboard Intern'],
        ['COOP-B002', 'student', 'Private profile update'],
        ['APP-002', 'student', 'Private application update'],
        ['OP-028', 'admin', 'Visible listing update'],
        ['COOP-B001', 'student', 'Own profile update'],
        ['APP-001', 'student', 'Own application update'],
      ].map(([ref, role, text], index) => ({ activity_id: 'ACT-00' + index, at: '2026-11-17T08:00:00Z', kind: 'test', ref, role, text }));
    } });
    const rail = app.get('rail').textContent;
    for (const hidden of ['OP-039', 'OP-036', 'Health Data Intern', 'BI Dashboard Intern', 'COOP-B002', 'APP-002', 'Private profile update', 'Private application update']) {
      assert.ok(!rail.includes(hidden), trackedId + ': rail exposed ' + hidden);
    }
    for (const visible of ['Visible listing update', 'Own profile update', 'Own application update']) assert.ok(rail.includes(visible), 'allowed activity was hidden');
    assert.match(rail, /No published and open tracked listing yet/);
    assertNoSupervisorData(rail + app.get('view').textContent);
  }
});

test('employer applicants retain canonical listing and submitted profile details', async () => {
  const app = await boot({ hash: '#employer/applicants', prepare: withApplications });
  const applicants = app.get('panel-applicants').textContent;
  for (const text of ['Layla Hassan', 'Arjun Mehta', 'OP-028', 'OP-031', 'APP-001', 'APP-002', 'Aviation Analytics Intern', 'Energy Data Intern']) assert.ok(applicants.includes(text), text);
  assert.doesNotMatch(applicants, /undefined/);
  assertNoSupervisorData(applicants);
});

// ---------- Internship Assistant (FAQ chatbot) ----------

const FAQ_URL = 'https://ray-suton.github.io/ipp-walking-skeleton-demo/data/faq.txt';
const SEED_URL = 'https://ray-suton.github.io/ipp-walking-skeleton-demo/data/ipp_sample_data.json';
const buttons = (root) => descendants(root).filter((node) => node.tagName === 'button');
const buttonNamed = (root, pattern) => buttons(root).find((node) => pattern.test(node.textContent.trim()));
const FAQ_KEY = 'ipp-faq-v1';

async function ask(app, text) {
  app.get('chat-input').value = text;
  await app.get('chat-form').fire('submit');
}
// Input events bubble to the form in a real browser; the DOM substitute does not, so deliver them explicitly.
async function typeInto(app, formId, fieldId, value) {
  const field = app.get(fieldId);
  field.value = value;
  for (const listener of app.get(formId).listeners.input || []) await listener({ target: field, currentTarget: app.get(formId), preventDefault() {} });
}

test('assistant: reachable from the app, loads the FAQ relative to the Pages path, and makes no other requests', async () => {
  const overview = await boot({ hash: '#overview' });
  assert.ok(descendants(overview.get('view')).some((node) => node.tagName === 'a' && node.attributes.href === '#assistant' && /Ask the Internship Assistant/.test(node.textContent)), 'Overview button');
  assert.deepEqual(overview.requests, [SEED_URL], 'the FAQ is only fetched when the assistant is opened');

  const app = await boot({ hash: '#assistant' });
  assert.deepEqual(app.requests.slice().sort(), [FAQ_URL, SEED_URL].sort());
  assert.match(app.get('page-title').textContent, /Ask the Internship Assistant/);
  assert.ok(app.get('view').textContent.includes('Prototype. Synthetic data. Not official university policy.'));
  assert.match(app.get('chat-privacy').textContent, /don't type personal information/);
  assert.equal(app.get('chat-input').attributes.disabled, undefined, 'input is enabled once the FAQ has loaded');
});

test('assistant: an FAQ question is answered word for word with its FAQ section as the source', async () => {
  const app = await boot({ hash: '#assistant' });
  await ask(app, 'Can I intern remotely?');
  const log = app.get('chat-log').textContent;
  assert.match(log, /Can I intern remotely\?/);
  assert.ok(log.includes('Yes. Placements are on site; remote roles are not approved.'));
  assert.match(log, /Source:\s*FAQ · Placements/);
  assert.match(log, /“Are placements on site\?”/);
  assert.equal(app.get('chat-input').value, '', 'the input is cleared after sending');
});

test('assistant: a suggested question can be asked with one click', async () => {
  const app = await boot({ hash: '#assistant' });
  const chip = buttons(app.get('view')).find((node) => /\bsuggestion\b/.test(node.className || '') && node.textContent === 'Who enters my final grade?');
  assert.ok(chip, 'suggestion chip for an approved question');
  await chip.fire('click');
  assert.ok(app.get('chat-log').textContent.includes('The faculty member assigned to your internship.'));
  assert.match(app.get('chat-log').textContent, /Source:\s*FAQ · Grading/);
});

test('assistant: an unknown question says "I don\'t know yet", invents nothing, and is saved for the coordinator', async () => {
  const app = await boot({ hash: '#assistant' });
  await ask(app, 'Are co-op students paid?');
  const log = app.get('chat-log').textContent;
  assert.ok(log.includes("I don't know yet. I've noted your question for the coordinator."));
  assert.doesNotMatch(log, /Source:/, 'an unknown reply has no FAQ source');
  assert.match(log, /unanswered questions/);
  const saved = JSON.parse(app.stored.get(FAQ_KEY));
  assert.equal(saved.unanswered.length, 1);
  assert.equal(saved.unanswered[0].question, 'Are co-op students paid?');
});

test('assistant: the lab test plan, 8 FAQ questions, 2 reworded, 1 unknown, behaves as specified', async () => {
  const app = await boot({ hash: '#assistant' });
  const faqLines = faqText.trim().split('\n').map((line) => /^Section: (.+?) \| Q: (.+?) \| A: (.+)$/.exec(line));
  for (const [, section, question, answer] of faqLines) {
    await ask(app, question);
    const log = app.get('chat-log').textContent;
    assert.ok(log.includes(answer), `answer for: ${question}`);
    assert.ok(log.includes(`FAQ · ${section}`), `source for: ${question}`);
  }
  await ask(app, 'Can I intern remotely?');
  assert.ok(app.get('chat-log').textContent.split('Yes. Placements are on site; remote roles are not approved.').length >= 3, 'the reworded question gets the on-site answer');
  await ask(app, 'Will I get money?');
  await ask(app, 'Are co-op students paid?');
  const unknownReplies = app.get('chat-log').textContent.split("I don't know yet. I've noted your question for the coordinator.").length - 1;
  assert.equal(unknownReplies, 2);
});

test('assistant: personal information is refused, never echoed, and never stored', async () => {
  const app = await boot({ hash: '#assistant' });
  await ask(app, 'my email is layla@example.com, are co-op students paid?');
  const log = app.get('chat-log').textContent;
  assert.match(log, /Please don't share personal information/);
  assert.match(log, /message withheld/);
  assert.ok(!log.includes('layla@example.com'));
  assert.ok(![...app.stored.values()].some((value) => value.includes('layla@example.com')));
  assert.equal(JSON.parse(app.stored.get(FAQ_KEY) || '{"unanswered":[]}').unanswered.length, 0, 'not saved as an unanswered question');
});

test('assistant: if the FAQ file cannot load, the chat is disabled with a retry, and it works after recovery', async () => {
  const app = await boot({ hash: '#assistant', faqFail: true });
  assert.match(app.get('view').textContent, /Could not load the approved FAQ/);
  assert.ok('disabled' in app.get('chat-input').attributes);
  app.failFaq(false);
  await buttonNamed(app.get('view'), /Retry loading the FAQ/).fire('click');
  await settle();
  assert.ok(!('disabled' in app.get('chat-input').attributes));
  await ask(app, 'How do I resubmit?');
  assert.ok(app.get('chat-log').textContent.includes('Submit a new version. The old version is kept and never overwritten.'));
});

test('coordinator: unanswered questions appear in the Administrator view; added entries need approval before the assistant uses them', async () => {
  const storage = new Map();
  const student = await boot({ hash: '#assistant', stored: storage });
  await ask(student, 'Are co-op students paid?');
  await ask(student, 'Will I get money?');

  const admin = await boot({ hash: '#admin/faq', stored: storage });
  assert.ok(admin.requests.includes(FAQ_URL));
  const panel = admin.get('panel-faq').textContent;
  assert.match(panel, /Coordinator approval required/);
  assert.match(panel, /Unanswered questions \(2\)/);
  assert.ok(panel.includes('Are co-op students paid?') && panel.includes('Will I get money?'));
  assert.match(admin.get('tab-faq').textContent, /Assistant FAQ\s*2/);

  // the coordinator turns one unanswered question into a draft entry
  await buttonNamed(admin.get('panel-faq'), /^Write an answer/).fire('click');
  assert.ok(['Will I get money?', 'Are co-op students paid?'].includes(admin.get('faq-question').value) || admin.get('faq-question').attributes.value, 'the form is prefilled');
  await typeInto(admin, 'faq-form', 'faq-section', 'Pay');
  await typeInto(admin, 'faq-form', 'faq-question', 'Are co-op students paid?');
  await typeInto(admin, 'faq-form', 'faq-answer', 'Pay depends on the employer and is listed in the opportunity.');
  await admin.get('faq-form').fire('submit');
  assert.match(admin.get('panel-faq').textContent, /Pending entries \(1\)/);
  assert.match(admin.get('toast').textContent, /added as Pending/);
  assert.equal(JSON.parse(storage.get(FAQ_KEY)).added[0].status, 'pending');

  const beforeApproval = await boot({ hash: '#assistant', stored: storage });
  await ask(beforeApproval, 'Are co-op students paid?');
  assert.ok(beforeApproval.get('chat-log').textContent.includes("I don't know yet."), 'pending entries are not used');

  const approver = await boot({ hash: '#admin/faq', stored: storage });
  await buttonNamed(approver.get('panel-faq'), /^Approve/).fire('click');
  assert.match(approver.get('toast').textContent, /ADD-001 approved/);
  assert.match(approver.get('toast').textContent, /1 unanswered question is now covered/);
  assert.match(approver.get('panel-faq').textContent, /Pending entries \(0\)/);
  assert.match(approver.get('panel-faq').textContent, /Approved FAQ \(9\)/);

  const afterApproval = await boot({ hash: '#assistant', stored: storage });
  await ask(afterApproval, 'Are co-op students paid?');
  const log = afterApproval.get('chat-log').textContent;
  assert.ok(log.includes('Pay depends on the employer and is listed in the opportunity.'));
  assert.match(log, /Source:\s*FAQ · Pay/);
  assert.match(log, /added by the coordinator/);
});

test('coordinator: the add form validates, and rejects personal information and duplicate questions', async () => {
  const app = await boot({ hash: '#admin/faq' });
  await admin_submit(app, { section: '', question: '', answer: '' });
  assert.match(app.get('faq-form').textContent, /Section is required/);
  assert.match(app.get('faq-form').textContent, /Question is required/);
  assert.match(app.get('faq-form').textContent, /Answer is required/);
  await admin_submit(app, { section: 'Pay', question: 'Is it paid?', answer: 'Email me at boss@corp.com' });
  assert.match(app.get('faq-form').textContent, /personal information/);
  await admin_submit(app, { section: 'Pay', question: 'Are placements on site?', answer: 'Maybe.' });
  assert.match(app.get('faq-form').textContent, /already exists \(FAQ-001\)/);
  assert.doesNotMatch(app.get('panel-faq').textContent, /Pending entries \(1\)/);

  async function admin_submit(page, values) {
    for (const [name, value] of Object.entries(values)) await typeInto(page, 'faq-form', `faq-${name}`, value);
    await page.get('faq-form').fire('submit');
  }
});

test('reset clears the assistant state: unanswered questions, pending entries and the conversation', async () => {
  const storage = new Map();
  const first = await boot({ hash: '#assistant', stored: storage });
  await ask(first, 'Are co-op students paid?');
  assert.equal(JSON.parse(storage.get(FAQ_KEY)).unanswered.length, 1);
  await first.get('reset-btn').fire('click');
  assert.equal(first.get('reset-dialog').open, true);
  await first.get('reset-confirm').fire('click');
  assert.deepEqual(JSON.parse(storage.get(FAQ_KEY)).unanswered, []);
  assert.doesNotMatch(first.get('chat-log').textContent, /co-op/);
});
