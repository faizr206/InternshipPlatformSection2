/* Shared synthetic IPP records and browser-local demo rules. No production access control. */
(function (root) {
  'use strict';

  const STORAGE_KEY = 'ipp-demo-v2';
  const SCHEMA_VERSION = 2;
  const ACTIVITY_LIMIT = 60;
  const OPPORTUNITY_STATUS = Object.freeze({ PENDING: 'Pending Review', APPROVED: 'Approved', RETURNED: 'Returned for revision', DECLINED: 'Declined' });
  const REASON_LIMIT = 300;
  const APPLICATION_STATUS = Object.freeze({ SUBMITTED: 'Submitted' });
  const PLACEMENT_STATUS = 'Not placed';
  const REVIEW_STATUS = Object.freeze({ NOT_STARTED: 'Not started' });
  const WORK_MODES = Object.freeze(['On-site', 'Hybrid', 'Remote']);
  const LIMITS = Object.freeze({ organization_name: 80, title: 100, location: 80, description: 600, duration: 40, display_name: 60 });
  const FIELD_LABELS = { organization_name: 'Organization name', title: 'Title', description: 'Description', location: 'Location' };
  const REQUIRED_FIELDS = ['organization_name', 'title', 'description', 'location'];
  const SEED_ARRAYS = ['student_profiles', 'published_listings', 'skills_vocabulary'];

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function hasSharedRecords(value) {
    return value && typeof value === 'object' && SEED_ARRAYS.every((key) => Array.isArray(value[key]));
  }

  function seedState(seed) {
    if (!hasSharedRecords(seed)) throw new Error('Load data/ipp_sample_data.json before creating the demo store.');
    return Object.assign(clone(seed), {
      version: SCHEMA_VERSION,
      faculty: [{ faculty_id: 'FAC-001', display_name: 'Dr. Sam Okafor' }],
      applications: [],
      reviews: [],
      activity: [],
      listing_versions: [],
    });
  }

  function latestSubmitted(profiles, studentId) {
    return profiles.reduce((latest, profile) => {
      if (profile.student_id !== studentId || profile.profile_status !== 'submitted') return latest;
      return !latest || Number(profile.profile_version) > Number(latest.profile_version) ? profile : latest;
    }, null);
  }

  function isAvailable(listing) {
    return listing.publication_status === 'published' && listing.listing_status === 'open';
  }

  // Read projections stop supervisor fields reaching student cards, dialogs or application history.
  function studentListing(listing) {
    if (!listing) return null;
    const safe = clone(listing);
    delete safe.supervisor_name;
    delete safe.supervisor_contact;
    return safe;
  }

  function nextId(prefix, records, key) {
    const max = records.reduce((result, record) => {
      const match = /-(\d+)$/.exec(String(record[key]));
      return match ? Math.max(result, Number(match[1])) : result;
    }, 0);
    return prefix + '-' + String(max + 1).padStart(3, '0');
  }

  function validProfile(profile) {
    return profile && typeof profile.student_id === 'string' && profile.student_id.trim() &&
      typeof profile.display_name === 'string' && profile.display_name.trim() &&
      Number.isInteger(Number(profile.profile_version)) && Number(profile.profile_version) > 0 &&
      typeof profile.profile_status === 'string' &&
      Array.isArray(profile.interests) && profile.interests.every((interest) => typeof interest === 'string') &&
      Array.isArray(profile.skills) && profile.skills.every((skill) => skill && typeof skill.skill_id === 'string') &&
      (profile.availability_start === null || typeof profile.availability_start === 'string') &&
      (profile.availability_end === null || typeof profile.availability_end === 'string');
  }

  function isValidState(value) {
    return hasSharedRecords(value) && value.version === SCHEMA_VERSION &&
      ['faculty', 'applications', 'reviews'].every((key) => Array.isArray(value[key])) &&
      value.faculty.length > 0 &&
      value.student_profiles.every(validProfile) &&
      value.student_profiles.some((profile) => profile.profile_status === 'submitted') &&
      value.published_listings.every((listing) => listing && typeof listing.opportunity_id === 'string' && typeof listing.title === 'string' && typeof listing.employer_name === 'string');
  }

  function browserStorage() {
    try {
      const storage = root.localStorage;
      storage.setItem('__ipp_probe__', '1');
      storage.removeItem('__ipp_probe__');
      return storage;
    } catch (error) {
      return null;
    }
  }

  function createStore(storage, seed) {
    // Snapshot the supplied fixture so reset never mutates the published shared contract.
    const initial = seedState(seed);
    const listeners = new Set();
    let persistent = Boolean(storage);
    let state = load();

    function load() {
      if (storage) {
        try {
          const raw = storage.getItem(STORAGE_KEY);
          if (raw) {
            const parsed = JSON.parse(raw);
            if (isValidState(parsed)) {
              // Preserve browser records written before the optional activity feed was added.
              if (!Array.isArray(parsed.activity)) parsed.activity = [];
              if (!Array.isArray(parsed.listing_versions)) parsed.listing_versions = [];
              parsed.activity = parsed.activity.slice(-ACTIVITY_LIMIT);
              return parsed;
            }
          }
        } catch (error) {
          persistent = false;
        }
      }
      return clone(initial);
    }

    function save() {
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

    function refresh() {
      state = load();
      for (const listener of listeners) listener();
    }

    function fail(code, message, extra) {
      return Object.assign({ ok: false, code, message }, extra);
    }

    function log(role, kind, text, ref) {
      state.activity.push({
        activity_id: nextId('ACT', state.activity, 'activity_id'),
        at: new Date().toISOString(),
        role,
        kind,
        text,
        ref: ref || '',
      });
      if (state.activity.length > ACTIVITY_LIMIT) state.activity.splice(0, state.activity.length - ACTIVITY_LIMIT);
    }

    /** Shared by first submissions and resubmissions: authorization, trimming and validation. */
    function readListingInput(input, options) {
      if (!options || !options.hrAuthorized) {
        return { failure: fail('unauthorized', 'Submission blocked: only an authorized HR representative can submit opportunities. (Simulated control; real authorization is deferred.)') };
      }
      const values = {
        organization_name: String(input.organization_name ?? input.employer_name ?? '').trim(),
        title: String(input.title ?? '').trim(),
        description: String(input.description ?? '').trim(),
        location: String(input.location ?? '').trim(),
        duration: String(input.duration ?? '').trim(),
      };
      const errors = {};
      for (const field of REQUIRED_FIELDS) {
        if (!values[field]) errors[field] = FIELD_LABELS[field] + ' is required.';
      }
      for (const field of Object.keys(values)) {
        if (!errors[field] && values[field].length > LIMITS[field]) {
          errors[field] = (FIELD_LABELS[field] || 'Duration') + ' must be ' + LIMITS[field] + ' characters or fewer.';
        }
      }
      if (Object.keys(errors).length) return { failure: fail('validation', 'Fix the highlighted fields and submit again.', { errors }) };
      const mode = String(input.work_mode ?? 'hybrid').toLowerCase();
      return { values, workMode: ['on-site', 'hybrid', 'remote'].includes(mode) ? mode : 'hybrid' };
    }

    function submitOpportunity(input, options) {
      const read = readListingInput(input, options);
      if (read.failure) return read.failure;
      const values = read.values;
      const opportunity = {
        opportunity_id: nextId('OP', state.published_listings, 'opportunity_id'),
        version: 1,
        submission_version: 1,
        employer_name: values.organization_name,
        title: values.title,
        description: values.description,
        sector: '',
        location: values.location,
        work_mode: read.workMode,
        start_date: null,
        end_date: null,
        duration: values.duration || 'Not specified',
        required_skills: [],
        desirable_skills: [],
        publication_status: 'unpublished',
        listing_status: 'open',
        supervisor_name: null,
        supervisor_contact: null,
        origin: 'demo',
      };
      state.published_listings.push(opportunity);
      log('employer', 'opportunity_submitted', 'Employer HR submitted “' + opportunity.title + '” for review', opportunity.opportunity_id);
      save();
      return { ok: true, opportunity: clone(opportunity) };
    }

    function approveOpportunity(opportunityId) {
      const opportunity = state.published_listings.find((item) => item.opportunity_id === opportunityId);
      if (!opportunity) return fail('not_found', 'Opportunity ' + opportunityId + ' does not exist.');
      if (opportunity.publication_status === 'published') return fail('already_approved', opportunityId + ' is already published.');
      if (opportunity.review_status) return fail('not_pending', opportunityId + ' was already ' + (opportunity.review_status === 'returned' ? 'returned for revision' : 'declined') + '.');
      opportunity.publication_status = 'published';
      log('admin', 'opportunity_approved', 'Administrator approved “' + opportunity.title + '”', opportunity.opportunity_id);
      save();
      return { ok: true, opportunity: clone(opportunity) };
    }

    /**
     * Administrator decision on a listing that is still under review. A reason is required for both
     * outcomes. Returned listings can be resubmitted by the employer; declined listings are final.
     */
    function reviewOpportunity(opportunityId, decision, reason) {
      const opportunity = state.published_listings.find((item) => item.opportunity_id === opportunityId);
      if (!opportunity) return fail('not_found', 'Opportunity ' + opportunityId + ' does not exist.');
      if (decision !== 'returned' && decision !== 'declined') return fail('invalid_decision', 'Choose return for revision or decline.');
      if (opportunity.publication_status === 'published') return fail('already_approved', opportunityId + ' is already published.');
      if (opportunity.review_status) return fail('not_pending', opportunityId + ' already has a review decision.');
      const text = String(reason ?? '').trim();
      if (!text) return fail('validation', 'A reason is required.', { errors: { reason: 'A reason is required.' } });
      if (text.length > REASON_LIMIT) {
        const message = 'The reason must be ' + REASON_LIMIT + ' characters or fewer.';
        return fail('validation', message, { errors: { reason: message } });
      }
      opportunity.review_status = decision;
      opportunity.review_reason = text;
      opportunity.reviewed_at = new Date().toISOString();
      const action = decision === 'returned' ? 'returned “' + opportunity.title + '” for revision' : 'declined “' + opportunity.title + '”';
      log('admin', decision === 'returned' ? 'opportunity_returned' : 'opportunity_declined', 'Administrator ' + action, opportunity.opportunity_id);
      save();
      return { ok: true, opportunity: clone(opportunity) };
    }

    /**
     * The employer's answer to a return for revision. Same opportunity ID, next version. The version
     * that was returned is archived untouched (old versions are never edited) and the new one goes
     * back into the review queue.
     */
    function resubmitOpportunity(opportunityId, input, options) {
      const opportunity = state.published_listings.find((item) => item.opportunity_id === opportunityId);
      if (!opportunity) return fail('not_found', 'Opportunity ' + opportunityId + ' does not exist.');
      if (opportunity.review_status !== 'returned') return fail('not_returned', 'Only a listing returned for revision can be resubmitted.');
      const read = readListingInput(input, options);
      if (read.failure) return read.failure;
      const previous = Object.assign(clone(opportunity), { archived_at: new Date().toISOString() });
      state.listing_versions.push(previous);
      const values = read.values;
      Object.assign(opportunity, {
        version: Number(opportunity.version || 1) + 1,
        submission_version: Number(opportunity.submission_version || 1) + 1,
        employer_name: values.organization_name,
        title: values.title,
        description: values.description,
        location: values.location,
        work_mode: read.workMode,
        duration: values.duration || 'Not specified',
        publication_status: 'unpublished',
        listing_status: 'open',
      });
      delete opportunity.review_status;
      delete opportunity.review_reason;
      delete opportunity.reviewed_at;
      log('employer', 'opportunity_resubmitted', 'Employer HR resubmitted “' + opportunity.title + '” as version ' + opportunity.version, opportunity.opportunity_id);
      save();
      return { ok: true, opportunity: clone(opportunity), previous: clone(previous) };
    }

    /** Earlier versions of a listing, oldest first. */
    function listVersions(opportunityId) {
      return state.listing_versions.filter((item) => item.opportunity_id === opportunityId).map(clone);
    }

    function getStudent(studentId) {
      const profile = latestSubmitted(state.student_profiles, studentId);
      return profile ? clone(profile) : null;
    }

    function listStudents() {
      return [...new Set(state.student_profiles.map((profile) => profile.student_id))].map(getStudent).filter(Boolean);
    }

    function hasApplied(studentId, opportunityId) {
      return state.applications.some((item) => item.student_id === studentId && item.opportunity_id === opportunityId);
    }

    function submitApplication(studentId, opportunityId) {
      const student = getStudent(studentId);
      if (!student) return fail('not_found', 'A submitted student profile is required.');
      const opportunity = state.published_listings.find((item) => item.opportunity_id === opportunityId);
      if (!opportunity) return fail('not_found', 'Opportunity ' + opportunityId + ' does not exist.');
      if (!isAvailable(opportunity)) return fail('not_approved', 'Only published and open listings accept applications.');
      if (hasApplied(studentId, opportunityId)) return fail('duplicate', 'You have already applied to this opportunity.');
      const application = {
        application_id: nextId('APP', state.applications, 'application_id'),
        opportunity_id: opportunityId,
        student_id: studentId,
        application_status: APPLICATION_STATUS.SUBMITTED,
        submitted_at: new Date().toISOString(),
      };
      const review = {
        review_id: nextId('REV', state.reviews, 'review_id'),
        application_id: application.application_id,
        faculty_id: state.faculty[0].faculty_id,
        review_status: REVIEW_STATUS.NOT_STARTED,
      };
      state.applications.push(application);
      state.reviews.push(review);
      log('student', 'application_submitted', student.display_name + ' applied to “' + opportunity.title + '”', application.application_id);
      save();
      return { ok: true, application: clone(application), review: clone(review) };
    }

    function updateDisplayName(studentId, displayName) {
      const student = getStudent(studentId);
      if (!student) return fail('not_found', 'A submitted student profile is required.');
      const name = String(displayName ?? '').trim();
      const message = !name ? 'Display name is required.' : name.length > LIMITS.display_name ? 'Display name must be ' + LIMITS.display_name + ' characters or fewer.' : '';
      if (message) return fail('validation', message, { errors: { display_name: message } });
      if (student.display_name === name) return { ok: true, student };
      const version = Math.max(...state.student_profiles.filter((profile) => profile.student_id === studentId).map((profile) => Number(profile.profile_version))) + 1;
      const corrected = Object.assign(student, { display_name: name, profile_version: version, profile_status: 'submitted' });
      state.student_profiles.push(corrected);
      log('student', 'profile_updated', 'Student display name changed to “' + name + '”', studentId);
      save();
      return { ok: true, student: clone(corrected) };
    }

    function reset() {
      state = clone(initial);
      log('system', 'demo_reset', 'Demo data reset to the shared synthetic records', '');
      save();
    }

    function listOpportunities(filter) {
      return state.published_listings.filter((listing) => {
        if (!filter || !filter.status) return true;
        if (filter.status === OPPORTUNITY_STATUS.PENDING) return listing.publication_status === 'unpublished' && !listing.review_status;
        if (filter.status === OPPORTUNITY_STATUS.APPROVED) return listing.publication_status === 'published';
        if (filter.status === OPPORTUNITY_STATUS.RETURNED) return listing.review_status === 'returned';
        if (filter.status === OPPORTUNITY_STATUS.DECLINED) return listing.review_status === 'declined';
        return false;
      }).map(clone);
    }

    function searchApproved(query, options) {
      const opts = options || {};
      const needle = String(query ?? '').trim().toLowerCase();
      let listings = state.published_listings.filter((listing) => isAvailable(listing) &&
        (!needle || listing.title.toLowerCase().includes(needle) || listing.employer_name.toLowerCase().includes(needle)));
      const workMode = String(opts.workMode ?? '').toLowerCase();
      if (WORK_MODES.some((mode) => mode.toLowerCase() === workMode)) {
        listings = listings.filter((listing) => listing.work_mode.toLowerCase() === workMode);
      }
      if (opts.sort === 'newest') listings.reverse();
      else if (opts.sort === 'title') listings.sort((a, b) => a.title.localeCompare(b.title));
      return listings.map(studentListing);
    }

    function getFaculty() {
      return clone(state.faculty[0]);
    }

    /** Newest first. */
    function listActivity(limit) {
      return state.activity
        .slice()
        .reverse()
        .slice(0, limit || ACTIVITY_LIMIT)
        .map(clone);
    }

    /**
     * Progress of the most recent opportunity submitted in this demo through the four hand-offs.
     * `placement_status` is reported separately because applying never implies a placement.
     */
    function getJourney() {
      const tracked = state.published_listings.slice().reverse().find((opportunity) => opportunity.origin === 'demo') || null;
      const application = tracked ? state.applications.find((item) => item.opportunity_id === tracked.opportunity_id) : null;
      const reviewed = Boolean(application && state.reviews.some((review) => review.application_id === application.application_id));
      const outcome = tracked && !isAvailable(tracked) ? tracked.review_status || null : null;
      const stages = [
        { key: 'submitted', role: 'employer', label: 'Submitted by Employer HR', done: Boolean(tracked) },
        { key: 'approved', role: 'admin', label: outcome === 'returned' ? 'Returned for revision by Administrator' : outcome === 'declined' ? 'Declined by Administrator' : 'Approved by Administrator', done: Boolean(tracked && isAvailable(tracked)), blocked: Boolean(outcome) },
        { key: 'applied', role: 'student', label: 'Student applied', done: Boolean(application) },
        { key: 'visible', role: 'faculty', label: 'Visible to Employer HR and Faculty', done: reviewed },
      ];
      return {
        opportunity: tracked ? studentListing(tracked) : null,
        application: application ? clone(application) : null,
        stages,
        complete: stages.every((stage) => stage.done),
        placement_status: PLACEMENT_STATUS,
      };
    }

    function listStudentApplications(studentId) {
      return state.applications.filter((application) => application.student_id === studentId).map((application) => Object.assign(clone(application), {
        opportunity: studentListing(state.published_listings.find((listing) => listing.opportunity_id === application.opportunity_id)),
        review: clone(state.reviews.find((review) => review.application_id === application.application_id) || null),
        placement_status: PLACEMENT_STATUS,
      }));
    }

    function listFacultyRecords() {
      return state.applications.map((application) => ({
        application: clone(application),
        opportunity: studentListing(state.published_listings.find((listing) => listing.opportunity_id === application.opportunity_id)),
        student: getStudent(application.student_id),
        review: clone(state.reviews.find((review) => review.application_id === application.application_id)),
        placement_status: PLACEMENT_STATUS,
      }));
    }

    function listEmployerApplications() {
      return state.applications
        .slice()
        .reverse()
        .map((application) => {
          const opportunity = state.published_listings.find((candidate) => candidate.opportunity_id === application.opportunity_id);
          const student = getStudent(application.student_id);
          return {
            application: clone(application),
            opportunity: studentListing(opportunity),
            student: {
              student_id: student.student_id,
              display_name: student.display_name,
              profile_version: student.profile_version,
              profile_status: student.profile_status,
            },
            placement_status: PLACEMENT_STATUS,
          };
        });
    }

    /** Number of applications received per opportunity ID, e.g. { 'OPP-003': 1 }. */
    function applicantCounts() {
      const byOpportunity = {};
      for (const application of state.applications) {
        byOpportunity[application.opportunity_id] = (byOpportunity[application.opportunity_id] || 0) + 1;
      }
      return byOpportunity;
    }

    function counts() {
      return {
        pending: state.published_listings.filter((listing) => listing.publication_status === 'unpublished' && !listing.review_status).length,
        approved: state.published_listings.filter(isAvailable).length,
        applications: state.applications.length,
      };
    }

    return {
      subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
      isPersistent: () => persistent,
      getSkillsVocabulary: () => clone(state.skills_vocabulary),
      getApplicationFor(studentId, opportunityId) {
        const found = state.applications.find((application) => application.student_id === studentId && application.opportunity_id === opportunityId);
        return found ? clone(found) : null;
      },
      getFaculty, listActivity, getJourney, listEmployerApplications, applicantCounts,
      refresh, reset, submitOpportunity, approveOpportunity, reviewOpportunity, resubmitOpportunity, listVersions, submitApplication, updateDisplayName, hasApplied,
      listOpportunities, searchApproved, getStudent, listStudents, listStudentApplications, listFacultyRecords, counts,
    };
  }

  root.IPPStore = Object.freeze({ STORAGE_KEY, OPPORTUNITY_STATUS, APPLICATION_STATUS, PLACEMENT_STATUS, REVIEW_STATUS, WORK_MODES, LIMITS, seedState, createStore, browserStorage });
})(globalThis);
