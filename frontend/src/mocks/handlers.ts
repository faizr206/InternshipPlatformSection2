/**
 * A tiny in-memory stand-in for the FastAPI backend. `mockFetch` has the same
 * shape as `fetch`, so the API client doesn't care which one it talks to.
 */
import type { DemoSettings, Role, Scenario } from "@/api/types";
import { FAQ, SCENARIO_DATES, countsFor, eventsFor, journeyFor, students, todosFor } from "./fixtures";

const SCENARIOS: Scenario[] = ["fresh", "reviewed", "midpoint", "end"];
const ROLES: Role[] = ["student", "employer", "coordinator", "reviewer", "supervisor", "advisor"];

const state: DemoSettings = { scenario: "fresh", today: SCENARIO_DATES.fresh };

/** Reset mock state (tests). */
export function resetMockState() {
  state.scenario = "fresh";
  state.today = SCENARIO_DATES.fresh;
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const notFound = (detail = "Not found") => json({ detail }, 404);

const STOP = new Set(["the", "a", "an", "is", "are", "do", "i", "my", "can", "how", "what", "who", "why", "to", "of", "in"]);
const words = (s: string) =>
  s.toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/).filter((w) => w.length > 1 && !STOP.has(w));

function answer(question: string) {
  const q = new Set(words(question));
  let best = { score: 0, i: -1 };
  FAQ.forEach((f, i) => {
    const score = words(f.q + " " + f.section).filter((w) => q.has(w)).length;
    if (score > best.score) best = { score, i };
  });
  if (best.i < 0)
    return {
      answer: "I don't have an approved answer for that yet. I've noted it for the coordinator.",
      source: null,
      mode: "retrieval" as const,
      confident: false,
    };
  const f = FAQ[best.i];
  return { answer: f.a, source: `FAQ · ${f.section}: “${f.q}”`, mode: "retrieval" as const, confident: best.score >= 2 };
}

export async function mockFetch(input: string, init: RequestInit = {}): Promise<Response> {
  // Small delay so loading states are visible in dev, none in tests.
  if (import.meta.env.MODE !== "test") await new Promise((r) => setTimeout(r, 120));
  const url = new URL(input, "http://mock.local");
  const method = (init.method ?? "GET").toUpperCase();
  const path = url.pathname;
  const qp = url.searchParams;
  const body = init.body ? JSON.parse(String(init.body)) : undefined;

  const role = (qp.get("role") ?? "student") as Role;
  const sid = qp.get("student_id") ?? "COOP-B001";
  if (qp.has("role") && !ROLES.includes(role)) return json({ detail: `Unknown role ${role}` }, 422);

  if (method === "GET" && path === "/api/students") return json(students);
  if (method === "GET" && path === "/api/demo/settings") return json(state);
  if (method === "PUT" && path === "/api/demo/today") {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(body?.today ?? "")) return json({ detail: "today must be YYYY-MM-DD" }, 422);
    state.today = body.today;
    return json(state);
  }
  if (method === "POST" && path === "/api/demo/reset") {
    const s = qp.get("scenario") as Scenario;
    if (!SCENARIOS.includes(s)) return json({ detail: "Unknown scenario" }, 422);
    state.scenario = s;
    state.today = SCENARIO_DATES[s];
    return json(state);
  }
  const jm = path.match(/^\/api\/home\/journey\/([^/]+)$/);
  if (method === "GET" && jm) {
    const st = students.find((s) => s.student_id === decodeURIComponent(jm[1]));
    if (!st) return notFound("Unknown student");
    return json({ student_id: st.student_id, display_name: st.display_name, stages: journeyFor(st.student_id, state.scenario) });
  }
  if (method === "GET" && path === "/api/home/todos") return json(todosFor(role, sid, state.scenario));
  if (method === "GET" && path === "/api/home/counts") return json(countsFor(role, sid, state.scenario));
  if (method === "GET" && path === "/api/events")
    return json(eventsFor(state.scenario, qp.get("student_id") ?? undefined, Number(qp.get("limit") ?? 12)));
  if (method === "POST" && path === "/api/assistant/ask") {
    if (!body?.question?.trim()) return json({ detail: "question is required" }, 422);
    return json(answer(body.question));
  }
  return notFound(`No mock for ${method} ${path}`);
}
