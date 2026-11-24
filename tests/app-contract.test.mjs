import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

await import('../src/ui.js'); // publishes IPPUI (pure at load time, so it works in Node)
await import('../src/faq.js'); // publishes IPPFaq (pure: used to check the chatbot config)
const { ICON_NAMES } = globalThis.IPPUI;

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), 'utf8');
const SOURCES = ['src/store.js', 'src/ui.js', 'src/faq.js', 'src/app.js'];

test('index.html loads the demo without remote script, style or media dependencies', async () => {
  const html = await read('index.html');
  const css = await read('styles.css');
  assert.deepEqual([...html.matchAll(/<(?:script|link|img|iframe|source)\b[^>]*\b(?:src|href)="(?:https?:)?\/\/[^"]+"/g)], [], 'no external assets');
  assert.doesNotMatch(css, /@import|url\(\s*['"]?(?:https?:)?\/\//, 'stylesheet pulls nothing remote');
  assert.match(html, /<script src="src\/store\.js(?:\?v=[0-9a-f]+)?"><\/script>\s*<script src="src\/ui\.js(?:\?v=[0-9a-f]+)?"><\/script>\s*<script src="src\/faq\.js(?:\?v=[0-9a-f]+)?"><\/script>\s*<script src="src\/app\.js(?:\?v=[0-9a-f]+)?"><\/script>/, 'scripts load in dependency order');
  assert.match(html, /<link rel="stylesheet" href="styles\.css(?:\?v=[0-9a-f]+)?"/);
});

test('the persistent banner discloses simulated roles, synthetic data and browser-local storage', async () => {
  const html = await read('index.html');
  assert.match(html, /Role switching and HR authorization are\s*<strong>simulated<\/strong>/);
  assert.match(html, /synthetic/);
  assert.match(html, /stored only in this browser/);
  assert.match(html, /not shared across users or\s*devices/);
  for (const deferred of ['Real authentication', 'Shared central storage', 'Eligibility verification', 'placement decisions']) {
    assert.ok(html.includes(deferred), `deferred item missing: ${deferred}`);
  }
});

test('the footer states this is not a production system and not tied to a real employer', async () => {
  const html = await read('index.html');
  assert.match(html, /Not a production system and not\s+affiliated with any real employer/);
});

test('reset and apply flows use confirmation dialogs with a safe default', async () => {
  const html = await read('index.html');
  assert.match(html, /<dialog id="reset-dialog"/);
  assert.match(html, /id="reset-cancel" autofocus/, 'destructive reset must default to Cancel');
  assert.match(html, /<dialog id="apply-dialog"/);
  assert.match(html, /does <strong>not<\/strong> approve a placement/);
});

test('no source file injects user text as HTML', async () => {
  for (const path of SOURCES) {
    const code = await read(path);
    assert.doesNotMatch(code, /\.(?:inner|outer)HTML\s*=|insertAdjacentHTML|document\.write|\beval\(|new Function\(/, path);
  }
});

test('the Overview plus all four Lab 3 roles have views; the demo opens on the Overview', async () => {
  const app = await read('src/app.js');
  for (const label of ['Overview', 'Employer HR', 'University Administrator', 'Student', 'Faculty Reviewer', 'Internship Assistant']) {
    assert.ok(app.includes(`label: '${label}'`), `missing route ${label}`);
  }
  assert.match(app, /VIEWS = \{ overview: overviewView, student: studentView, employer: employerView, admin: adminView, faculty: facultyView, assistant: assistantView \}/);
  assert.match(app, /DEFAULT_ROUTE = 'overview'/);
});

test('statuses stay separate: no view can show an application as placed', async () => {
  for (const path of ['src/app.js', 'src/ui.js']) {
    const code = await read(path);
    assert.match(await read('src/app.js'), /PLACEMENT_STATUS/, 'views read the shared constant');
    assert.doesNotMatch(code.replaceAll('Not placed', ''), /\bplaced\b/i, `${path}: the only "placed" wording allowed is "Not placed"`);
  }
});

test('the static server serves exactly what index.html needs and nothing else (no course documents)', async () => {
  const server = await read('scripts/serve.mjs');
  const html = await read('index.html');
  const needed = [...html.matchAll(/<(?:script src|link rel="stylesheet" href)="([^"?]+)(?:\?[^"]*)?"/g)].map((match) => match[1]);
  assert.ok(needed.length >= 4, 'found the referenced files');
  for (const file of needed) assert.ok(server.includes(`'/${file}'`), `server must allow /${file}`);
  assert.doesNotMatch(server, /\.docx|\.png|\.md['"]/);
  assert.match(server, /ALLOWED/);
});

test('every icon the UI asks for exists (a typo would silently render an empty icon)', async () => {
  const app = await read('src/app.js');
  const used = new Set();
  for (const pattern of [/\bicon\(\s*'([A-Za-z]+)'/g, /\bicon:\s*'([A-Za-z]+)'/g, /emptyState\(\s*'([A-Za-z]+)'/g]) {
    for (const match of app.matchAll(pattern)) used.add(match[1]);
  }
  const activityMap = /ACTIVITY_ICON = \{([^}]+)\}/.exec(app);
  for (const match of (activityMap ? activityMap[1] : '').matchAll(/:\s*'([A-Za-z]+)'/g)) used.add(match[1]);
  assert.ok(used.size >= 15, `expected many icons in use, found ${used.size}`);
  const missing = [...used].filter((name) => !ICON_NAMES.includes(name));
  assert.deepEqual(missing, [], 'icons used but not defined in ui.js');
});

test('every CSS class the UI sets is defined in styles.css (catches typos and forgotten styles)', async () => {
  const app = await read('src/app.js');
  const css = await read('styles.css');
  const html = await read('index.html');
  const defined = new Set([...css.matchAll(/\.([A-Za-z][\w-]*)/g)].map((match) => match[1]));
  const used = new Set();
  for (const match of app.matchAll(/class:\s*'([^'$]+)'/g)) match[1].split(/\s+/).forEach((token) => used.add(token));
  for (const match of html.matchAll(/class="([^"]+)"/g)) match[1].split(/\s+/).forEach((token) => used.add(token));
  // Template-literal classes (e.g. `chip chip-${kind}`) are covered by listing their expansions.
  for (const name of ['chip-approved', 'chip-pending', 'chip-submitted', 'chip-neutral', 'chip-new', 'act-employer', 'act-admin', 'act-student', 'act-faculty', 'act-system']) used.add(name);
  const undefinedClasses = [...used].filter((token) => !defined.has(token));
  assert.deepEqual(undefinedClasses, []);
});

test('styles: hidden attribute always wins, motion respects reduced-motion, tiles have six tones', async () => {
  const css = await read('styles.css');
  assert.match(css, /\[hidden\]\s*\{\s*display:\s*none\s*!important/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)[^}]*\{[^}]*animation:\s*none\s*!important/s);
  for (let i = 0; i < 6; i += 1) assert.match(css, new RegExp(`\\.tone-${i}\\b`));
});

test('the server allowlist exposes the shared JSON seed at its canonical path', async () => {
  const server = await read('scripts/serve.mjs');
  assert.match(server, /\['\/data\/ipp_sample_data\.json', \['data\/ipp_sample_data\.json', 'application\/json; charset=utf-8'\]\]/);
  const app = await read('src/app.js');
  assert.match(app, /new URL\('data\/ipp_sample_data\.json', document\.baseURI\)/);
});

// ---------- Internship Assistant: hard requirements from the Sprint 2 lab ----------

test('no API key, token or secret is committed anywhere in the published files', async () => {
  const files = ['index.html', 'styles.css', 'package.json', 'README.md', 'PROJECT_DESCRIPTION.md', 'docs/assistant.md', 'src/store.js', 'src/ui.js', 'src/faq.js', 'src/app.js', 'scripts/serve.mjs', 'scripts/stamp.mjs', 'data/faq.txt', 'data/chatbot-config.json', 'data/ipp_sample_data.json'];
  const secretPatterns = [/\bsk-[A-Za-z0-9_-]{20,}/, /\bbearer\s+[A-Za-z0-9._-]{20,}/i, /api[_-]?key["']?\s*[:=]\s*["'][^"']{8,}/i, /secret["']?\s*[:=]\s*["'][^"']{8,}/i, /\bAKIA[0-9A-Z]{16}\b/, /\bgh[pousr]_[A-Za-z0-9]{20,}/, /\bxox[bpas]-/, /-----BEGIN [A-Z ]*PRIVATE KEY-----/];
  for (const path of files) {
    const text = await read(path);
    for (const pattern of secretPatterns) assert.doesNotMatch(text, pattern, `${path} looks like it contains a secret (${pattern})`);
  }
});

test('the assistant makes no third-party requests: the only fetches are the seed and the FAQ file, by relative URL', async () => {
  const app = await read('src/app.js');
  const faq = await read('src/faq.js');
  const relativeFetches = [...app.matchAll(/fetch\(new URL\('([^']+)', document\.baseURI\)/g)].map((match) => match[1]);
  assert.equal([...app.matchAll(/\bfetch\(/g)].length, relativeFetches.length, 'every fetch is a relative URL resolved against the page');
  assert.deepEqual(relativeFetches.sort(), ['data/chatbot-config.json', 'data/faq.txt', 'data/ipp_sample_data.json']);
  assert.doesNotMatch(app + faq, /\bhttps?:\/\/(?!www\.w3\.org)/, 'no absolute URLs in the code');
  assert.doesNotMatch(app + faq, /XMLHttpRequest|WebSocket|sendBeacon|EventSource|importScripts/);
});

test('the lab wording is exact: banner, unknown reply, coordinator approval label and the assistant button', async () => {
  const app = await read('src/app.js');
  const faq = await read('src/faq.js');
  const html = await read('index.html');
  assert.ok(app.includes("'Prototype. Synthetic data. Not official university policy.'"));
  assert.ok(faq.includes(`"I don't know yet. I've noted your question for the coordinator."`));
  assert.match(app, /Coordinator approval required/);
  assert.match(html, /id="assistant-btn" href="#assistant">[\s\S]*<span>Ask the Internship Assistant<\/span>/);
  assert.match(app, /'Ask the Internship Assistant'/);
});

test('the approved FAQ is a plain file in the repository, served by the local server and loaded by relative URL', async () => {
  const server = await read('scripts/serve.mjs');
  assert.match(server, /\['\/data\/faq\.txt', \['data\/faq\.txt', 'text\/plain; charset=utf-8'\]\]/);
  assert.match(server, /\['\/src\/faq\.js'/);
  const gitignore = await read('.gitignore');
  assert.match(gitignore, /^!data\/faq\.txt$/m, 'faq.txt is published');
  const faqText = await read('data/faq.txt');
  assert.equal(faqText.trim().split('\n').length, 8);
  assert.ok(faqText.trim().split('\n').every((line) => /^Section: .+ \| Q: .+ \| A: .+$/.test(line)));
});

test('the assistant engine has no DOM, network or language-model dependency (pure, deterministic text matching)', async () => {
  const code = (await read('src/faq.js')).replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, ''); // judge the code, not the comments
  assert.doesNotMatch(code, /\bdocument\b|\bwindow\b|\bfetch\b|\bXMLHttpRequest\b|\bimport\s*\(|\brequire\s*\(/);
  assert.doesNotMatch(code, /openai|anthropic|gemini|\bllm\b|completion/i, 'no AI service is called from the engine');
  assert.doesNotMatch(code, /\bfetch\b|XMLHttpRequest/, 'the engine only validates embed URLs; it never loads them');
});

test('optional Botpress mode is inert by default and can only ever hold valid, public embed URLs', async () => {
  const config = JSON.parse(await read('data/chatbot-config.json'));
  const parsed = globalThis.IPPFaq.parseChatbotConfig(config);
  assert.ok(parsed.ok || config.botpress.enabled !== true, 'an enabled config must pass validation');
  assert.ok(Array.isArray(config.botpress.scripts));
  const server = await read('scripts/serve.mjs');
  assert.match(server, /\['\/data\/chatbot-config\.json', \['data\/chatbot-config\.json', 'application\/json; charset=utf-8'\]\]/);
  assert.match(await read('.gitignore'), /^!data\/chatbot-config\.json$/m);
  const app = await read('src/app.js');
  assert.doesNotMatch(app, /botpress\.cloud|bpcontent\.cloud/, 'no embed host or URL is hard-coded in the UI code');
  assert.match(app, /Faq\.parseChatbotConfig\(config\)/, 'the UI only loads scripts that passed validation');
});
