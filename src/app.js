/*
 * IPP demo UI: an overview page plus four simulated role views over one shared, browser-local store.
 * Every user-supplied string is rendered as a text node (never as HTML).
 *
 * Render model: every user action runs inside act(), which pauses the store's change notification,
 * so the handler can finish updating UI state and then render exactly once. Changes from another
 * browser tab arrive through the store subscription and render normally.
 */
(function () {
  'use strict';

  const Store = window.IPPStore;
  const Faq = window.IPPFaq;
  const { h, icon, orgTile, avatar, timeEl, refreshRelativeTimes } = window.IPPUI;
  let store;
  let faq; // internship assistant: approved FAQ, unanswered questions, coordinator approvals
  const { OPPORTUNITY_STATUS, PLACEMENT_STATUS, WORK_MODES, LIMITS } = Store;

  const DEFAULT_ROUTE = 'overview'; // set to 'student' to open on the Student view instead

  const OVERVIEW = { id: 'overview', label: 'Overview', short: 'Overview', hint: 'Journey and live activity', icon: 'home' };
  // Ordered by the end-to-end journey.
  const ROLES = [
    { id: 'employer', label: 'Employer HR', short: 'Employer', hint: '1 · Submit, view applicants', icon: 'briefcase' },
    { id: 'admin', label: 'University Administrator', short: 'Admin', hint: '2 · Review and approve', icon: 'shield' },
    { id: 'student', label: 'Student', short: 'Student', hint: '3 · Browse and apply', icon: 'cap' },
    { id: 'faculty', label: 'Faculty Reviewer', short: 'Faculty', hint: '4 · P07 placeholder', icon: 'book' },
  ];
  const ASSISTANT = { id: 'assistant', label: 'Internship Assistant', short: 'Assistant', hint: 'FAQ prototype · P01–P03', icon: 'chat' };
  // Parts owned by other teams are labelled so nobody mistakes a placeholder for the real thing.
  const P04_LABEL = 'P04 placeholder: applications are owned by P04/P05';
  const P07_LABEL = 'P07 placeholder';
  const FAQ_LABEL = 'FAQ prototype by P01–P03. Official chatbot: P06';
  const ROUTES = [OVERVIEW, ...ROLES, ASSISTANT];
  const ACTIVITY_ICON = { employer: 'briefcase', admin: 'shield', student: 'cap', faculty: 'book', system: 'reset' };
  const STUDENT_TABS = [
    { id: 'opportunities', label: 'Opportunities', icon: 'search' },
    { id: 'applications', label: 'My applications', icon: 'inbox' },
    { id: 'profile', label: 'My profile', icon: 'user' },
  ];
  const EMPLOYER_TABS = [
    { id: 'submit', label: 'Opportunities', icon: 'briefcase' },
    { id: 'applicants', label: 'Applicants', icon: 'inbox' },
  ];
  const ADMIN_TABS = [
    { id: 'review', label: 'Opportunities', icon: 'inbox' },
    { id: 'faq', label: 'Assistant FAQ', icon: 'chat' },
  ];
  const ROLE_TABS = { student: STUDENT_TABS, employer: EMPLOYER_TABS, admin: ADMIN_TABS };

  // Fictional organizations, used by "Fill sample data" so repeated demos do not repeat one listing.
  const SAMPLE_DRAFTS = [
    {
      organization_name: 'Harbor Robotics',
      title: 'Controls Engineering Intern',
      description: 'Help test motion-control firmware on a lab rig and document the results for the engineering team.',
      location: 'Abu Dhabi',
      work_mode: 'On-site',
      duration: '8 weeks',
    },
    {
      organization_name: 'Atlas Health Labs',
      title: 'UX Research Intern',
      description: 'Plan and run usability sessions for a patient-scheduling tool and present findings to the product team.',
      location: 'Remote',
      work_mode: 'Remote',
      duration: '10 weeks',
    },
    {
      organization_name: 'Cedar Ledger Partners',
      title: 'Risk Analytics Intern',
      description: 'Build dashboards that track portfolio risk indicators and explain trends to non-technical colleagues.',
      location: 'Dubai',
      work_mode: 'Hybrid',
      duration: '12 weeks',
    },
  ];
  const blankDraft = () => ({
    organization_name: '',
    title: '',
    description: '',
    location: '',
    work_mode: 'Hybrid',
    duration: '',
  });

  const ui = {
    route: null,
    studentId: null,
    tab: 'opportunities',
    query: '',
    workMode: 'All',
    sort: 'newest',
    hrAuthorized: true,
    draft: blankDraft(),
    errors: {},
    formMessage: '',
    sampleIndex: 0,
    nameDraft: null,
    nameError: '',
    focusId: null, // element to focus after the next render
    dialogFocusId: null, // element to focus once a dialog has closed
    pendingApply: null,
    pendingReview: null, // { id, decision } while the reason dialog is open
    resubmitOf: null, // opportunity ID being revised and resubmitted
    fresh: new Set(), // record IDs to highlight once, on the next render
    seenActivity: new Set(),
    activityPrimed: false, // false until the first render, so existing entries do not all flash
    prevStats: {},
    enter: false, // true on route changes: play the entrance animation
    batch: false,
    chat: null, // assistant conversation: kept in memory only, never saved
    bot: { status: 'idle', scripts: [] }, // optional Botpress mode
    faqLoading: false,
    faqError: '',
    faqDraft: { section: '', question: '', answer: '' },
    faqErrors: {},
    faqMessage: '',
  };

  const $ = (selector) => document.querySelector(selector);

  /** Run a store action without letting its change notification trigger an early render. */
  function act(fn) {
    ui.batch = true;
    try {
      return fn();
    } finally {
      ui.batch = false;
    }
  }

  // ---------- shared building blocks ----------

  function chip(text, kind, iconName) {
    return h('span', { class: `chip chip-${kind}` }, iconName && icon(iconName, 13), text);
  }
  const placeholderTag = (text) => h('span', { class: 'placeholder-tag' }, icon('info', 13), text);
  const approvalChip = (status) =>
    status === OPPORTUNITY_STATUS.APPROVED
      ? chip(status, 'approved', 'check')
      : status === 'Closed'
        ? chip(status, 'neutral', 'lock')
        : status === OPPORTUNITY_STATUS.RETURNED
          ? chip(status, 'pending', 'reset')
          : status === OPPORTUNITY_STATUS.DECLINED
            ? chip(status, 'declined', 'x')
            : chip(status, 'pending', 'clock');

  function listingLabel(opportunity) {
    if (opportunity.publication_status !== 'published') {
      if (opportunity.review_status === 'returned') return OPPORTUNITY_STATUS.RETURNED;
      if (opportunity.review_status === 'declined') return OPPORTUNITY_STATUS.DECLINED;
      return OPPORTUNITY_STATUS.PENDING;
    }
    return opportunity.listing_status === 'open' ? OPPORTUNITY_STATUS.APPROVED : 'Closed';
  }

  function skillNames(ids) {
    const vocabulary = store.getSkillsVocabulary();
    return (ids || []).map((id) => vocabulary.find((skill) => skill.skill_id === id)?.label || id).join(', ') || 'Not specified';
  }

  function listingDetails(opportunity) {
    return facts([
      ['Dates', opportunity.start_date && opportunity.end_date ? `${opportunity.start_date} – ${opportunity.end_date}` : 'Not specified'],
      ['Required skills', skillNames(opportunity.required_skills)],
      ['Desirable skills', skillNames(opportunity.desirable_skills)],
    ]);
  }

  function metaChips(opportunity) {
    return h(
      'ul',
      { class: 'meta' },
      [
        ['pin', opportunity.location],
        ['monitor', opportunity.work_mode],
        ['clock', opportunity.duration],
      ].filter(([, text]) => text).map(([iconName, text]) => h('li', null, icon(iconName, 14), text)),
    );
  }

  function facts(pairs) {
    return h('dl', { class: 'facts' }, pairs.map(([label, value]) => h('div', null, h('dt', null, label), h('dd', null, value))));
  }

  function formatTime(iso) {
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? iso : date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  }

  function emptyState(iconName, title, text, action, compact) {
    return h(
      'div',
      { class: `empty${compact ? ' compact' : ''}` },
      h('span', { class: 'empty-icon' }, icon(iconName, 24)),
      h('p', { class: 'empty-title' }, title),
      text && h('p', null, text),
      action,
    );
  }

  function hero(eyebrow, title, text, options) {
    const opts = options || {};
    return h(
      'section',
      { class: `hero${opts.large ? ' hero-lg' : ''}` },
      opts.icon && h('div', { class: 'hero-icon' }, icon(opts.icon, 110)),
      h('p', { class: 'eyebrow' }, eyebrow),
      h('h1', { id: 'page-title', tabindex: '-1' }, title),
      h('p', null, text),
      opts.extra,
    );
  }

  /** Stat tiles. The value is always the final number; a change plays a short "bump" animation. */
  function stats(items, variant) {
    return h(
      'div',
      { class: `stats${variant ? ` ${variant}` : ''}` },
      items.map((item) => {
        const previous = ui.prevStats[item.key];
        const changed = previous !== undefined && previous !== item.value;
        ui.prevStats[item.key] = item.value;
        return h(
          'div',
          { class: 'stat' },
          h('p', { class: 'stat-label' }, item.icon && icon(item.icon, 16), item.label),
          h('p', { class: `stat-value${item.text ? ' text' : ''}` }, h('span', { class: changed ? 'bump' : null }, item.value)),
          h('p', { class: 'stat-note' }, item.note),
        );
      }),
    );
  }

  function field(spec) {
    const { id, name, label, value, error, hint, required, multiline, options, maxlength, counter, list, datalist } = spec;
    const describedBy = [error ? `${id}-error` : null, hint ? `${id}-hint` : null].filter(Boolean).join(' ');
    const common = {
      id,
      name,
      'aria-required': required ? 'true' : null,
      'aria-invalid': error ? 'true' : null,
      'aria-describedby': describedBy || null,
    };
    let control;
    if (options) {
      control = h('select', common, options.map((option) => h('option', { value: option, selected: option === value }, option)));
    } else if (multiline) {
      control = h('textarea', { ...common, rows: '4', maxlength }, value || '');
    } else {
      control = h('input', { ...common, type: 'text', value: value || '', maxlength, autocomplete: 'off', list: list || null });
    }
    return h(
      'div',
      { class: `field${error ? ' has-error' : ''}` },
      h(
        'div',
        { class: 'field-label' },
        h('label', { for: id }, label, required && h('span', { class: 'req', 'aria-hidden': 'true' }, ' *')),
        counter && h('span', { class: 'counter', id: `${id}-count`, 'aria-hidden': 'true' }, `${(value || '').length} / ${maxlength}`),
      ),
      control,
      datalist && h('datalist', { id: list }, datalist.map((item) => h('option', { value: item }))),
      hint && h('p', { id: `${id}-hint`, class: 'hint' }, hint),
      error && h('p', { id: `${id}-error`, class: 'error' }, error),
    );
  }

  // ---------- toast (persistent live region) ----------

  function showToast(message, options) {
    const opts = options || {};
    $('#toast').replaceChildren(
      h(
        'div',
        { class: `toast-card${opts.error ? ' is-error' : ''}` },
        h('span', { class: 'toast-icon' }, icon(opts.error ? 'alert' : 'checkCircle', 18)),
        h('div', null, h('p', null, message), opts.link && h('a', { href: opts.link.href }, opts.link.text, icon('arrow', 14))),
        h('button', { type: 'button', class: 'toast-close', 'aria-label': 'Dismiss notification', onClick: clearToast }, icon('x', 16)),
      ),
    );
  }
  function clearToast() {
    $('#toast').replaceChildren();
  }

  // ---------- journey tracker and activity feed ----------

  function journeyCard(wide) {
    const journey = store.getJourney();
    const nextIndex = journey.stages.findIndex((stage) => !stage.done);
    const steps = journey.stages.map((stage, index) => {
      const state = stage.done ? 'is-done' : index === nextIndex ? 'is-current' : '';
      return h(
        'li',
        { class: `step ${state}` },
        h(
          'a',
          { href: `#${stage.role}`, 'aria-current': index === nextIndex ? 'step' : null },
          h('span', { class: 'step-dot' }, stage.done ? icon('check', 15) : String(index + 1)),
          h(
            'span',
            { class: 'step-text' },
            h('span', { class: 'step-label' }, stage.label),
            h('span', { class: 'step-state' }, stage.done ? 'Done' : stage.blocked ? 'Action needed' : index === nextIndex ? 'Next step' : 'Waiting'),
          ),
        ),
      );
    });
    const visibleOpportunity = journey.opportunity && (ui.route !== 'student' || (journey.opportunity.publication_status === 'published' && journey.opportunity.listing_status === 'open'));
    const record = visibleOpportunity
      ? h('p', { class: 'journey-record' }, 'Tracking ', h('strong', null, journey.opportunity.opportunity_id), ` · ${journey.opportunity.title} at ${journey.opportunity.employer_name}`)
      : h('p', { class: 'journey-record' }, ui.route === 'student' ? 'No published and open tracked listing yet.' : 'No submitted record yet. Submit an opportunity as Employer HR to start the journey.');
    return h(
      'section',
      { class: `card journey${wide ? ' journey-h' : ''}`, 'aria-labelledby': 'journey-title' },
      h('div', { class: 'journey-head' }, h('h2', { class: 'card-title', id: 'journey-title' }, icon('layers', 18), 'Demo journey'), journey.complete && chip('Complete', 'approved', 'check')),
      record,
      h('ol', { class: 'steps' }, steps),
      h(
        'div',
        { class: 'journey-foot' },
        h('p', { class: 'journey-placement' }, 'Placement status', chip(journey.placement_status, 'neutral')),
        h('p', { class: 'muted' }, 'Decided separately from applying; placement decisions are deferred.'),
      ),
    );
  }

  function activityCard(limit) {
    let entries = store.listActivity();
    if (ui.route === 'student') {
      const visibleRefs = new Set([
        ...store.searchApproved('').map((listing) => listing.opportunity_id),
        ...store.listStudentApplications(ui.studentId).map((application) => application.application_id),
        ui.studentId,
      ]);
      entries = entries.filter((entry) => !entry.ref || visibleRefs.has(entry.ref));
    }
    entries = entries.slice(0, limit);
    const keyOf = (entry) => `${entry.activity_id}@${entry.at}`;
    const list = entries.length
      ? h(
          'ul',
          { class: 'activity-list' },
          entries.map((entry) =>
            h(
              'li',
              { class: `activity-item${ui.activityPrimed && !ui.seenActivity.has(keyOf(entry)) ? ' is-new' : ''}` },
              h('span', { class: `act-icon act-${entry.role}` }, icon(ACTIVITY_ICON[entry.role] || 'pulse', 16)),
              h('div', { class: 'act-text' }, entry.text, entry.ref ? ` (${entry.ref})` : '', h('span', { class: 'act-time' }, timeEl(entry.at))),
            ),
          ),
        )
      : emptyState('pulse', 'No activity yet', 'Actions in any role show up here as they happen.', null, true);
    entries.forEach((entry) => ui.seenActivity.add(keyOf(entry)));
    return h('section', { class: 'card', 'aria-labelledby': 'activity-title' }, h('h2', { class: 'card-title', id: 'activity-title' }, icon('pulse', 18), 'Recent activity'), list);
  }

  // ---------- Overview ----------

  function overviewView() {
    const counts = store.counts();
    const steps = [
      {
        role: ROLES[0],
        text: 'Submit an internship opportunity, then see who applies. It starts as Pending Review.',
        metric: `${counts.pending} pending · ${counts.applications} ${counts.applications === 1 ? 'applicant' : 'applicants'}`,
      },
      { role: ROLES[1], text: 'Review the queue and approve opportunities for students.', metric: `${counts.approved} approved` },
      { role: ROLES[2], text: 'Search approved opportunities and apply once to each.', metric: `${counts.applications} ${counts.applications === 1 ? 'application' : 'applications'}` },
      { role: ROLES[3], text: 'Inspect applications read-only. An application is not a placement.', metric: `${counts.applications} ${counts.applications === 1 ? 'record' : 'records'}` },
    ];
    const scope = (cls, iconName, title, items) =>
      h('section', { class: `card scope-card ${cls}` }, h('h3', null, icon(iconName, 18), title), h('ul', null, items.map((item) => h('li', null, item))));

    return h(
      'div',
      null,
      hero(
        'Internship Practicum Platform · Sprint 3 demo',
        'One placement journey, from opportunity to application',
        'Employers submit opportunities, the university approves them, students apply and faculty follow each application, all on one shared record.',
        {
          large: true,
          icon: 'layers',
          extra: h(
            'div',
            { class: 'hero-actions' },
            h('a', { class: 'btn btn-light', href: '#employer' }, 'Start the demo', icon('arrow', 16)),
            h('a', { class: 'btn btn-outline-light', href: '#student' }, 'Browse as a student'),
            h('a', { class: 'btn btn-outline-light', href: '#assistant' }, icon('chat', 16), 'Ask the Internship Assistant'),
          ),
        },
      ),
      stats(
        [
          { key: 'pending', label: 'Pending review', value: counts.pending, note: 'Waiting for the administrator', icon: 'clock' },
          { key: 'approved', label: 'Approved opportunities', value: counts.approved, note: 'Visible to students', icon: 'checkCircle' },
          { key: 'applications', label: 'Applications', value: counts.applications, note: 'Submitted by students', icon: 'send' },
          { key: 'placement', label: 'Placement status', value: PLACEMENT_STATUS, text: true, note: 'Decisions are deferred', icon: 'lock' },
        ],
        'four',
      ),
      h('div', { class: 'section-head' }, h('h2', null, 'How the journey works')),
      h(
        'div',
        { class: 'how-grid' },
        steps.map((step, index) =>
          h(
            'a',
            { class: 'how-card', href: `#${step.role.id}` },
            h('div', { class: 'how-top' }, h('span', { class: 'how-step' }, `Step ${index + 1}`), h('span', { class: 'how-icon' }, icon(step.role.icon, 20))),
            h('h3', null, step.role.label),
            h('p', null, step.text),
            h('span', { class: 'how-metric' }, step.metric, icon('arrow', 16)),
          ),
        ),
      ),
      h('div', { class: 'overview-cols' }, journeyCard(true), activityCard(8)),
      h('div', { class: 'section-head' }, h('h2', null, 'What is working, simulated or deferred')),
      h(
        'div',
        { class: 'scope-cards' },
        scope('scope-working', 'checkCircle', 'Working', [
          'Students and listings loaded from data/ipp_sample_data.json (shared P01–P03 data)',
          'Administrator review: approve, return for revision or decline, with a required reason',
          'Employer sees the status and reason, and resubmits a new version (old version kept)',
          'One shared record through all four roles, duplicate prevention, records persist in this browser',
        ]),
        scope('scope-simulated', 'info', 'Simulated', [
          'Role switching (no login)',
          'HR authorization checkbox',
          'Four selectable synthetic students and one faculty reviewer',
          'Placeholders for other teams: applications (P04/P05) and faculty review (P07)',
        ]),
        scope('scope-deferred', 'clock', 'Deferred', [
          'Real authentication and permissions',
          'Shared central storage',
          'Eligibility verification',
          'Faculty review outcomes and placement decisions',
        ]),
      ),
    );
  }

  // ---------- tabs (Student and Employer HR) ----------

  /** A tab bar for the current route; `counts` maps a tab ID to a number shown beside its label. */
  function tabBar(tabs, label, counts) {
    return h(
      'div',
      { class: 'tabs', role: 'tablist', 'aria-label': label },
      tabs.map((tab) =>
        h(
          'button',
          {
            type: 'button',
            role: 'tab',
            id: `tab-${tab.id}`,
            'aria-controls': `panel-${tab.id}`,
            'aria-selected': String(ui.tab === tab.id),
            tabindex: ui.tab === tab.id ? '0' : '-1',
            onClick: () => setTab(tab.id),
            onKeydown: onTabKeys,
          },
          icon(tab.icon, 16),
          tab.label,
          counts[tab.id] !== undefined && h('span', { class: 'tab-count' }, counts[tab.id]),
        ),
      ),
    );
  }

  function tabPanel(id, content) {
    return h('div', { role: 'tabpanel', id: `panel-${id}`, 'aria-labelledby': `tab-${id}`, hidden: ui.tab !== id }, content);
  }

  // ---------- Student view ----------

  function studentView() {
    const student = store.getStudent(ui.studentId);
    const counts = store.counts();
    const mine = store.listStudentApplications(ui.studentId);

    const tablist = tabBar(STUDENT_TABS, 'Student sections', { applications: mine.length });
    const panel = tabPanel;

    return h(
      'div',
      null,
      hero('Student view', `Welcome, ${student.display_name}`, 'Browse approved internships and apply. Applying expresses interest; it does not approve a placement.', { icon: 'cap' }),
      stats([
        { key: 'approved', label: 'Open opportunities', value: counts.approved, note: 'Approved by the university', icon: 'checkCircle' },
        { key: 'applications', label: 'My applications', value: mine.length, note: 'Submitted by you', icon: 'send' },
        { key: 'placement', label: 'Placement status', value: PLACEMENT_STATUS, text: true, note: 'Decided separately from applying', icon: 'lock' },
      ]),
      h('div', { class: 'field' },
        h('label', { for: 'demo-student' }, 'Synthetic student profile'),
        h('select', { id: 'demo-student', onChange: (event) => {
          ui.studentId = event.target.value;
          ui.nameDraft = null;
          ui.nameError = '';
          ui.query = '';
          ui.workMode = 'All';
          ui.focusId = 'demo-student';
          clearToast();
          render();
        } }, store.listStudents().map((profile) => h('option', {
          value: profile.student_id, selected: profile.student_id === ui.studentId,
        }, `${profile.display_name} · ${profile.student_id} · v${profile.profile_version}`))),
      ),
      tablist,
      panel('opportunities', opportunitiesPanel()),
      panel('applications', applicationsPanel(mine)),
      panel('profile', profilePanel(student)),
    );
  }

  function setTab(id, moveFocus) {
    ui.tab = id;
    if (needsFaq()) ensureFaq();
    document.querySelectorAll('#view [role="tab"]').forEach((button) => {
      const selected = button.id === `tab-${id}`;
      button.setAttribute('aria-selected', String(selected));
      button.tabIndex = selected ? 0 : -1;
      if (selected && moveFocus) button.focus();
    });
    document.querySelectorAll('#view [role="tabpanel"]').forEach((panelEl) => {
      panelEl.hidden = panelEl.id !== `panel-${id}`;
    });
    try {
      history.replaceState(null, '', `#${ui.route}/${id}`);
    } catch (error) {
      /* some embedders block history updates; the tab still works */
    }
  }

  function onTabKeys(event) {
    const ids = (ROLE_TABS[ui.route] || []).map((tab) => tab.id);
    const index = ids.indexOf(ui.tab);
    let next = null;
    if (event.key === 'ArrowRight') next = (index + 1) % ids.length;
    else if (event.key === 'ArrowLeft') next = (index - 1 + ids.length) % ids.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = ids.length - 1;
    if (next !== null) {
      event.preventDefault();
      setTab(ids[next], true);
    }
  }

  function opportunitiesPanel() {
    const search = h('input', {
      id: 'search',
      type: 'search',
      value: ui.query,
      placeholder: 'e.g. Analytics, Emirates',
      autocomplete: 'off',
      onInput: (event) => {
        ui.query = event.target.value;
        fillResults();
      },
    });
    const modes = ['All', ...WORK_MODES];
    return [
      h(
        'div',
        { class: 'filters' },
        h('div', { class: 'field search' }, h('label', { for: 'search' }, 'Search by title or organization'), h('div', { class: 'search-box' }, icon('search', 18), search)),
        h(
          'fieldset',
          null,
          h('legend', null, 'Work mode'),
          h(
            'div',
            { class: 'segmented' },
            modes.map((mode) =>
              h(
                'label',
                { class: 'seg' },
                h('input', {
                  type: 'radio',
                  name: 'workmode',
                  value: mode,
                  checked: ui.workMode === mode,
                  onChange: () => {
                    ui.workMode = mode;
                    fillResults();
                  },
                }),
                h('span', null, mode),
              ),
            ),
          ),
        ),
        h(
          'div',
          { class: 'field' },
          h('label', { for: 'sort' }, 'Sort by'),
          h(
            'select',
            {
              id: 'sort',
              onChange: (event) => {
                ui.sort = event.target.value;
                fillResults();
              },
            },
            [
              ['newest', 'Newest first'],
              ['title', 'Title A–Z'],
            ].map(([value, label]) => h('option', { value, selected: ui.sort === value }, label)),
          ),
        ),
      ),
      h('p', { id: 'result-count', class: 'muted', 'aria-live': 'polite' }),
      h('div', { id: 'results' }),
    ];
  }

  // Called after the panel is attached, and whenever a filter changes.
  function fillResults() {
    const results = $('#results');
    if (!results) return;
    const list = store.searchApproved(ui.query, { workMode: ui.workMode, sort: ui.sort });
    const query = ui.query.trim();
    const filtered = Boolean(query) || ui.workMode !== 'All';
    $('#result-count').textContent = `${list.length} approved ${list.length === 1 ? 'opportunity' : 'opportunities'}${
      query ? ` matching “${query}”` : ''
    }${ui.workMode !== 'All' ? ` · ${ui.workMode}` : ''}`;
    if (list.length === 0) {
      results.replaceChildren(
        emptyState(
          'search',
          'No matching opportunities',
          filtered
            ? `No approved opportunities match ${query ? `“${query}”` : 'these filters'}. Try a different title or organization, or clear the filters.`
            : 'No approved opportunities are available yet. They appear here after university review.',
          filtered &&
            h(
              'button',
              {
                type: 'button',
                class: 'btn btn-quiet',
                onClick: () => {
                  ui.query = '';
                  ui.workMode = 'All';
                  ui.focusId = 'search';
                  render();
                },
              },
              'Clear filters',
            ),
        ),
      );
      return;
    }
    results.replaceChildren(h('div', { class: 'grid-2' }, list.map(opportunityCard)));
  }

  function opportunityCard(opportunity) {
    const id = opportunity.opportunity_id;
    const applied = store.getApplicationFor(ui.studentId, id);
    const isDemo = opportunity.origin === 'demo';
    return h(
      'article',
      { class: `card opp${ui.fresh.has(id) ? ' is-new' : ''}`, 'aria-labelledby': `opp-title-${id}` },
      h(
        'div',
        { class: 'opp-head' },
        orgTile(opportunity.employer_name),
        h('div', { class: 'opp-head-text' }, h('p', { class: 'org' }, opportunity.employer_name), h('h3', { id: `opp-title-${id}` }, opportunity.title)),
        isDemo ? chip('New', 'new') : h('span', { class: 'idtag' }, id),
      ),
      h('p', { class: 'desc' }, opportunity.description || opportunity.sector),
      listingDetails(opportunity),
      metaChips(opportunity),
      h(
        'div',
        { class: 'opp-foot' },
        applied
          ? h('p', { class: 'applied', id: `applied-${id}`, tabindex: '-1' }, chip('Application submitted', 'submitted', 'check'), applied.application_id)
          : h(
              'div',
              { class: 'apply-group' },
              h(
                'button',
                { type: 'button', class: 'btn', title: P04_LABEL, onClick: (event) => openApplyDialog(opportunity, event.currentTarget) },
                icon('send', 16),
                'Apply',
                h('span', { class: 'sr-only' }, ` to ${opportunity.title} at ${opportunity.employer_name}`),
              ),
              placeholderTag(P04_LABEL),
            ),
        isDemo && h('span', { class: 'idtag' }, id),
      ),
    );
  }

  function applicationsPanel(mine) {
    if (mine.length === 0) {
      return emptyState(
        'inbox',
        'No applications yet',
        'Apply to an approved opportunity and it will be tracked here.',
        h('button', { type: 'button', class: 'btn', onClick: () => setTab('opportunities', true) }, 'Browse opportunities'),
      );
    }
    return [
      h('p', { class: 'notice' }, icon('info', 18), 'Application status and placement status are separate. Submitting an application does not approve a placement.'),
      h(
        'div',
        { class: 'grid-2' },
        mine
          .slice()
          .reverse()
          .map((application) =>
            h(
              'article',
              { class: `card${ui.fresh.has(application.opportunity_id) ? ' is-new' : ''}` },
              h(
                'div',
                { class: 'opp-head' },
                orgTile(application.opportunity.employer_name),
                h('div', { class: 'opp-head-text' }, h('h3', null, application.opportunity.title), h('p', { class: 'muted' }, application.opportunity.employer_name)),
                chip(application.application_status, 'submitted'),
              ),
              facts([
                ['Application ID', application.application_id],
                ['Opportunity ID', application.opportunity_id],
                ['Application status', application.application_status],
                ['Placement status', chip(application.placement_status, 'neutral')],
                ['Submitted', formatTime(application.submitted_at)],
              ]),
              h(
                'ol',
                { class: 'lifecycle', 'aria-label': 'Application progress' },
                h('li', { class: 'life-step is-done' }, h('strong', null, 'Submitted'), timeEl(application.submitted_at)),
                h('li', { class: 'life-step' }, h('strong', null, 'Faculty review'), application.review ? application.review.review_status : 'Not started'),
                h('li', { class: 'life-step' }, h('strong', null, 'Placement'), application.placement_status),
              ),
            ),
          ),
      ),
    ];
  }

  function profilePanel(student) {
    const value = ui.nameDraft !== null ? ui.nameDraft : student.display_name;
    return h(
      'form',
      { class: 'card form', novalidate: true, onSubmit: onProfileSubmit },
      h(
        'div',
        { class: 'profile-head' },
        avatar(student.display_name, 'lg'),
        h('div', null, h('h2', null, 'My demo profile'), h('p', { class: 'muted' }, `${student.student_id} · Student`)),
      ),
      field({
        id: 'profile-display-name',
        name: 'display_name',
        label: 'Display name',
        value,
        error: ui.nameError,
        required: true,
        maxlength: LIMITS.display_name,
      }),
      facts([
        ['Student ID', student.student_id],
        ['Profile version', String(student.profile_version)],
        ['Profile status', student.profile_status],
        ['Interests', student.interests.length ? student.interests.join(', ') : 'Missing: interests not provided'],
        ['Availability', student.availability_start && student.availability_end ? `${student.availability_start} – ${student.availability_end}` : 'Missing: availability unknown'],
        ['Skills', student.skills.map((skill) => `${skillNames([skill.skill_id])} (${skill.evidence_status})`).join(', ') || 'Not provided'],
      ]),
      h('p', { class: 'note' }, 'Eligibility and official approval require human review. Missing interests or availability are not inferred. Saving a correction creates a new submitted profile version.'),
      h('div', { class: 'form-actions' }, h('button', { type: 'submit', class: 'btn' }, 'Save new profile version')),
    );
  }

  function onProfileSubmit(event) {
    event.preventDefault();
    const value = new FormData(event.currentTarget).get('display_name');
    const result = act(() => store.updateDisplayName(ui.studentId, value));
    ui.focusId = 'profile-display-name';
    if (!result.ok) {
      ui.nameDraft = String(value);
      ui.nameError = result.errors ? result.errors.display_name : result.message;
      render();
      return;
    }
    ui.nameDraft = null;
    ui.nameError = '';
    showToast(`Display name saved as “${result.student.display_name}”.`);
    render();
  }

  // ---------- apply dialog ----------

  function openApplyDialog(opportunity) {
    ui.pendingApply = opportunity.opportunity_id;
    const student = store.getStudent(ui.studentId);
    $('#apply-facts').replaceChildren(
      ...[
        ['Opportunity', `${opportunity.title} (${opportunity.opportunity_id})`],
        ['Organization', opportunity.employer_name],
        ['Applicant', `${student.display_name} (${student.student_id})`],
      ].map(([label, value]) => h('div', null, h('dt', null, label), h('dd', null, value))),
    );
    const error = $('#apply-error');
    error.hidden = true;
    error.textContent = '';
    $('#apply-dialog').showModal();
  }

  function confirmApply() {
    const opportunityId = ui.pendingApply;
    const result = act(() => store.submitApplication(ui.studentId, opportunityId));
    if (!result.ok) {
      const error = $('#apply-error');
      error.textContent = result.message;
      error.hidden = false;
      render();
      return;
    }
    ui.pendingApply = null;
    ui.dialogFocusId = `applied-${opportunityId}`;
    ui.fresh = new Set([opportunityId, result.application.application_id]);
    $('#apply-dialog').close();
    const opportunity = store.searchApproved('').find((item) => item.opportunity_id === opportunityId);
    showToast(
      `${result.application.application_id} submitted for ${opportunity.title} at ${opportunity.employer_name}. Application status: Submitted. Placement status: ${PLACEMENT_STATUS}. Employer HR and Faculty Reviewer can now view it.`,
      { link: { href: '#employer/applicants', text: 'Next: see it as Employer HR' } },
    );
    render();
  }

  // ---------- Employer HR view ----------

  function previewCard() {
    const draft = ui.draft;
    const org = draft.organization_name.trim();
    const title = draft.title.trim();
    const description = draft.description.trim();
    return h(
      'article',
      { class: 'card opp preview', 'aria-label': 'Listing preview' },
      h(
        'div',
        { class: 'opp-head' },
        orgTile(org || '?'),
        h(
          'div',
          { class: 'opp-head-text' },
          h('p', { class: `org${org ? '' : ' placeholder'}` }, org || 'Organization name'),
          h('h3', { class: title ? null : 'placeholder' }, title || 'Opportunity title'),
        ),
      ),
      h('p', { class: `desc${description ? '' : ' placeholder'}` }, description || 'The description students will read appears here.'),
      metaChips({
        location: draft.location.trim() || 'Location',
        work_mode: draft.work_mode,
        duration: draft.duration.trim() || 'Duration',
      }),
      h('div', { class: 'opp-foot' }, chip('Pending Review', 'pending', 'clock'), h('span', { class: 'muted' }, 'Students see it after approval')),
    );
  }

  function employerView() {
    const opportunities = store.listOpportunities().reverse(); // newest first
    const received = store.listEmployerApplications();
    const applicantCounts = store.applicantCounts();
    const hasErrors = Object.keys(ui.errors).length > 0;

    const form = h(
      'form',
      { id: 'opp-form', class: 'card form form-card', novalidate: true, onSubmit: onEmployerSubmit, onInput: onEmployerInput },
      h('h2', { class: 'card-title' }, icon('briefcase', 18), 'Submit an opportunity'),
      ui.resubmitOf && resubmitBanner(),
      h(
        'div',
        { class: 'authz' },
        h(
          'label',
          { class: 'check' },
          h('input', { type: 'checkbox', id: 'hr-authorized', checked: ui.hrAuthorized, onChange: onAuthChange }),
          'Simulate an authorized HR representative',
        ),
        h('p', { class: 'hint' }, 'Demo-only control, not production access control. Real HR authorization is deferred. Untick it to see submission blocked.'),
      ),
      h('p', { class: 'hint' }, 'Fields marked * are required.'),
      (ui.formMessage || hasErrors) &&
        h('div', { id: 'opp-form-error', class: 'error-summary', role: 'alert', tabindex: '-1' }, ui.formMessage || 'Fix the highlighted fields and submit again.'),
      field({ id: 'opp-organization_name', name: 'organization_name', label: 'Organization name', value: ui.draft.organization_name, error: ui.errors.organization_name, required: true, maxlength: LIMITS.organization_name }),
      field({ id: 'opp-title', name: 'title', label: 'Opportunity title', value: ui.draft.title, error: ui.errors.title, required: true, maxlength: LIMITS.title }),
      field({ id: 'opp-description', name: 'description', label: 'Description', value: ui.draft.description, error: ui.errors.description, required: true, multiline: true, maxlength: LIMITS.description, counter: true }),
      h(
        'div',
        { class: 'two-col' },
        field({ id: 'opp-location', name: 'location', label: 'Location', value: ui.draft.location, error: ui.errors.location, required: true, maxlength: LIMITS.location }),
        field({ id: 'opp-work_mode', name: 'work_mode', label: 'Work mode', value: ui.draft.work_mode, options: WORK_MODES }),
      ),
      field({ id: 'opp-duration', name: 'duration', label: 'Duration (optional)', value: ui.draft.duration, error: ui.errors.duration, hint: 'For example: 12 weeks', maxlength: LIMITS.duration }),
      h('p', { id: 'authz-blocked', class: 'blocked', hidden: ui.hrAuthorized }, icon('lock', 16), 'Submission is blocked: the simulated HR authorization is unchecked.'),
      h(
        'div',
        { class: 'form-actions' },
        h('button', { type: 'submit', id: 'submit-opp', class: 'btn', disabled: !ui.hrAuthorized, 'aria-describedby': 'authz-blocked' }, icon('send', 16), ui.resubmitOf ? 'Resubmit for review' : 'Submit for review'),
        h('button', { type: 'button', class: 'btn btn-quiet', onClick: fillSample }, 'Fill sample data'),
      ),
    );

    const preview = h(
      'section',
      { class: 'stack preview-sec', 'aria-labelledby': 'preview-title' },
      h('div', { class: 'section-head' }, h('h2', { id: 'preview-title', class: 'card-title' }, icon('eye', 18), 'Live preview')),
      h('p', { class: 'muted' }, 'How students will see this listing once an administrator approves it. It updates as you type.'),
      h('div', { id: 'preview-slot' }, previewCard()),
    );

    const statusCard = h(
      'section',
      { class: 'card stack status-card', 'aria-labelledby': 'status-heading' },
      h('h2', { id: 'status-heading', class: 'card-title', tabindex: '-1' }, icon('pulse', 18), 'Opportunity status'),
      h('p', { class: 'muted' }, 'Status is read from the shared opportunity record, so the administrator’s decision shows up here.'),
      h(
        'ul',
        { class: 'status-list' },
        opportunities.map((opportunity) =>
          h(
            'li',
            { class: `status-row${ui.fresh.has(opportunity.opportunity_id) ? ' is-new' : ''}` },
            orgTile(opportunity.employer_name, 'sm'),
            h(
              'div',
              { class: 'body' },
              h('div', { class: 'row-head' }, h('p', { class: 'row-title' }, opportunity.title), approvalChip(listingLabel(opportunity))),
              h('p', { class: 'muted' }, `${opportunity.employer_name} · ${opportunity.opportunity_id}${opportunity.origin === 'demo' ? ' · submitted in this demo' : ''}${Number(opportunity.version) > 1 ? ` · version ${opportunity.version}` : ''}`),
              statusDetail(opportunity),
              applicantCounts[opportunity.opportunity_id] > 0 &&
                h(
                  'button',
                  { type: 'button', class: 'link-btn', onClick: () => setTab('applicants', true) },
                  `${applicantCounts[opportunity.opportunity_id]} ${applicantCounts[opportunity.opportunity_id] === 1 ? 'applicant' : 'applicants'} · View`,
                ),
            ),
          ),
        ),
      ),
    );

    return h(
      'div',
      null,
      hero('Employer HR view', 'Employer HR', 'Submit an internship opportunity for university review, then see who applies. New submissions start as Pending Review.', { icon: 'briefcase' }),
      tabBar(EMPLOYER_TABS, 'Employer sections', { applicants: received.length }),
      tabPanel('submit', h('div', { class: 'split' }, form, h('div', { class: 'side' }, preview, statusCard))),
      tabPanel('applicants', applicantsPanel(received)),
    );
  }

  /** Applications received by Employer HR: read-only, and never an implication of a placement. */
  function applicantsPanel(received) {
    const notice = h(
      'p',
      { class: 'notice' },
      icon('info', 18),
      'View only. An application is not a placement: shortlisting, interviews and offers are deferred. In this demo the simulated HR user sees applicants for every organization; per-employer access needs real accounts.',
    );
    if (received.length === 0) {
      return [
        notice,
        emptyState(
          'inbox',
          'No applications yet',
          'When a student applies to an approved opportunity, the applicant appears here.',
          h('a', { class: 'btn', href: '#student' }, 'Open the Student view', icon('arrow', 16)),
        ),
      ];
    }
    return [
      notice,
      h('div', { class: 'section-head' }, h('h2', { id: 'applicants-heading', tabindex: '-1' }, `Applications received (${received.length})`)),
      h(
        'div',
        { class: 'grid-2' },
        received.map((entry) =>
          h(
            'article',
            { class: `card${ui.fresh.has(entry.application.application_id) ? ' is-new' : ''}` },
            h(
              'div',
              { class: 'opp-head' },
              avatar(entry.student.display_name),
              h(
                'div',
                { class: 'opp-head-text' },
                h('h3', null, entry.student.display_name),
                h('p', { class: 'muted' }, `Applied to ${entry.opportunity.title} · ${entry.opportunity.employer_name}`),
              ),
              chip(entry.application.application_status, 'submitted'),
            ),
            facts([
              ['Application ID', entry.application.application_id],
              ['Student ID', entry.student.student_id],
              ['Opportunity ID', entry.opportunity.opportunity_id],
              ['Profile version', String(entry.student.profile_version)],
              ['Profile status', entry.student.profile_status],
              ['Application status', entry.application.application_status],
              ['Placement status', chip(entry.placement_status, 'neutral')],
              ['Submitted', h('span', null, formatTime(entry.application.submitted_at), ' (', timeEl(entry.application.submitted_at), ')')],
            ]),
          ),
        ),
      ),
    ];
  }

  function onEmployerInput(event) {
    const name = event.target.name;
    if (!name || !(name in ui.draft)) return;
    ui.draft[name] = event.target.value;
    const slot = $('#preview-slot');
    if (slot) slot.replaceChildren(previewCard());
    if (name === 'description') {
      const counter = $('#opp-description-count');
      if (counter) counter.textContent = `${event.target.value.length} / ${LIMITS.description}`;
    }
  }

  function onAuthChange(event) {
    ui.hrAuthorized = event.target.checked;
    $('#submit-opp').disabled = !ui.hrAuthorized;
    $('#authz-blocked').hidden = ui.hrAuthorized;
  }

  function fillSample() {
    ui.draft = { ...SAMPLE_DRAFTS[ui.sampleIndex % SAMPLE_DRAFTS.length] };
    ui.sampleIndex += 1;
    ui.errors = {};
    ui.formMessage = '';
    ui.focusId = ui.hrAuthorized ? 'submit-opp' : 'hr-authorized';
    render();
  }

  /** What the employer sees under a listing: its status, the reason for a return or decline, and earlier versions. */
  function statusDetail(opportunity) {
    const label = listingLabel(opportunity);
    const versions = store.listVersions(opportunity.opportunity_id);
    const history = versions.length
      ? h(
          'div',
          { class: 'version-history' },
          h('p', { class: 'muted' }, 'Earlier versions (kept):'),
          h(
            'ul',
            null,
            versions.map((version) =>
              h(
                'li',
                { class: 'muted' },
                `Version ${version.version}: ${version.review_status === 'returned' ? 'Returned for revision' : version.review_status === 'declined' ? 'Declined' : 'Submitted'}${version.review_reason ? ` · Reason: ${version.review_reason}` : ''}`,
              ),
            ),
          ),
        )
      : null;
    if (label === OPPORTUNITY_STATUS.RETURNED) {
      return [
        h('p', { class: 'reason' }, h('strong', null, 'Returned for revision. '), 'Reason: ', opportunity.review_reason),
        h(
          'button',
          { type: 'button', class: 'btn btn-sm', onClick: () => startResubmit(opportunity) },
          icon('reset', 16),
          'Revise and resubmit',
          h('span', { class: 'sr-only' }, ` ${opportunity.title} (${opportunity.opportunity_id})`),
        ),
        history,
      ];
    }
    if (label === OPPORTUNITY_STATUS.DECLINED) {
      return [h('p', { class: 'reason' }, h('strong', null, 'Declined. '), 'Reason: ', opportunity.review_reason, ' This decision is final; submit a new listing if needed.'), history];
    }
    return [
      h(
        'p',
        { class: 'muted' },
        label === OPPORTUNITY_STATUS.PENDING
          ? 'Waiting for university approval. Students cannot see it yet.'
          : opportunity.listing_status === 'open' ? 'Published and open. Visible to students.' : 'Closed. Not visible to students.',
      ),
      history,
    ];
  }

  function resubmitBanner() {
    const current = store.listOpportunities().find((item) => item.opportunity_id === ui.resubmitOf);
    if (!current) return null;
    return h(
      'div',
      { id: 'resubmit-banner', class: 'notice', role: 'status' },
      icon('info', 18),
      h('span', null, `Resubmitting ${current.opportunity_id} (version ${current.version}) as version ${Number(current.version) + 1}. The previous version is kept. `, h('button', { type: 'button', class: 'link-btn', onClick: cancelResubmit }, 'Cancel resubmission')),
    );
  }

  function startResubmit(opportunity) {
    const mode = WORK_MODES.find((item) => item.toLowerCase() === String(opportunity.work_mode).toLowerCase()) || 'Hybrid';
    ui.draft = {
      organization_name: opportunity.employer_name,
      title: opportunity.title,
      description: opportunity.description || opportunity.sector || '',
      location: opportunity.location || '',
      work_mode: mode,
      duration: !opportunity.duration || opportunity.duration === 'Not specified' ? '' : opportunity.duration,
    };
    ui.resubmitOf = opportunity.opportunity_id;
    ui.errors = {};
    ui.formMessage = '';
    ui.focusId = 'opp-description';
    render();
  }

  function cancelResubmit() {
    ui.resubmitOf = null;
    ui.draft = blankDraft();
    ui.errors = {};
    ui.formMessage = '';
    render();
  }

  function onEmployerSubmit(event) {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    ui.draft = { ...blankDraft(), ...data };
    const result = act(() => (ui.resubmitOf ? store.resubmitOpportunity(ui.resubmitOf, data, { hrAuthorized: ui.hrAuthorized }) : store.submitOpportunity(data, { hrAuthorized: ui.hrAuthorized })));
    if (!result.ok) {
      ui.errors = result.errors || {};
      ui.formMessage = result.message;
      const firstInvalid = ['organization_name', 'title', 'description', 'location', 'duration'].find((name) => ui.errors[name]);
      ui.focusId = firstInvalid ? `opp-${firstInvalid}` : 'opp-form-error';
      render();
      return;
    }
    const created = result.opportunity;
    const resubmitted = Boolean(ui.resubmitOf);
    ui.resubmitOf = null;
    ui.draft = blankDraft();
    ui.errors = {};
    ui.formMessage = '';
    ui.focusId = 'status-heading';
    ui.fresh = new Set([created.opportunity_id]);
    showToast(resubmitted ? `${created.opportunity_id} “${created.title}” resubmitted as version ${created.version}. The previous version is kept. Status: ${listingLabel(created)}.` : `${created.opportunity_id} “${created.title}” submitted. Status: ${listingLabel(created)}.`, {
      link: { href: '#admin', text: 'Next: review it as University Administrator' },
    });
    render();
  }

  // ---------- University Administrator view ----------

  function adminView() {
    const pending = store.listOpportunities({ status: OPPORTUNITY_STATUS.PENDING });
    const approved = store.listOpportunities({ status: OPPORTUNITY_STATUS.APPROVED });
    const reviewed = [...store.listOpportunities({ status: OPPORTUNITY_STATUS.RETURNED }), ...store.listOpportunities({ status: OPPORTUNITY_STATUS.DECLINED })];

    const head = (opportunity) =>
      h(
        'div',
        { class: 'opp-head' },
        orgTile(opportunity.employer_name),
        h('div', { class: 'opp-head-text' }, h('p', { class: 'org' }, opportunity.employer_name), h('h3', null, opportunity.title)),
        h('span', { class: 'idtag' }, opportunity.opportunity_id),
      );

    const queue = pending.length
      ? h(
          'div',
          { class: 'grid-2' },
          pending.map((opportunity) =>
            h(
              'article',
              { class: 'card opp' },
              head(opportunity),
              h('p', { class: 'desc' }, opportunity.description || opportunity.sector),
              metaChips(opportunity),
              h(
                'div',
                { class: 'opp-foot' },
                approvalChip(listingLabel(opportunity)),
                h(
                  'div',
                  { class: 'row-actions' },
                  h(
                    'button',
                    { type: 'button', class: 'btn btn-sm', onClick: () => approve(opportunity) },
                    icon('check', 16),
                    'Approve',
                    h('span', { class: 'sr-only' }, ` ${opportunity.title} (${opportunity.opportunity_id})`),
                  ),
                  h(
                    'button',
                    { type: 'button', class: 'btn btn-quiet btn-sm', onClick: () => openReviewDialog(opportunity, 'returned') },
                    icon('reset', 16),
                    'Return for revision',
                    h('span', { class: 'sr-only' }, ` ${opportunity.title} (${opportunity.opportunity_id})`),
                  ),
                  h(
                    'button',
                    { type: 'button', class: 'btn btn-danger btn-sm', onClick: () => openReviewDialog(opportunity, 'declined') },
                    icon('x', 16),
                    'Decline',
                    h('span', { class: 'sr-only' }, ` ${opportunity.title} (${opportunity.opportunity_id})`),
                  ),
                ),
              ),
            ),
          ),
        )
      : emptyState('inbox', 'The review queue is empty', 'No opportunities are waiting for review. Submissions from the Employer HR view appear here as Pending Review.');

    const approvedList = approved.length
      ? h(
          'div',
          { class: 'grid-2' },
          approved
            .slice()
            .reverse()
            .map((opportunity) =>
              h(
                'article',
                { class: `card opp${ui.fresh.has(opportunity.opportunity_id) ? ' is-new' : ''}` },
                head(opportunity),
                metaChips(opportunity),
                h('div', { class: 'opp-foot' }, approvalChip(listingLabel(opportunity))),
              ),
            ),
        )
      : emptyState('checkCircle', 'Nothing approved yet', 'Approved opportunities are listed here once published to students.');

    const faqCounts = faq.counts();
    return h(
      'div',
      null,
      hero('University Administrator view', 'University Administrator', 'Review submitted opportunities: approve them for students, return them for revision, or decline them. A reason is required for return and decline.', { icon: 'shield' }),
      tabBar(ADMIN_TABS, 'Administrator sections', { faq: faqCounts.unanswered + faqCounts.pending }),
      tabPanel('review', [
        stats(
          [
            { key: 'pending', label: 'Pending review', value: pending.length, note: 'Waiting for your decision', icon: 'clock' },
            { key: 'published', label: 'Published', value: approved.length, note: 'Includes closed listings; only open listings reach students', icon: 'checkCircle' },
          ],
          'two',
        ),
        h('div', { class: 'section-head' }, h('h2', { id: 'queue-heading', tabindex: '-1' }, 'Review queue')),
        queue,
        reviewed.length > 0 && h('div', { class: 'section-head' }, h('h2', null, `Returned and declined (${reviewed.length})`)),
        reviewed.length > 0 &&
          h(
            'div',
            { class: 'grid-2' },
            reviewed.map((opportunity) =>
              h(
                'article',
                { class: `card opp${ui.fresh.has(opportunity.opportunity_id) ? ' is-new' : ''}` },
                head(opportunity),
                h('p', { class: 'reason' }, h('strong', null, `${listingLabel(opportunity)}. `), 'Reason: ', opportunity.review_reason),
                h('div', { class: 'opp-foot' }, approvalChip(listingLabel(opportunity)), h('span', { class: 'muted' }, 'Reviewed ', timeEl(opportunity.reviewed_at))),
              ),
            ),
          ),
        h('div', { class: 'section-head' }, h('h2', null, 'Published opportunities')),
        approvedList,
      ]),
      tabPanel('faq', faqAdminPanel()),
    );
  }

  // ---------- return for revision / decline (a reason is required for both) ----------

  function openReviewDialog(opportunity, decision) {
    ui.pendingReview = { id: opportunity.opportunity_id, decision };
    const returning = decision === 'returned';
    $('#review-title').textContent = returning ? 'Return for revision' : 'Decline';
    $('#review-listing').textContent = `${opportunity.title} · ${opportunity.employer_name} · ${opportunity.opportunity_id}`;
    $('#review-confirm').textContent = returning ? 'Return for revision' : 'Decline';
    $('#review-confirm').className = returning ? 'btn' : 'btn btn-danger';
    $('#review-help').textContent = returning
      ? 'Employer HR will see this reason and can revise and resubmit a new version.'
      : 'Employer HR will see this reason. Declining is final for this listing.';
    $('#review-reason').value = '';
    $('#review-reason').removeAttribute('aria-invalid');
    const error = $('#review-error');
    error.hidden = true;
    error.textContent = '';
    $('#review-dialog').showModal();
  }

  function confirmReview() {
    const { id, decision } = ui.pendingReview;
    const result = act(() => store.reviewOpportunity(id, decision, $('#review-reason').value));
    if (!result.ok) {
      const error = $('#review-error');
      error.textContent = (result.errors && result.errors.reason) || result.message;
      error.hidden = false;
      $('#review-reason').setAttribute('aria-invalid', 'true');
      $('#review-reason').focus();
      return;
    }
    ui.pendingReview = null;
    ui.dialogFocusId = 'queue-heading';
    ui.fresh = new Set([id]);
    $('#review-dialog').close();
    showToast(
      decision === 'returned'
        ? `${id} returned for revision. Employer HR can see the reason and resubmit a new version.`
        : `${id} declined. Employer HR can see the reason.`,
      { link: { href: '#employer', text: 'Next: see it as Employer HR' } },
    );
    render();
  }

  function approve(opportunity) {
    ui.focusId = 'queue-heading';
    ui.fresh = new Set([opportunity.opportunity_id]);
    const result = act(() => store.approveOpportunity(opportunity.opportunity_id));
    if (!result.ok) {
      ui.fresh = new Set();
      showToast(result.message, { error: true });
      render();
      return;
    }
    showToast(`${opportunity.opportunity_id} “${opportunity.title}” approved. Students can now see it, and Employer HR sees the new status.`, {
      link: { href: '#student', text: 'Next: apply as Student' },
    });
    render();
  }

  // ---------- Faculty Reviewer view ----------

  function facultyView() {
    const records = store.listFacultyRecords();
    const body = records.length
      ? h(
          'div',
          { class: 'grid-2' },
          records
            .slice()
            .reverse()
            .map((record) =>
              h(
                'article',
                { class: `card${ui.fresh.has(record.application.application_id) ? ' is-new' : ''}` },
                h(
                  'div',
                  { class: 'opp-head' },
                  avatar(record.student.display_name),
                  h('div', { class: 'opp-head-text' }, h('h3', null, record.student.display_name), h('p', { class: 'muted' }, `${record.opportunity.title} · ${record.opportunity.employer_name}`)),
                  chip(record.application.application_status, 'submitted'),
                ),
                facts([
                  ['Application ID', record.application.application_id],
                  ['Student ID', record.student.student_id],
                  ['Opportunity ID', record.opportunity.opportunity_id],
                  ['Review ID', record.review.review_id],
                  ['Review status', chip(record.review.review_status, 'neutral')],
                  ['Application status', record.application.application_status],
                  ['Placement status', chip(record.placement_status, 'neutral')],
                  ['Submitted', formatTime(record.application.submitted_at)],
                ]),
              ),
            ),
        )
      : emptyState('book', 'No applications yet', 'Applications submitted in the Student view appear here, linked to the same student and opportunity IDs.');

    return h(
      'div',
      null,
      hero('Faculty Reviewer view', 'Faculty Reviewer', 'Inspect student application records and their statuses.', { icon: 'book', extra: h('div', { class: 'hero-tags' }, chip('Read-only', 'neutral', 'lock'), placeholderTag(P07_LABEL)) }),
      h('p', { class: 'notice' }, icon('info', 18), 'Read-only view. Viewing an application does not approve a placement. Review decisions and placement approval are deferred.'),
      h('div', { class: 'section-head' }, h('h2', null, `Application records (${records.length})`)),
      body,
    );
  }

  // ---------- Internship Assistant (FAQ chatbot) ----------

  const PROTOTYPE_BANNER = 'Prototype. Synthetic data. Not official university policy.';
  const blankFaqDraft = () => ({ section: '', question: '', answer: '' });

  /** Loads the approved FAQ file the first time the assistant or the coordinator's FAQ tab is opened. */
  function ensureFaq() {
    if (faq.isLoaded() || ui.faqLoading) return;
    ui.faqLoading = true;
    ui.faqError = '';
    fetch(new URL('data/faq.txt', document.baseURI), { cache: 'no-store' })
      .then((response) => {
        if (!response.ok) throw new Error('FAQ request failed: ' + response.status);
        return response.text();
      })
      .then((text) => {
        const parsed = Faq.parseFaq(text);
        if (parsed.entries.length === 0) throw new Error('The FAQ file has no valid entries.');
        ui.faqLoading = false;
        faq.setBase(parsed.entries); // notifies the subscriber, which renders
      })
      .catch(() => {
        ui.faqLoading = false;
        ui.faqError = 'Could not load the approved FAQ. Check your connection and try again.';
        render();
      });
  }

  const needsFaq = () => ui.route === 'assistant' || (ui.route === 'admin' && ui.tab === 'faq');

  function faqUnavailable() {
    if (ui.faqError) {
      return h(
        'div',
        { class: 'card', role: 'alert' },
        h('p', { class: 'error' }, ui.faqError),
        h(
          'button',
          {
            type: 'button',
            class: 'btn',
            onClick: () => {
              ui.faqError = '';
              ensureFaq();
              render();
            },
          },
          'Retry loading the FAQ',
        ),
      );
    }
    return h('p', { class: 'muted', role: 'status' }, 'Loading the approved FAQ…');
  }

  function chatMessages() {
    if (!ui.chat) {
      ui.chat = [
        {
          role: 'bot',
          kind: 'greeting',
          text: 'Hi! Ask me about placements, grading, employer submissions, review or applying. I only answer from the approved FAQ, and I will say so when I do not know.',
        },
      ];
    }
    return ui.chat;
  }

  function messageElement(message) {
    if (message.role === 'user') {
      return h('div', { class: 'msg msg-user' }, h('div', { class: 'msg-bubble' }, h('span', { class: 'sr-only' }, 'You asked: '), message.text));
    }
    return h(
      'div',
      { class: `msg msg-bot${message.kind === 'unknown' ? ' is-unknown' : ''}` },
      h('span', { class: 'avatar tone-0', 'aria-hidden': 'true' }, icon('chat', 16)),
      h(
        'div',
        { class: 'msg-bubble' },
        h('span', { class: 'sr-only' }, 'Assistant: '),
        h('p', null, message.text),
        message.source &&
          h(
            'p',
            { class: 'msg-source' },
            icon('book', 14),
            h('strong', null, 'Source: '),
            `FAQ · ${message.source.section}`,
            h('span', { class: 'muted' }, ` · “${message.source.question}”${message.source.origin === 'coordinator' ? ' (added by the coordinator)' : ''}`),
          ),
        message.kind === 'unknown' && h('p', { class: 'msg-note' }, icon('inbox', 14), 'Saved in the coordinator’s list of unanswered questions.'),
      ),
    );
  }

  function assistantView() {
    const ready = faq.isLoaded();
    return h(
      'div',
      null,
      hero(
        'Internship Assistant',
        'Ask the Internship Assistant',
        'Ask in your own words. Answers come only from the approved FAQ. If the answer is not there, the assistant says so and notes your question for the coordinator.',
        { icon: 'chat' },
      ),
      h('p', { class: 'proto-banner', role: 'note' }, icon('alert', 18), h('strong', null, PROTOTYPE_BANNER)),
      h('p', { class: 'notice', role: 'note' }, icon('info', 18), FAQ_LABEL),
      h(
        'section',
        { class: 'card chat', 'aria-labelledby': 'chat-title' },
        h('h2', { class: 'card-title', id: 'chat-title' }, icon('chat', 18), 'Conversation'),
        h(
          'div',
          { id: 'chat-log', class: 'chat-log', role: 'log', 'aria-live': 'polite', 'aria-label': 'Conversation with the Internship Assistant', tabindex: '0' },
          chatMessages().map(messageElement),
        ),
        ready
          ? h(
              'div',
              { class: 'suggestions' },
              h('p', { class: 'suggestions-label' }, 'Try asking:'),
              h(
                'div',
                { class: 'suggestion-list' },
                faq
                  .approved()
                  .slice(0, 8)
                  .map((entry) => h('button', { type: 'button', class: 'suggestion', onClick: () => askAssistant(entry.question) }, entry.question)),
              ),
            )
          : faqUnavailable(),
        h(
          'p',
          { id: 'chat-privacy', class: 'privacy-reminder' },
          icon('lock', 14),
          "Please don't type personal information (names, email addresses, phone numbers or ID numbers). Questions the assistant can't answer are saved, as typed, for the coordinator.",
        ),
        h(
          'form',
          { id: 'chat-form', class: 'chat-form', novalidate: true, onSubmit: onAsk },
          h('label', { for: 'chat-input', class: 'sr-only' }, 'Your question'),
          h('input', {
            id: 'chat-input',
            type: 'text',
            name: 'question',
            maxlength: Faq.LIMITS.ask,
            autocomplete: 'off',
            placeholder: 'Ask a question, for example “Can I intern remotely?”',
            'aria-describedby': 'chat-privacy',
            disabled: !ready,
          }),
          h('button', { type: 'submit', class: 'btn', disabled: !ready }, icon('send', 16), 'Send'),
        ),
      ),
      botpressCard(),
      h(
        'p',
        { class: 'muted' },
        'Answers are copied word for word from the approved FAQ and show their FAQ section as the source. This is a keyword matcher, not a language model, so it can miss a rewording; when that happens it says "I don\'t know yet" instead of guessing.',
      ),
    );
  }

  // ---------- optional hosted chatbot (Botpress), off unless data/chatbot-config.json enables it ----------

  /** Reads data/chatbot-config.json once, when the assistant page is opened. Missing or invalid means "not configured". */
  function ensureBotConfig() {
    if (ui.bot.status !== 'idle') return;
    ui.bot.status = 'checking';
    fetch(new URL('data/chatbot-config.json', document.baseURI), { cache: 'no-store' })
      .then((response) => (response.ok ? response.json() : null))
      .then((config) => {
        const parsed = Faq.parseChatbotConfig(config);
        ui.bot.scripts = parsed.scripts;
        ui.bot.status = parsed.ok ? 'available' : 'unconfigured';
        if (parsed.ok) render();
      })
      .catch(() => {
        ui.bot.status = 'unconfigured';
      });
  }

  /** Loads the validated embed scripts one after another (the config script needs the inject script first). */
  function loadBotpress() {
    if (ui.bot.status !== 'available' && ui.bot.status !== 'error') return;
    ui.bot.status = 'loading';
    render();
    const queue = ui.bot.scripts.slice();
    const next = () => {
      const src = queue.shift();
      if (!src) {
        ui.bot.status = 'loaded';
        render();
        try {
          if (window.botpress && typeof window.botpress.open === 'function') window.botpress.open();
        } catch (error) {
          /* the widget's own button still works */
        }
        return;
      }
      const script = h('script', { src });
      script.addEventListener('load', next);
      script.addEventListener('error', () => {
        ui.bot.status = 'error';
        render();
      });
      document.body.append(script);
    };
    next();
  }

  function botpressCard() {
    const status = ui.bot.status;
    if (!['available', 'loading', 'loaded', 'error'].includes(status)) return null;
    return h(
      'section',
      { class: 'card stack', 'aria-labelledby': 'botpress-title' },
      h('h2', { class: 'card-title', id: 'botpress-title' }, icon('chat', 18), 'Prefer the Botpress assistant?'),
      h(
        'p',
        { class: 'muted' },
        "This opens a separate chatbot run by Botpress, a third party. Your questions are sent to Botpress and its model provider, not handled by this app. The coordinator's list of unanswered questions will not see them, and this page's personal-information check does not apply, so do not type personal information.",
      ),
      status === 'loaded'
        ? h('p', { class: 'notice', role: 'status' }, icon('info', 18), 'The Botpress assistant is loaded. Look for its chat button at the bottom right of the page.')
        : [
            status === 'error' && h('p', { class: 'error', role: 'alert' }, 'The Botpress assistant could not be loaded. Check your connection and try again.'),
            h(
              'div',
              { class: 'form-actions' },
              h('button', { type: 'button', class: 'btn btn-quiet', disabled: status === 'loading', onClick: loadBotpress }, status === 'loading' ? 'Loading…' : status === 'error' ? 'Try again' : 'Open the Botpress assistant'),
            ),
          ],
    );
  }

  function onAsk(event) {
    event.preventDefault();
    askAssistant($('#chat-input').value);
  }

  function askAssistant(text) {
    const typed = String(text ?? '').trim();
    if (!typed) {
      const input = $('#chat-input');
      if (input) input.focus();
      return;
    }
    const result = act(() => faq.ask(typed));
    const messages = chatMessages();
    // A message that looks like personal information is never echoed back or stored.
    messages.push({ role: 'user', text: result.kind === 'pii' ? '(message withheld: it looked like personal information)' : typed });
    messages.push({ role: 'bot', kind: result.kind, text: result.reply, source: result.source });
    if (messages.length > 60) messages.splice(0, messages.length - 60);
    ui.focusId = 'chat-input';
    render();
  }

  // ---------- coordinator: unanswered questions and FAQ approval (Administrator view, "Assistant FAQ" tab) ----------

  function faqAdminPanel() {
    const unanswered = faq.openUnanswered();
    const pending = faq.pending();
    const ready = faq.isLoaded();

    const unansweredRow = (item) =>
      h(
        'li',
        { class: 'status-row' },
        h('span', { class: 'act-icon act-system' }, icon('help', 16)),
        h(
          'div',
          { class: 'body' },
          h('div', { class: 'row-head' }, h('p', { class: 'row-title' }, item.question), item.count > 1 && chip(`Asked ${item.count} times`, 'neutral')),
          h('p', { class: 'muted' }, 'Last asked ', timeEl(item.last_asked_at)),
          h(
            'div',
            { class: 'row-actions' },
            h('button', { type: 'button', class: 'btn btn-sm', onClick: () => draftFromQuestion(item) }, 'Write an answer', h('span', { class: 'sr-only' }, ` for “${item.question}”`)),
            h('button', { type: 'button', class: 'btn btn-quiet btn-sm', onClick: () => dismissQuestion(item) }, 'Dismiss', h('span', { class: 'sr-only' }, ` “${item.question}”`)),
          ),
        ),
      );

    const pendingCard = (entry) =>
      h(
        'article',
        { class: `card${ui.fresh.has(entry.id) ? ' is-new' : ''}` },
        h('div', { class: 'card-top' }, chip(entry.section, 'neutral'), h('span', { class: 'idtag' }, entry.id)),
        h('h3', null, entry.question),
        h('p', { class: 'desc' }, entry.answer),
        h('p', { class: 'muted' }, 'Added ', timeEl(entry.created_at)),
        h(
          'div',
          { class: 'opp-foot' },
          chip('Pending', 'pending', 'clock'),
          h(
            'div',
            { class: 'row-actions' },
            h('button', { type: 'button', class: 'btn btn-sm', onClick: () => approveFaq(entry) }, icon('check', 16), 'Approve', h('span', { class: 'sr-only' }, ` ${entry.id}`)),
            h('button', { type: 'button', class: 'btn btn-quiet btn-sm', onClick: () => discardFaq(entry) }, 'Discard', h('span', { class: 'sr-only' }, ` ${entry.id}`)),
          ),
        ),
      );

    const form = h(
      'form',
      { id: 'faq-form', class: 'card form', novalidate: true, onSubmit: onFaqAdd, onInput: onFaqInput },
      h('h2', { class: 'card-title' }, icon('plus', 18), 'Add an FAQ entry', chip('Coordinator approval required', 'pending', 'lock')),
      h('p', { class: 'hint' }, 'Use plain language and no personal information. The entry is saved as Pending and the assistant does not use it until it is approved below.'),
      ui.faqMessage && h('div', { id: 'faq-form-error', class: 'error-summary', role: 'alert', tabindex: '-1' }, ui.faqMessage),
      field({
        id: 'faq-section',
        name: 'section',
        label: 'Section',
        value: ui.faqDraft.section,
        error: ui.faqErrors.section,
        required: true,
        maxlength: Faq.LIMITS.section,
        list: 'faq-sections',
        datalist: ready ? faq.sections() : [],
        hint: 'Choose an existing section or type a new one.',
      }),
      field({ id: 'faq-question', name: 'question', label: 'Question', value: ui.faqDraft.question, error: ui.faqErrors.question, required: true, maxlength: Faq.LIMITS.question }),
      field({ id: 'faq-answer', name: 'answer', label: 'Answer', value: ui.faqDraft.answer, error: ui.faqErrors.answer, required: true, multiline: true, maxlength: Faq.LIMITS.answer, counter: true }),
      h('div', { class: 'form-actions' }, h('button', { type: 'submit', class: 'btn' }, icon('send', 16), 'Submit for coordinator approval')),
    );

    return [
      h('p', { class: 'notice' }, icon('info', 18), 'Coordinator approval required. New entries stay Pending, and the assistant only ever answers from approved entries.'),
      h('div', { class: 'section-head' }, h('h2', { id: 'unanswered-heading', class: 'card-title', tabindex: '-1' }, icon('help', 18), `Unanswered questions (${unanswered.length})`)),
      unanswered.length
        ? h('div', { class: 'card' }, h('ul', { class: 'status-list' }, unanswered.map(unansweredRow)))
        : emptyState('checkCircle', 'No unanswered questions', 'Questions the assistant cannot answer appear here, exactly as typed, so the coordinator can write an answer.'),
      form,
      h(
        'div',
        { class: 'section-head' },
        h('h2', { id: 'pending-heading', class: 'card-title', tabindex: '-1' }, icon('clock', 18), `Pending entries (${pending.length})`, chip('Coordinator approval required', 'pending')),
      ),
      pending.length ? h('div', { class: 'grid-2' }, pending.map(pendingCard)) : emptyState('inbox', 'No pending entries', 'Entries added above wait here for approval.', null, true),
      ready ? approvedFaq(faq.approved()) : faqUnavailable(),
    ];
  }

  function approvedFaq(entries) {
    const groups = new Map();
    for (const entry of entries) {
      if (!groups.has(entry.section)) groups.set(entry.section, []);
      groups.get(entry.section).push(entry);
    }
    return h(
      'div',
      { class: 'stack' },
      h(
        'div',
        { class: 'section-head' },
        h('h2', { class: 'card-title' }, icon('book', 18), `Approved FAQ (${entries.length})`),
        h('button', { type: 'button', class: 'btn btn-quiet btn-sm', onClick: exportFaq }, icon('download', 16), 'Download faq.txt'),
      ),
      h(
      'details',
      { class: 'card faq-approved' },
      h('summary', null, 'Show what the assistant can answer'),
      h(
        'div',
        { class: 'faq-groups' },
        [...groups].map(([section, list]) =>
          h(
            'section',
            { class: 'faq-group' },
            h('h3', null, section),
            h(
              'ul',
              null,
              list.map((entry) =>
                h(
                  'li',
                  null,
                  h('p', { class: 'row-title' }, entry.question),
                  h('p', { class: 'muted' }, entry.answer),
                  h('span', { class: 'idtag' }, `${entry.id} · ${entry.origin === 'coordinator' ? 'added by coordinator' : 'faq.txt'}`),
                ),
              ),
            ),
          ),
        ),
      ),
      h('p', { class: 'hint' }, 'Download faq.txt is the file to upload as a chatbot Knowledge Base. Entries approved here exist only in this browser until the file in the repository is replaced.'),
      ),
    );
  }

  function draftFromQuestion(item) {
    ui.faqDraft = { section: '', question: item.question.slice(0, Faq.LIMITS.question), answer: '' };
    ui.faqErrors = {};
    ui.faqMessage = '';
    ui.focusId = 'faq-section';
    render();
  }

  function dismissQuestion(item) {
    act(() => faq.dismissUnanswered(item.id));
    ui.focusId = 'unanswered-heading';
    render();
  }

  function onFaqInput(event) {
    const name = event.target.getAttribute('name');
    if (!name || !(name in ui.faqDraft)) return;
    ui.faqDraft[name] = event.target.value;
    if (name === 'answer') {
      const counter = $('#faq-answer-count');
      if (counter) counter.textContent = `${event.target.value.length} / ${Faq.LIMITS.answer}`;
    }
  }

  function onFaqAdd(event) {
    event.preventDefault();
    const result = act(() => faq.addEntry(ui.faqDraft));
    if (!result.ok) {
      ui.faqErrors = result.errors;
      ui.faqMessage = result.message;
      const firstInvalid = ['section', 'question', 'answer'].find((name) => result.errors[name]);
      ui.focusId = `faq-${firstInvalid}`;
      render();
      return;
    }
    ui.faqDraft = blankFaqDraft();
    ui.faqErrors = {};
    ui.faqMessage = '';
    ui.fresh = new Set([result.entry.id]);
    ui.focusId = 'pending-heading';
    showToast(`${result.entry.id} added as Pending. The coordinator must approve it before the assistant can use it.`);
    render();
  }

  function approveFaq(entry) {
    ui.fresh = new Set([entry.id]);
    ui.focusId = 'pending-heading';
    const result = act(() => faq.approve(entry.id));
    if (!result.ok) {
      ui.fresh = new Set();
      showToast(result.message, { error: true });
      render();
      return;
    }
    const covered = result.resolved ? ` ${result.resolved} unanswered question${result.resolved === 1 ? ' is' : 's are'} now covered.` : '';
    showToast(`${entry.id} approved. The assistant can now answer it.${covered}`, { link: { href: '#assistant', text: 'Next: ask the assistant' } });
    render();
  }

  function discardFaq(entry) {
    const result = act(() => faq.discard(entry.id));
    ui.focusId = 'pending-heading';
    showToast(result.ok ? `${entry.id} discarded.` : result.message, { error: !result.ok });
    render();
  }

  function exportFaq() {
    try {
      const url = URL.createObjectURL(new Blob([faq.exportText()], { type: 'text/plain;charset=utf-8' }));
      const link = h('a', { href: url, download: 'faq.txt' });
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      showToast('Downloaded faq.txt with the approved entries.');
    } catch (error) {
      showToast('This browser could not create the file.', { error: true });
    }
  }

  // ---------- chrome: navigation, top bar, render loop ----------

  const VIEWS = { overview: overviewView, student: studentView, employer: employerView, admin: adminView, faculty: facultyView, assistant: assistantView };

  function persona(routeId) {
    switch (routeId) {
      case 'employer':
        return { name: 'HR Representative', detail: 'Sample employer user' };
      case 'admin':
        return { name: 'Placement Office', detail: 'Sample administrator' };
      case 'student': {
        const student = store.getStudent(ui.studentId);
        return { name: student.display_name, detail: `${student.student_id} · Student` };
      }
      case 'faculty': {
        const faculty = store.getFaculty();
        return { name: faculty.display_name, detail: `${faculty.faculty_id} · Faculty` };
      }
      case 'assistant':
        return { name: 'Internship Assistant', detail: 'Answers from the approved FAQ' };
      default:
        return { name: 'Demo overview', detail: 'Choose a role to begin' };
    }
  }

  function renderTopbar() {
    const current = ROUTES.find((item) => item.id === ui.route);
    $('#crumb-current').textContent = current.label;
    const who = persona(ui.route);
    $('#persona').replaceChildren(
      ui.route === 'overview' || ui.route === 'assistant'
        ? h('span', { class: 'avatar tone-0', 'aria-hidden': 'true' }, icon(ui.route === 'assistant' ? 'chat' : 'layers', 16))
        : avatar(who.name),
      h('span', { class: 'persona-text' }, h('span', { class: 'persona-name' }, who.name), h('span', { class: 'persona-detail' }, who.detail)),
      h('span', { class: 'sim-tag', title: 'There is no real sign-in; roles are switched from the sidebar.' }, ui.route === 'overview' ? 'Demo' : ui.route === 'assistant' ? 'Prototype' : 'Simulated'),
    );
  }

  function render(options) {
    const view = $('#view');
    view.classList.remove('view-enter');
    view.replaceChildren(VIEWS[ui.route]());
    if (ui.enter) {
      void view.offsetWidth; // restart the entrance animation
      view.classList.add('view-enter');
      ui.enter = false;
    }
    const wide = ui.route === 'overview' || ui.route === 'assistant'; // these pages have no journey/activity rail
    $('#workspace').classList.toggle('no-rail', wide);
    $('#rail').replaceChildren(...(wide ? [] : [journeyCard(false), activityCard(6)]));
    renderTopbar();
    if (ui.route === 'student') fillResults();
    if (ui.route === 'assistant') {
      const log = $('#chat-log');
      if (log) log.scrollTop = log.scrollHeight;
    }
    $('#storage-warning').hidden = store.isPersistent();
    ui.fresh = new Set();
    ui.activityPrimed = true;
    if (ui.focusId) {
      const target = document.getElementById(ui.focusId);
      if (target) target.focus();
      ui.focusId = null;
    } else if (options && options.focusHeading) {
      const heading = $('#page-title');
      if (heading) heading.focus();
    }
  }

  function buildNav() {
    const link = (item) =>
      h(
        'a',
        { href: `#${item.id}`, class: 'nav-item', 'data-route': item.id },
        h('span', { class: 'nav-icon' }, icon(item.icon, 20)),
        h(
          'span',
          { class: 'nav-text' },
          h('span', { class: 'nav-label' }, h('span', { class: 'nav-full' }, item.label), h('span', { class: 'nav-short' }, item.short)),
          h('span', { class: 'nav-hint' }, item.hint),
        ),
      );
    $('#role-nav').replaceChildren(link(OVERVIEW), h('p', { class: 'nav-group' }, 'Demo roles'), ...ROLES.map(link), h('p', { class: 'nav-group' }, 'Help'), link(ASSISTANT));
  }

  function updateNav() {
    document.querySelectorAll('#role-nav a').forEach((anchor) => {
      if (anchor.dataset.route === ui.route) anchor.setAttribute('aria-current', 'page');
      else anchor.removeAttribute('aria-current');
    });
    const current = ROUTES.find((item) => item.id === ui.route);
    document.title = `${current.label} · IPP Sprint 3`;
  }

  function route(initial) {
    const [routeId, tabId] = location.hash.replace(/^#\/?/, '').split('/');
    const next = ROUTES.some((item) => item.id === routeId) ? routeId : DEFAULT_ROUTE;
    const changed = next !== ui.route;
    ui.route = next;
    const tabs = ROLE_TABS[next];
    ui.tab = tabs ? (tabs.some((tab) => tab.id === tabId) ? tabId : tabs[0].id) : null;
    if (needsFaq()) ensureFaq();
    if (ui.route === 'assistant') ensureBotConfig();
    updateNav();
    if (changed || initial) {
      if (changed) clearToast();
      ui.enter = true;
      render({ focusHeading: !initial });
      if (changed && !initial) window.scrollTo(0, 0);
    } else if (tabs) {
      setTab(ui.tab);
    }
  }

  // ---------- reset + dialogs ----------

  function wireDialogs() {
    const applyDialog = $('#apply-dialog');
    const resetDialog = $('#reset-dialog');

    $('#apply-cancel').addEventListener('click', () => applyDialog.close());
    $('#apply-confirm').addEventListener('click', confirmApply);
    $('#review-cancel').addEventListener('click', () => $('#review-dialog').close());
    $('#review-confirm').addEventListener('click', confirmReview);
    $('#reset-btn').addEventListener('click', () => resetDialog.showModal());
    $('#reset-cancel').addEventListener('click', () => resetDialog.close());
    $('#reset-confirm').addEventListener('click', () => {
      ui.draft = blankDraft();
      ui.errors = {};
      ui.formMessage = '';
      ui.query = '';
      ui.workMode = 'All';
      ui.sort = 'newest';
      ui.nameDraft = null;
      ui.nameError = '';
      ui.hrAuthorized = true;
      ui.sampleIndex = 0;
      ui.resubmitOf = null;
      ui.seenActivity.clear();
      ui.studentId = store.listStudents()[0].student_id;
      ui.dialogFocusId = 'page-title';
      resetDialog.close();
      ui.chat = null;
      ui.faqDraft = blankFaqDraft();
      ui.faqErrors = {};
      ui.faqMessage = '';
      act(() => {
        store.reset();
        faq.reset();
      });
      showToast('Demo data reset to the initial synthetic records.');
      render();
    });

    // Focus is handled after close so the browser's own focus restoration cannot override it.
    for (const dialog of [applyDialog, resetDialog, $('#review-dialog')]) {
      dialog.addEventListener('close', () => {
        if (!ui.dialogFocusId) return;
        const target = document.getElementById(ui.dialogFocusId);
        ui.dialogFocusId = null;
        if (target) target.focus();
      });
    }
  }

  function init() {
    faq = Faq.createFaqStore(Store.browserStorage());
    faq.subscribe(() => {
      if (!ui.batch) render();
    });
    buildNav();
    wireDialogs();
    store.subscribe(() => {
      if (!ui.batch) render();
    });
    window.addEventListener('hashchange', () => route(false));
    window.addEventListener('storage', (event) => {
      if (event.key === null || event.key === Store.STORAGE_KEY) store.refresh();
      if (event.key === null || event.key === Faq.STORAGE_KEY) faq.refresh();
    });
    setInterval(() => refreshRelativeTimes(), 15000);
    route(true);
  }

  async function start() {
    try {
      const response = await fetch(new URL('data/ipp_sample_data.json', document.baseURI), { cache: 'no-store' });
      if (!response.ok) throw new Error('Seed request failed: ' + response.status);
      store = Store.createStore(Store.browserStorage(), await response.json());
      ui.studentId = store.listStudents()[0].student_id;
      init();
    } catch (error) {
      $('#view').replaceChildren(h('div', { class: 'card', role: 'alert' },
        h('h1', null, 'Unable to load synthetic demo data'),
        h('p', null, 'Check your connection and try again.'),
        h('button', { type: 'button', class: 'btn', onClick: start }, 'Retry loading data'),
      ));
    }
  }

  start();
})();
