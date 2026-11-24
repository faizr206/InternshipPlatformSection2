/**
 * Shared API types for the unified Coop Platform.
 * These mirror the FastAPI response models; once the backend exposes its
 * OpenAPI schema they can be regenerated with `openapi-typescript`.
 */

export type Role = "student" | "employer" | "coordinator" | "reviewer" | "supervisor" | "advisor";
export type Scenario = "fresh" | "reviewed" | "midpoint" | "end";
/** Owning team module for a page, record or event. */
export type Owner = "P01" | "P02" | "P03" | "P04" | "P05" | "P06" | "P07" | "Core";

export interface StudentSummary {
  student_id: string;
  display_name: string;
  programme: string;
  interests: string[];
  profile_version: number;
}

export interface DemoSettings {
  today: string; // ISO date
  scenario: Scenario;
}

export type StageStatus = "done" | "current" | "upcoming" | "blocked";

export interface JourneyStage {
  owner: Exclude<Owner, "Core">;
  label: string;
  status: StageStatus;
  detail: string;
  ref?: string | null;
}

export interface Journey {
  student_id: string;
  display_name: string;
  stages: JourneyStage[];
}

export type TodoPriority = "high" | "normal" | "low";

export interface Todo {
  id: string;
  title: string;
  detail: string;
  owner: Owner;
  /** Route in the SPA that resolves this task. */
  href: string;
  priority: TodoPriority;
  due?: string | null;
  count?: number;
}

export interface ActivityEvent {
  id: string;
  at: string; // ISO datetime
  actor: string;
  role: Role | "system";
  action: string;
  ref?: string | null;
  owner: Owner;
  student_id?: string | null;
}

/** Sidebar badge counts, keyed by nav item key. */
export type NavCounts = Partial<Record<NavKey, number>>;

export type NavKey =
  | "home"
  | "profile"
  | "opportunities"
  | "applications"
  | "matching"
  | "preparation"
  | "placement"
  | "assistant"
  | "records";

export interface AssistantAnswer {
  answer: string;
  source: string | null;
  mode: "retrieval" | "llm";
  confident: boolean;
}

export interface HomeQuery {
  role: Role;
  student_id: string;
}
