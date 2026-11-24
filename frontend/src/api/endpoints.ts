import { request } from "./client";
import type {
  ActivityEvent,
  AssistantAnswer,
  DemoSettings,
  HomeQuery,
  Journey,
  NavCounts,
  Scenario,
  StudentSummary,
  Todo,
} from "./types";

/** One function per backend endpoint. Keep paths in sync with backend routers. */
export const api = {
  students: () => request<StudentSummary[]>("/api/students"),
  demoSettings: () => request<DemoSettings>("/api/demo/settings"),
  setToday: (today: string) => request<DemoSettings>("/api/demo/today", { method: "PUT", body: { today } }),
  resetScenario: (scenario: Scenario) =>
    request<DemoSettings>("/api/demo/reset", { method: "POST", query: { scenario } }),
  journey: (studentId: string) => request<Journey>(`/api/home/journey/${encodeURIComponent(studentId)}`),
  todos: (q: HomeQuery) => request<Todo[]>("/api/home/todos", { query: { ...q } }),
  navCounts: (q: HomeQuery) => request<NavCounts>("/api/home/counts", { query: { ...q } }),
  events: (opts: { limit?: number; student_id?: string } = {}) =>
    request<ActivityEvent[]>("/api/events", { query: opts }),
  askAssistant: (question: string, role: string) =>
    request<AssistantAnswer>("/api/assistant/ask", { method: "POST", body: { question, role } }),
};
