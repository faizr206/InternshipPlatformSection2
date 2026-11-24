/*
 * IPP Internship Assistant engine: FAQ parsing, matching, privacy guard and coordinator-approval store.
 *
 * Classic script that publishes `IPPFaq` on globalThis. Pure logic, no DOM and no network, so it is
 * unit-tested in Node. There is no language model and no API key anywhere: the assistant can only
 * return text that exists, word for word, in an approved FAQ entry. When it is not confident it says
 * so and records the question for the coordinator instead of guessing.
 *
 * Everything is synthetic prototype content, not official university policy.
 */
(function (root) {
  'use strict';

  const STORAGE_KEY = 'ipp-faq-v1';
  const UNKNOWN_REPLY = "I don't know yet. I've noted your question for the coordinator.";
  const EMPTY_REPLY = 'Please ask a question about internships, for example placements, grading, employer submissions, review or applying.';
  const PII_REPLY =
    "Please don't share personal information such as names, email addresses, phone numbers or ID numbers. That message was not sent or saved. Ask again without it.";
  const MIN_SCORE = 0.45; // below this the assistant refuses to answer (tuned in tests/faq.test.mjs)
  const AMBIGUITY_MARGIN = 0.03; // two different entries this close, with no clear winner, count as "not sure"
  const CONFIDENT_SCORE = 0.8; // a score this high wins even when another entry is close
  const UNANSWERED_LIMIT = 100;

  const LIMITS = Object.freeze({ section: 40, question: 150, answer: 500, ask: 300 });

  // ---------- parsing the approved FAQ file ----------

  /** Parses "Section: S | Q: Q | A: A" lines. Blank lines and # comments are skipped; malformed lines are reported. */
  function parseFaq(text) {
    const entries = [];
    const problems = [];
    String(text ?? '')
      .split(/\r?\n/)
      .forEach((line, index) => {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) return;
        const match = /^Section:\s*(.+?)\s*\|\s*Q:\s*(.+?)\s*\|\s*A:\s*(.+)$/.exec(trimmed);
        if (!match) {
          problems.push({ line: index + 1, text: trimmed.slice(0, 80) });
          return;
        }
        entries.push({
          id: `FAQ-${String(entries.length + 1).padStart(3, '0')}`,
          section: match[1],
          question: match[2],
          answer: match[3],
          origin: 'faq.txt',
          status: 'approved',
        });
      });
    return { entries, problems };
  }

  /** The inverse of parseFaq, for exporting an updated faq.txt (e.g. to upload as a Botpress Knowledge Base). */
  function serializeFaq(entries) {
    return entries.map((entry) => `Section: ${entry.section} | Q: ${entry.question} | A: ${entry.answer}`).join('\n') + '\n';
  }

  // ---------- turning a question into comparable tokens ----------

  // Function words and chat scaffolding only. Anything else a user types is evidence, and words the
  // FAQ has never seen count *against* a match, so wordy off-topic questions are not answered.
  const STOPWORDS = new Set(
    (
      'a an the is are am was were be been being do does did doing done i me my mine we our us you your yours it its to of in on at for ' +
      'and or but if so then than that this these those there with as by from can could would will shall may might please what whats who whom ' +
      'whose which when where why how have has had having about into onto upon get gets got getting just also very want wants wanna know ' +
      'wondering wonder curious question questions ask asking help hi hello hey thanks thank go goes going ' +
      'allowed allow permitted permit possible okay ok process procedure steps step another other different certain'
    ).split(/\s+/),
  );

  // Words that mean the same thing for this FAQ. The first word names the group. Deliberately absent:
  // anything about pay, visas, deadlines or other topics the FAQ does not cover.
  const GROUPS = [
    ['placement', 'placements', 'placed', 'intern', 'interns', 'interning', 'internship', 'internships', 'work', 'working'],
    ['opportunity', 'opportunities', 'listing', 'listings', 'posting', 'postings', 'vacancy', 'vacancies', 'position', 'positions', 'job', 'jobs', 'role', 'roles'],
    ['remote', 'remotely', 'online', 'virtual', 'virtually', 'wfh', 'home'],
    ['site', 'onsite', 'inperson', 'office', 'workplace'],
    ['abroad', 'overseas', 'international', 'internationally', 'foreign', 'country', 'countries'],
    ['grade', 'grades', 'grading', 'graded', 'mark', 'marks', 'marked', 'score', 'scores', 'gpa'],
    ['enter', 'enters', 'entered', 'give', 'gives', 'gave', 'given', 'assign', 'assigns', 'assigned', 'decide', 'decides', 'decided', 'award', 'awards', 'awarded', 'record', 'records', 'recorded', 'responsible'],
    ['faculty', 'professor', 'professors', 'lecturer', 'lecturers', 'teacher', 'teachers', 'instructor', 'instructors', 'academic'],
    ['employer', 'employers', 'company', 'companies', 'organization', 'organizations', 'organisation', 'organisations', 'host', 'hosts', 'business', 'businesses', 'firm', 'firms'],
    ['must', 'need', 'needs', 'needed', 'require', 'requires', 'required', 'requirement', 'requirements', 'should', 'necessary', 'mandatory'],
    ['include', 'includes', 'included', 'including', 'provide', 'provides', 'provided', 'put', 'contain', 'contains', 'attach', 'attaches', 'add', 'supply'],
    ['approve', 'approval', 'approved', 'approves', 'approving', 'accept', 'accepts', 'accepted', 'authorize', 'authorise', 'authorized', 'authorised'],
    ['review', 'reviews', 'reviewed', 'reviewing', 'check', 'checks', 'checked', 'checking', 'checklist', 'vet', 'vetted', 'assess', 'assessed', 'assessment'],
    ['return', 'returns', 'returned', 'returning', 'reject', 'rejects', 'rejected', 'rejecting', 'decline', 'declined', 'deny', 'denied', 'bounce', 'bounced'],
    ['resubmit', 'resubmits', 'resubmitted', 'resubmitting', 'resubmission', 'resend'],
    ['submit', 'submits', 'submitted', 'submitting', 'submission', 'submissions', 'upload', 'uploads'],
    ['apply', 'applies', 'applied', 'applying', 'application', 'applications', 'applicant', 'applicants'],
    ['mean', 'means', 'meant', 'guarantee', 'guarantees', 'guaranteed', 'imply', 'implies', 'implied', 'equal', 'equals', 'same'],
    ['version', 'versions', 'copy', 'copies', 'revision', 'revisions'],
    ['coordinator', 'coordinators'],
  ];

  function undouble(word) {
    return /([b-df-hj-np-tv-z])\1$/.test(word) && !/(ll|ss|zz)$/.test(word) ? word.slice(0, -1) : word;
  }

  /** A deliberately small stemmer: plurals, -ing, -ed, -ly and a trailing e. Synonym groups cover the rest. */
  function stem(word) {
    let w = word;
    if (w.length > 4 && w.endsWith('ies')) w = `${w.slice(0, -3)}y`;
    else if (w.length > 4 && w.endsWith('sses')) w = w.slice(0, -2);
    else if (w.length > 3 && w.endsWith('s') && !/(ss|us|is)$/.test(w)) w = w.slice(0, -1);
    if (w.length > 5 && w.endsWith('ing')) w = undouble(w.slice(0, -3));
    else if (w.length > 4 && w.endsWith('ed')) w = undouble(w.slice(0, -2));
    if (w.length > 5 && w.endsWith('ly')) w = w.slice(0, -2);
    if (w.length > 4 && w.endsWith('e')) w = w.slice(0, -1);
    return w;
  }

  const CANONICAL = new Map();
  for (const group of GROUPS) {
    const name = stem(group[0]);
    for (const word of group) CANONICAL.set(stem(word), name);
  }

  /** Content tokens of a piece of text: lower-cased, stop words removed, stemmed, synonyms merged. */
  function tokenize(text) {
    const words = String(text ?? '')
      .toLowerCase()
      .replace(/\bco[\s-]?op\b/g, 'coop') // "co-op", "co op" and "coop" are one word
      .replace(/['’]s\b/g, '')
      .replace(/[^a-z0-9]+/g, ' ')
      .split(' ')
      .filter(Boolean);
    const tokens = [];
    for (const word of words) {
      if (STOPWORDS.has(word)) continue;
      const stemmed = stem(word);
      tokens.push(CANONICAL.get(stemmed) || stemmed);
    }
    return tokens;
  }

  // ---------- matching ----------

  /** Precomputes token sets and inverse-document-frequency weights for a list of approved entries. */
  function buildIndex(entries) {
    const docs = entries.map((entry) => {
      const question = new Set(tokenize(entry.question));
      const answer = new Set([...tokenize(entry.answer)].filter((token) => !question.has(token)));
      const section = new Set([...tokenize(entry.section)].filter((token) => !question.has(token) && !answer.has(token)));
      return { entry, question, answer, section };
    });
    const documentFrequency = new Map();
    for (const doc of docs) {
      for (const token of new Set([...doc.question, ...doc.answer, ...doc.section])) {
        documentFrequency.set(token, (documentFrequency.get(token) || 0) + 1);
      }
    }
    const count = docs.length;
    const frequency = (token) => documentFrequency.get(token) || 0;
    // A word the FAQ has never seen is evidence the question is about something else (pay, visas,
    // deadlines, "on Fridays"...). It weighs double, so one stray word is enough to refuse.
    const unknownWeight = 2 * Math.log(1 + count / 0.5);
    const weight = (token) => (frequency(token) ? Math.log(1 + count / frequency(token)) : unknownWeight);
    return { docs, weight, frequency, vocabulary: new Set(documentFrequency.keys()) };
  }

  /** Edit distance <= 1 (insert, delete, substitute or swap), enough to forgive a typo. */
  function withinOneEdit(a, b) {
    if (a === b) return true;
    if (Math.abs(a.length - b.length) > 1) return false;
    let i = 0;
    while (i < a.length && i < b.length && a[i] === b[i]) i += 1;
    const restA = a.slice(i);
    const restB = b.slice(i);
    if (restA.length === restB.length) {
      return restA.slice(1) === restB.slice(1) || (restA.length > 1 && restA[0] === restB[1] && restA[1] === restB[0] && restA.slice(2) === restB.slice(2));
    }
    return restA.length > restB.length ? restA.slice(1) === restB : restB.slice(1) === restA;
  }

  /** Maps a word the FAQ has never seen onto a single near-identical FAQ word (typo repair), else leaves it alone. */
  function repairTypo(token, vocabulary) {
    if (vocabulary.has(token) || token.length < 5) return token;
    const candidates = [...vocabulary].filter((word) => word[0] === token[0] && word.length >= 5 && withinOneEdit(token, word));
    return candidates.length === 1 ? candidates[0] : token;
  }

  function scoreDoc(doc, queryTokens, index, total) {
    const { weight, frequency } = index;
    let matchedQuestion = 0;
    let matchedAnswer = 0;
    let matchedSection = 0;
    let distinctiveAnswerHit = false;
    for (const token of queryTokens) {
      if (doc.question.has(token)) matchedQuestion += weight(token);
      else if (doc.answer.has(token)) {
        // An answer-only word is strong evidence only if it points at this entry alone ("remote"
        // appears in one answer); a word that recurs across answers ("approved") proves little.
        const distinctive = frequency(token) === 1;
        matchedAnswer += (distinctive ? 0.75 : 0.5) * weight(token);
        if (distinctive) distinctiveAnswerHit = true;
      } else if (doc.section.has(token)) matchedSection += 0.35 * weight(token);
    }
    if (matchedQuestion === 0) return 0; // at least one word must overlap the FAQ question itself
    let questionWeight = 0;
    for (const token of doc.question) questionWeight += weight(token);
    const questionCoverage = questionWeight ? matchedQuestion / questionWeight : 0; // how much of the FAQ question was asked about
    // A single shared word is not enough ("Can I apply?" must not get "No."): the entry has to cover at
    // least half of the FAQ question, or be pinned down by a word that only its answer contains.
    if (questionCoverage < 0.5 && !distinctiveAnswerHit) return 0;
    const coverage = (matchedQuestion + matchedAnswer + matchedSection) / total; // how much of what was asked is explained
    return coverage * (0.5 + 0.5 * questionCoverage);
  }

  /**
   * Finds the approved entry that best explains a question.
   * Returns { kind: 'answer', entry, score } or { kind: 'unknown', score, entry|null } when not confident.
   */
  function matchQuestion(index, text) {
    const rawTokens = tokenize(text);
    if (rawTokens.length === 0) return { kind: 'empty', score: 0, entry: null };
    if (index.docs.length === 0) return { kind: 'unknown', score: 0, entry: null };
    const queryTokens = [...new Set(rawTokens.map((token) => repairTypo(token, index.vocabulary)))];
    const total = queryTokens.reduce((sum, token) => sum + index.weight(token), 0);
    const ranked = index.docs
      .map((doc) => ({ entry: doc.entry, score: scoreDoc(doc, queryTokens, index, total) }))
      .sort((a, b) => b.score - a.score);
    const [best, second] = ranked;
    const unclear = second && second.score > 0 && best.score - second.score < AMBIGUITY_MARGIN && best.score < CONFIDENT_SCORE;
    if (best.score >= MIN_SCORE && !unclear) return { kind: 'answer', entry: best.entry, score: best.score };
    return { kind: 'unknown', score: best.score, entry: best.score > 0 ? best.entry : null };
  }

  // ---------- privacy guard ----------

  const PII_PATTERNS = [
    ['email address', /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/],
    ['phone number', /(?:\+?\d[\s().-]?){9,}\d/],
    ['ID or long number', /\d{6,}/],
    ['student ID', /\b(?:coop-?[a-z]?\d{2,}|stu-?\d{2,})\b/i],
    ['self-introduction', /\b(?:my name is|my name's|i am called|i'm called|call me|my (?:e-?mail|phone|mobile|number|address|id|student id|passport|birthday))\b/i],
    ['sensitive identifier', /\b(?:passport|emirates id|national id|ssn|social security|credit card|date of birth|dob)\b/i],
  ];

  /** Returns the kinds of personal information a text appears to contain (an empty list means none found). */
  function detectPii(text) {
    const value = String(text ?? '');
    return PII_PATTERNS.filter(([, pattern]) => pattern.test(value)).map(([kind]) => kind);
  }

  // ---------- optional hosted-chatbot mode: which embed scripts may ever be loaded ----------

  // Only the hosts that serve a Botpress webchat embed. A script URL from anywhere else is refused,
  // and so is any URL that carries credentials or a secret-looking query parameter: embed URLs are
  // public, an API key or token is never one.
  const EMBED_HOSTS = Object.freeze(['cdn.botpress.cloud', 'files.bpcontent.cloud']);
  const SECRET_PARAMETER = /^(?:key|api[_-]?key|token|access[_-]?token|secret|auth|authorization|password|pwd)$/i;

  /** Validates data/chatbot-config.json. Returns { ok, scripts, reason }; a disabled or empty config is not an error. */
  function parseChatbotConfig(config) {
    const section = config && typeof config === 'object' ? config.botpress : null;
    if (!section || section.enabled !== true) return { ok: false, reason: 'disabled', scripts: [] };
    if (!Array.isArray(section.scripts) || section.scripts.length === 0 || section.scripts.length > 4) {
      return { ok: false, reason: 'scripts must list between 1 and 4 URLs', scripts: [] };
    }
    const scripts = [];
    for (const raw of section.scripts) {
      let url;
      try {
        url = new URL(String(raw));
      } catch (error) {
        return { ok: false, reason: 'a script entry is not a valid URL', scripts: [] };
      }
      if (url.protocol !== 'https:') return { ok: false, reason: 'script URLs must use https', scripts: [] };
      if (!EMBED_HOSTS.includes(url.hostname) || url.port) return { ok: false, reason: `script host not allowed: ${url.hostname}`, scripts: [] };
      if (url.username || url.password) return { ok: false, reason: 'script URLs must not contain credentials', scripts: [] };
      if ([...url.searchParams.keys()].some((name) => SECRET_PARAMETER.test(name))) return { ok: false, reason: 'script URLs must not contain keys or tokens', scripts: [] };
      scripts.push(url.href);
    }
    return { ok: true, scripts };
  }

  // ---------- state: coordinator-approved additions and unanswered questions ----------

  const questionKey = (text) => [...new Set(tokenize(text))].sort().join(' ');
  const collapse = (text) => String(text ?? '').replace(/\s+/g, ' ').trim();

  function createFaqStore(storage) {
    const listeners = new Set();
    let persistent = Boolean(storage);
    let base = [];
    let state = load();
    let indexCache = null;

    function emptyState() {
      return { version: 1, added: [], unanswered: [] };
    }

    function load() {
      if (storage) {
        try {
          const raw = storage.getItem(STORAGE_KEY);
          if (raw) {
            const parsed = JSON.parse(raw);
            if (parsed && parsed.version === 1 && Array.isArray(parsed.added) && Array.isArray(parsed.unanswered)) return parsed;
          }
        } catch (error) {
          /* unreadable data: start empty */
        }
      }
      return emptyState();
    }

    function save() {
      indexCache = null;
      if (storage) {
        try {
          storage.setItem(STORAGE_KEY, JSON.stringify(state));
          persistent = true;
        } catch (error) {
          persistent = false;
        }
      }
      for (const listener of listeners) listener();
    }

    const clone = (value) => JSON.parse(JSON.stringify(value));
    const nextId = (prefix, records) => {
      let max = 0;
      for (const record of records) {
        const found = /-(\d+)$/.exec(record.id);
        if (found) max = Math.max(max, Number(found[1]));
      }
      return `${prefix}-${String(max + 1).padStart(3, '0')}`;
    };
    const fail = (errors, message) => ({ ok: false, errors, message });

    function approved() {
      return [...base, ...state.added.filter((entry) => entry.status === 'approved')];
    }
    function pending() {
      return state.added.filter((entry) => entry.status === 'pending');
    }
    function index() {
      if (!indexCache) indexCache = buildIndex(approved());
      return indexCache;
    }

    function setBase(entries) {
      base = entries.map((entry) => ({ ...entry }));
      indexCache = null;
      for (const listener of listeners) listener();
    }

    /** Answer a user's question from approved entries only, or record it as unanswered. Never invents text. */
    function ask(text) {
      const raw = collapse(text).slice(0, LIMITS.ask * 4);
      if (!raw) return { kind: 'empty', reply: EMPTY_REPLY };
      const pii = detectPii(raw);
      if (pii.length > 0) return { kind: 'pii', kinds: pii, reply: PII_REPLY };
      const question = raw.slice(0, LIMITS.ask);
      const result = matchQuestion(index(), question);
      if (result.kind === 'empty') return { kind: 'empty', reply: EMPTY_REPLY };
      if (result.kind === 'answer') {
        const { entry } = result;
        return {
          kind: 'answer',
          reply: entry.answer,
          score: result.score,
          source: { id: entry.id, section: entry.section, question: entry.question, origin: entry.origin },
        };
      }
      const key = questionKey(question);
      const now = new Date().toISOString();
      const existing = state.unanswered.find((item) => item.status === 'open' && item.key === key);
      if (existing) {
        existing.count += 1;
        existing.last_asked_at = now;
      } else {
        state.unanswered.push({ id: nextId('Q', state.unanswered), question, key, count: 1, first_asked_at: now, last_asked_at: now, status: 'open' });
        if (state.unanswered.length > UNANSWERED_LIMIT) state.unanswered.splice(0, state.unanswered.length - UNANSWERED_LIMIT);
      }
      save();
      return { kind: 'unknown', reply: UNKNOWN_REPLY, score: result.score, recorded: true };
    }

    /** Draft a new FAQ entry. It stays pending (and unused by the assistant) until the coordinator approves it. */
    function addEntry(input) {
      const values = { section: collapse(input.section), question: collapse(input.question), answer: collapse(input.answer) };
      const labels = { section: 'Section', question: 'Question', answer: 'Answer' };
      const errors = {};
      for (const field of ['section', 'question', 'answer']) {
        if (!values[field]) errors[field] = `${labels[field]} is required.`;
        else if (values[field].length > LIMITS[field]) errors[field] = `${labels[field]} must be ${LIMITS[field]} characters or fewer.`;
        else if (values[field].includes('|')) errors[field] = `${labels[field]} cannot contain the | character (it separates fields in faq.txt).`;
        else if (detectPii(values[field]).length > 0) errors[field] = `${labels[field]} looks like it contains personal information. Remove it.`;
      }
      if (!errors.question) {
        const key = questionKey(values.question);
        const duplicate = key && [...approved(), ...pending()].find((entry) => questionKey(entry.question) === key);
        if (duplicate) errors.question = `A question like this already exists (${duplicate.id}).`;
      }
      if (Object.keys(errors).length > 0) return fail(errors, 'Fix the highlighted fields and try again.');
      const entry = {
        id: nextId('ADD', state.added),
        ...values,
        origin: 'coordinator',
        status: 'pending',
        created_at: new Date().toISOString(),
      };
      state.added.push(entry);
      save();
      return { ok: true, entry: clone(entry) };
    }

    /** Coordinator approval: the entry joins the approved FAQ, and any open unanswered questions it now covers are closed. */
    function approve(id) {
      const entry = state.added.find((item) => item.id === id);
      if (!entry) return { ok: false, message: `${id} does not exist.` };
      if (entry.status === 'approved') return { ok: false, message: `${id} is already approved.` };
      entry.status = 'approved';
      entry.approved_at = new Date().toISOString();
      indexCache = null;
      let resolved = 0;
      for (const item of state.unanswered) {
        if (item.status !== 'open') continue;
        const result = matchQuestion(index(), item.question);
        if (result.kind === 'answer' && result.entry.id === entry.id) {
          item.status = 'answered';
          item.answered_by = entry.id;
          resolved += 1;
        }
      }
      save();
      return { ok: true, entry: clone(entry), resolved };
    }

    function discard(id) {
      const position = state.added.findIndex((item) => item.id === id && item.status === 'pending');
      if (position < 0) return { ok: false, message: `${id} is not a pending entry.` };
      const [removed] = state.added.splice(position, 1);
      save();
      return { ok: true, entry: clone(removed) };
    }

    function dismissUnanswered(id) {
      const item = state.unanswered.find((candidate) => candidate.id === id && candidate.status === 'open');
      if (!item) return { ok: false, message: `${id} is not an open question.` };
      item.status = 'dismissed';
      save();
      return { ok: true };
    }

    function reset() {
      state = emptyState();
      save();
    }

    function refresh() {
      state = load();
      indexCache = null;
      for (const listener of listeners) listener();
    }

    return {
      subscribe(listener) {
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
      isPersistent: () => persistent,
      setBase,
      isLoaded: () => base.length > 0,
      refresh,
      reset,
      ask,
      addEntry,
      approve,
      discard,
      dismissUnanswered,
      approved: () => clone(approved()),
      pending: () => clone(pending()),
      openUnanswered: () =>
        clone(state.unanswered.filter((item) => item.status === 'open').sort((a, b) => (a.last_asked_at < b.last_asked_at ? 1 : -1))),
      counts: () => ({ unanswered: state.unanswered.filter((item) => item.status === 'open').length, pending: pending().length }),
      sections: () => [...new Set([...approved(), ...pending()].map((entry) => entry.section))],
      exportText: () => serializeFaq(approved()),
    };
  }

  root.IPPFaq = Object.freeze({
    STORAGE_KEY,
    UNKNOWN_REPLY,
    EMPTY_REPLY,
    PII_REPLY,
    MIN_SCORE,
    LIMITS,
    SYNONYM_GROUPS: GROUPS,
    parseFaq,
    serializeFaq,
    tokenize,
    buildIndex,
    matchQuestion,
    detectPii,
    parseChatbotConfig,
    EMBED_HOSTS,
    createFaqStore,
  });
})(globalThis);
