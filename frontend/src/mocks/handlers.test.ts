import { describe, expect, it } from "vitest";
import { mockFetch } from "./handlers";

const get = async (p: string, init?: RequestInit) => {
  const r = await mockFetch(p, init);
  return { status: r.status, body: await r.json() };
};

describe("mock API", () => {
  it("uses the latest submitted profile per student", async () => {
    const { body } = await get("/api/students");
    expect(body).toHaveLength(4);
    expect(body.find((s: { student_id: string }) => s.student_id === "COOP-B001").profile_version).toBe(2);
  });

  it("moves the journey forward when the scenario changes", async () => {
    const before = await get("/api/home/journey/COOP-B001");
    expect(before.body.stages.find((s: { owner: string }) => s.owner === "P07").status).toBe("upcoming");
    const reset = await get("/api/demo/reset?scenario=midpoint", { method: "POST" });
    expect(reset.body).toEqual({ scenario: "midpoint", today: "2027-03-18" });
    const after = await get("/api/home/journey/COOP-B001");
    expect(after.body.stages.find((s: { owner: string }) => s.owner === "P07").status).toBe("current");
  });

  it("rejects unknown scenarios and roles", async () => {
    expect((await get("/api/demo/reset?scenario=nope", { method: "POST" })).status).toBe(422);
    expect((await get("/api/home/todos?role=hacker&student_id=COOP-B001")).status).toBe(422);
  });

  it("flags Noor's incomplete profile instead of guessing", async () => {
    const { body } = await get("/api/home/journey/COOP-B004");
    expect(body.stages[0]).toMatchObject({ owner: "P01", status: "blocked" });
  });
});
