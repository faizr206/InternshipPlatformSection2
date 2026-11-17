import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const read = (path) => readFile(new URL('../' + path, import.meta.url), 'utf8');
const [storeCode, uiCode, appCode, json, html] = await Promise.all([read('src/store.js'), read('src/ui.js'), read('src/app.js'), read('data/ipp_sample_data.json'), read('index.html')]);
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

async function boot({ fail = false, hash = '#student', prepare } = {}) {
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
  const stored = new Map();
  const requests = [];
  let shouldFail = fail;
  const context = vm.createContext({
    document, URL, console,
    location: { hash },
    history: { replaceState() {} },
    localStorage: { getItem: (key) => stored.get(key) || null, setItem: (key, value) => stored.set(key, value), removeItem: (key) => stored.delete(key) },
    addEventListener() {},
    scrollTo() {},
    setInterval() {},
    fetch: async (url) => { requests.push(String(url)); return { ok: !shouldFail, status: shouldFail ? 404 : 200, json: async () => JSON.parse(json) }; },
  });
  context.window = context;
  vm.runInContext(storeCode, context, { filename: 'src/store.js' });
  if (prepare) {
    const state = context.IPPStore.seedState(seed);
    prepare(state);
    stored.set(context.IPPStore.STORAGE_KEY, JSON.stringify(state));
  }
  vm.runInContext(uiCode, context, { filename: 'src/ui.js' });
  vm.runInContext(appCode, context, { filename: 'src/app.js' });
  await settle();
  return { document, requests, stored, recover: () => { shouldFail = false; }, get: (id) => document.getElementById(id) };
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
