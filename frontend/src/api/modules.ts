/**
 * Typed calls for every module router in backend/app/modules. Field names are the backend's (snake_case).
 * Mutations send actor_role (simulated roles); the backend checks it and returns 403 for the wrong role.
 */
import { request } from "./client";
import type { Role } from "./types";

// ---------- shared ----------
export interface Skill { skill_id: string; evidence_status: "self_declared" | "reviewed"; reviewed_by?: string | null; reviewed_at?: string | null; evidence_id?: string | null }
export interface Profile {
  student_id: string; display_name: string; profile_version: number; profile_status?: string;
  interests: string[]; availability_start: string | null; availability_end: string | null; skills: Skill[];
  goals?: string | null; preferred_location?: string | null;
}
export interface Listing {
  opportunity_id: string; version: number; submission_version?: number; employer_name: string; title: string;
  sector?: string; location: string; work_mode: string; description?: string; start_date: string | null;
  end_date: string | null; duration?: string; required_skills: string[]; desirable_skills: string[];
  publication_status: string; listing_status: string; review_status?: string | null; review_reason?: string | null;
  reviewed_by?: string | null; supervisor_name?: string | null; supervisor_contact?: string | null; status?: string;
  external?: boolean; source_url?: string;
}
export interface HistoryEvent { action: string; actor_role: string; actor_name: string; reason: string | null; next_action: string; created_at: string }
export interface Application {
  application_id: string; student_id: string; student_name: string; profile_version: number; opportunity_id: string;
  opportunity_version: number; opportunity_title: string; employer_name: string | null; application_status: string;
  placement_status: string; submitted_at: string; statement: string | null; history: HistoryEvent[];
  interview: { starts_at: string; duration_minutes: number; mode: string; location: string; completed_at: string | null } | null;
}
export interface Recommendation {
  recommendation_id: string; run_id: string; student_id: string; profile_version: number; opportunity_id: string;
  opportunity_version: number; method_version: string; score: number; compatible: boolean;
  eligibility: "eligible" | "unknown" | "ineligible"; reasons: string[]; gaps: string[]; unknowns: string[];
  created_at: string; ai_method_version?: string;
  ai_matches: { term: string; field: string; skill_id: string; skill_name?: string; evidence_status: string }[];
  ai_insights: {
    version: string; relevance: number; top_terms: string[]; summary: string;
    next_steps: { kind: "learn" | "verify"; skill_id: string; skill_name: string; score_gain: number; tip: string }[];
    similar: { opportunity_id: string; title: string; employer_name?: string; similarity: number }[];
  } | null;
}
export interface Correction { correction_id: string; recommendation_id: string; student_id: string; student_name: string; reason: string; affected_field: string; source_module: string; status: string; note: string | null; created_at: string }
export interface GapRecord { gap_id: string; skill_id: string; skill_name: string; opportunity_id: string; p06_status: string | null; next_action: string; activity: { title: string } | null }
export interface Handoff { handoff_id: string; from_module: string; to_module: string; kind: string; student_id: string | null; ref: string | null; payload: Record<string, unknown>; status: string; created_at: string }
export interface People { people: Record<string, { id: string; name: string; role: string }>; advisors: { id: string; name: string }[] }

const act = (role: Role, extra: object = {}) => ({ actor_role: role, ...extra });
const post = <T,>(path: string, body: object) => request<T>(path, { method: "POST", body });
const put = <T,>(path: string, body: object) => request<T>(path, { method: "PUT", body });

// ---------- P01 profiles ----------
export interface ProfileState {
  student_id: string; profile: Profile; status: "submitted" | "clarification_requested" | "reviewed";
  review: { decision: string; comment: string | null; actor_name: string; created_at: string } | null;
  draft: (Partial<Omit<Profile, "skills">> & { skills?: string[]; updated_at: string }) | null;
}
export interface ProfileVersion { profile_version: number; source: string; created_at: string | null; profile: Profile }
export const p01 = {
  state: (sid: string) => request<ProfileState>(`/api/students/${sid}/profile`),
  versions: (sid: string) => request<ProfileVersion[]>(`/api/students/${sid}/profile-versions`),
  saveDraft: (sid: string, draft: object) => put<ProfileState>(`/api/students/${sid}/profile/draft`, act("student", draft)),
  submit: (sid: string) => post<ProfileState & { new_version: boolean }>(`/api/students/${sid}/profile/submit`, act("student")),
  review: (sid: string, decision: string, comment?: string) =>
    post<ProfileState>(`/api/students/${sid}/profile/review`, act("coordinator", { decision, comment })),
  skills: () => request<Record<string, string>>("/api/skills"),
};

// ---------- P02 / P03 listings ----------
export interface Decision { decision: string; version: number; reason: string | null; actor_name: string; created_at: string; checklist: string[] | null }
export const listings = {
  all: () => request<Listing[]>("/api/submissions"),
  queue: () => request<Listing[]>("/api/review-queue"),
  checklist: () => request<string[]>("/api/review/checklist"),
  versions: (id: string) => request<(Listing & { current: boolean; archived_at: string | null })[]>(`/api/submissions/${id}/versions`),
  decisions: (id: string) => request<Decision[]>(`/api/opportunities/${id}/decisions`),
  submit: (body: object) => post<Listing>("/api/submissions", act("employer", { hr_authorized: true, ...body })),
  resubmit: (id: string, body: object) => post<Listing>(`/api/submissions/${id}/resubmit`, act("employer", { hr_authorized: true, ...body })),
  decide: (id: string, decision: string, reason?: string, checklist?: string[]) =>
    post<Listing>(`/api/submissions/${id}/decision`, act("coordinator", { decision, reason, checklist })),
  publish: (id: string) => post<Listing>(`/api/opportunities/${id}/publish`, act("coordinator")),
  close: (id: string, reason?: string) => post<Listing>(`/api/opportunities/${id}/close`, act("coordinator", { reason })),
  open: (q = "") => request<Listing[]>("/api/opportunities", { query: { q } }),
};

// ---------- P04 applications ----------
export const p04 = {
  mine: (sid: string) => request<Application[]>(`/api/students/${sid}/applications`),
  all: () => request<Application[]>("/api/applications"),
  apply: (sid: string, oid: string, statement: string) => post<Application>("/api/applications", act("student", { student_id: sid, opportunity_id: oid, statement })),
  draft: (sid: string, oid: string, statement: string) => post<Application>("/api/applications/draft", act("student", { student_id: sid, opportunity_id: oid, statement })),
  submitDraft: (aid: string, statement: string) => post<Application>(`/api/applications/${aid}/submit`, act("student", { statement })),
  decide: (aid: string, action: string, reason?: string) => post<Application>(`/api/applications/${aid}/decisions`, act("employer", { action, reason })),
  interview: (aid: string, body: object) => post<Application>(`/api/applications/${aid}/interview`, act("employer", body)),
  completeInterview: (aid: string) => post<Application>(`/api/applications/${aid}/interview/complete`, act("employer")),
  respond: (aid: string, response: "accept" | "decline", reason?: string) => post<Application>(`/api/applications/${aid}/offer-response`, act("student", { response, reason })),
  withdraw: (aid: string, reason?: string) => post<Application>(`/api/applications/${aid}/withdraw`, act("student", { reason })),
  confirm: (aid: string) => post<{ placement_id: string; already_confirmed: boolean }>(`/api/applications/${aid}/confirm-placement`, act("coordinator")),
  statementDraft: (sid: string, oid: string) => post<{ statement: string }>("/api/ai/statement-draft", { student_id: sid, opportunity_id: oid }),
};

// ---------- P05 matching ----------
export const p05 = {
  latest: (sid: string) => request<Recommendation[]>(`/api/students/${sid}/recommendations`),
  run: (sid: string) => post<Recommendation[]>(`/api/students/${sid}/recommendations`, {}),
  runs: (sid: string) => request<{ run_id: string; created_at: string; profile_version: number; results: number; eligible: number }[]>(`/api/students/${sid}/recommendation-runs`),
  prepare: (recId: string, skillId: string) => post<GapRecord>(`/api/recommendations/${recId}/gaps/${skillId}/handoff`, act("student")),
  flag: (recId: string, reason: string, affected_field: string) => post<Correction>(`/api/recommendations/${recId}/flags`, act("student", { reason, affected_field })),
  corrections: () => request<Correction[]>("/api/corrections"),
  record: (cid: string, note: string) => post<Correction>(`/api/corrections/${cid}/record`, act("coordinator", { note })),
};

// ---------- P06 preparation ----------
export interface Module { module_id: string; skill_id: string; status: "full" | "outline"; title: string; outcome: string; minutes: number; resource: { title: string; minutes: number; parts: { heading: string; text: string }[] } | null; task: string; checklist: string[] }
export interface ChainStep { key: string; label: string; detail: string; reached: boolean; current: boolean; blocked: boolean }
export interface PrepGap { gap_id: string; student_id: string; skill_id: string; skill_name: string; module_id: string; module_title: string; module_status: string; source: string; reason: string; opportunity_id: string | null; status: "open" | "closed"; created_at: string; skill_status: string; skill_status_label: string; chain: ChainStep[]; display_name?: string }
export interface Submission { evidence_id: string; student_id: string; skill_id: string; module_id: string; status: string; status_label: string; versions: { v: number; at: string; explanation: string; board: Board }[]; reviews: { at: string; by: string; decision: string; comment: string; checklist: boolean[] }[]; display_name?: string; module?: Module }
export interface Board { items: { key: string; summary: string; assignee: string; status: "todo" | "inprogress" | "done" }[]; log: { key: string; from: string; to: string; reason: string; at: string }[]; people?: string[] }
export interface Plan { student_id: string; display_name: string; today: string; gaps: PrepGap[]; next_step: { kind: string; text: string; module_id?: string }; resources: Record<string, string>; submissions: Submission[] }
export const p06 = {
  modules: () => request<Module[]>("/api/p06/modules"),
  plan: (sid: string) => request<Plan>(`/api/p06/students/${sid}/plan`),
  board: (sid: string) => request<Board>(`/api/p06/students/${sid}/board`),
  gaps: () => request<PrepGap[]>("/api/p06/gaps"),
  queue: () => request<Submission[]>("/api/p06/review-queue"),
  addGap: (sid: string, skill_id: string, reason: string, opportunity_id?: string) => post(`/api/p06/students/${sid}/gaps`, act("coordinator", { skill_id, reason, opportunity_id })),
  completeResource: (sid: string, mid: string) => post(`/api/p06/students/${sid}/resources/${mid}/complete`, act("student")),
  addItem: (sid: string, summary: string) => post<Board>(`/api/p06/students/${sid}/board/items`, act("student", { summary })),
  assign: (sid: string, key: string, assignee: string) => put<Board>(`/api/p06/students/${sid}/board/items/${key}/assignee`, act("student", { assignee })),
  move: (sid: string, key: string, to: string, reason: string) => post<Board>(`/api/p06/students/${sid}/board/items/${key}/move`, act("student", { to, reason })),
  submit: (sid: string, module_id: string, explanation: string) => post<Submission>(`/api/p06/students/${sid}/submissions`, act("student", { module_id, explanation })),
  review: (ev: string, decision: string, checklist: boolean[], comment?: string) =>
    post<Submission & { p01_profile_version: number | null }>(`/api/p06/submissions/${ev}/review`, act("reviewer", { decision, checklist, comment })),
};

// ---------- P07 progress ----------
export interface Goal { goal_id: string; text: string; outcomes: string[] }
export interface LogEntry { log_id: string; week: number; date: string; goal_id: string | null; status: string; period: string; versions: { v: number; at: string; text: string; evidence: string[] }[]; feedback: { at: string; by: string; type: string; text: string }[] }
export interface ActionItem { action_id: string; text: string; owner: string; due: string; status: string; closure: string; closed_at: string | null; created_by: string; overdue: boolean }
export interface P07Record {
  student_id: string; display_name: string; today: string; outcomes: { outcome_id: string; name: string }[];
  advisors: { id: string; name: string }[];
  readiness: { demonstrated: { skill_id: string; evidence_id: string; review_date: string }[]; in_progress: string[] };
  placement: null | { placement_id: string; employer_name: string; role: string; location: string; period_start: string; period_end: string; supervisor_name: string | null; supervisor_contact?: string | null; academic_advisor: string | null; confirmed_by: string | null; received_at: string; opportunity_id: string; application_id: string | null };
  period?: { label: string; start: string; end: string };
  agreement?: { goals: Goal[]; status: string; signoffs: Record<"student" | "supervisor" | "advisor", string | null> };
  logs?: LogEntry[];
  evidence?: { evidence_id: string; title: string; date: string; source: string; in_period: boolean }[];
  judgements?: { outcome_id: string; name: string; level: string; evidence: string[]; by: string | null; at: string | null; evidence_missing: boolean }[];
  milestones?: { milestone_id: string; text: string; done: boolean; done_at: string | null }[];
  actions?: ActionItem[];
  final?: { employer: { by: string; at: string; text: string; would_host: string } | null; advisor: { by: string; at: string; outcomes: Record<string, string>; summary: string; next_goal: string } | null };
  counts?: { logs_awaiting_supervisor: number; overdue_actions: number };
}
export const p07 = {
  record: (sid: string, role: Role) => request<P07Record>(`/api/p07/students/${sid}`, { query: { viewer_role: role } }),
  assignAdvisor: (pid: string, advisor: string) => post(`/api/p07/placements/${pid}/advisor`, act("coordinator", { advisor })),
  addGoal: (pid: string, text: string, outcomes: string[]) => post(`/api/p07/placements/${pid}/agreement/goals`, act("student", { text, outcomes })),
  removeGoal: (pid: string, gid: string) => post(`/api/p07/placements/${pid}/agreement/goals/${gid}/remove`, act("student")),
  sign: (pid: string, role: Role) => post(`/api/p07/placements/${pid}/agreement/sign`, act(role)),
  addLog: (pid: string, body: { text: string; goal_id?: string; evidence_ids?: string[]; new_evidence_title?: string }) => post(`/api/p07/placements/${pid}/logs`, act("student", body)),
  revise: (lid: string, text: string) => post(`/api/p07/logs/${lid}/revise`, act("student", { text })),
  acknowledge: (lid: string) => post(`/api/p07/logs/${lid}/acknowledge`, act("supervisor")),
  requestDetail: (lid: string, text: string) => post(`/api/p07/logs/${lid}/request-detail`, act("supervisor", { text })),
  addMilestone: (pid: string, text: string) => post(`/api/p07/placements/${pid}/milestones`, act("supervisor", { text })),
  setMilestone: (mid: string, done: boolean) => put(`/api/p07/milestones/${mid}`, act("supervisor", { done })),
  judge: (pid: string, lo: string, level: string, evidence_ids: string[]) => put(`/api/p07/placements/${pid}/judgements/${lo}`, act("advisor", { level, evidence_ids })),
  addAction: (pid: string, text: string, owner: string, due: string) => post(`/api/p07/placements/${pid}/actions`, act("advisor", { text, owner, due })),
  closeAction: (aid: string, role: Role, closure: string) => post(`/api/p07/actions/${aid}/close`, act(role, { closure })),
  employerFeedback: (pid: string, text: string, would_host: string) => post(`/api/p07/placements/${pid}/employer-feedback`, act("supervisor", { text, would_host })),
  finalReview: (pid: string, outcomes: Record<string, string>, summary: string, next_goal: string) => post(`/api/p07/placements/${pid}/final-review`, act("advisor", { outcomes, summary, next_goal })),
};

// ---------- Assistant (coordinator side) and records ----------
export interface AssistantQuestion { question_id: string; question: string; asked_by_role: string; student_id: string | null; reason: string; count: number; last_asked_at: string; status: string; reply: string | null; replied_by: string | null }
export interface AssistantEntry { faq_id: string; topic: string; question: string; answer: string; status: string; created_by: string; approved_by: string | null; source?: string; team?: string }
export const assistant = {
  status: () => request<{ mode: string; model: string | null; approved_entries: number; note: string }>("/api/assistant/status"),
  faq: () => request<AssistantEntry[]>("/api/assistant/faq"),
  questions: (status = "") => request<AssistantQuestion[]>("/api/assistant/questions", { query: { status } }),
  entries: (status = "") => request<AssistantEntry[]>("/api/assistant/entries", { query: { status } }),
  reply: (qid: string, reply: string) => post(`/api/assistant/questions/${qid}/reply`, act("coordinator", { reply })),
  dismiss: (qid: string) => post(`/api/assistant/questions/${qid}/dismiss`, act("coordinator")),
  addEntry: (body: { topic: string; question: string; answer: string; question_id?: string }) => post<AssistantEntry>("/api/assistant/entries", act("coordinator", body)),
  approve: (id: string) => post(`/api/assistant/entries/${id}/approve`, act("coordinator")),
  discard: (id: string) => post(`/api/assistant/entries/${id}/discard`, act("coordinator")),
};
export const records = {
  handoffs: () => request<Handoff[]>("/api/handoffs"),
  events: (limit = 200) => request<{ id: string; at: string; module: string; actor_name: string; actor_role: string; action: string; ref: string; text: string }[]>("/api/events", { query: { limit } }),
  people: () => request<People>("/api/people"),
};
