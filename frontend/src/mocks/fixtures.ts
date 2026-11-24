/**
 * In-memory demo fixtures used while VITE_USE_MOCKS is on.
 * Students and listings come from the P01–P03 sample file; journeys, to-dos and
 * events are derived per demo scenario (dates follow the P06/P07 presets).
 * Everything here is SYNTHETIC.
 */
import sample from "./ipp_sample_data.json";
import type {
  ActivityEvent,
  JourneyStage,
  NavCounts,
  Role,
  Scenario,
  StudentSummary,
  Todo,
} from "@/api/types";

export const SCENARIO_DATES: Record<Scenario, string> = {
  fresh: "2026-11-23",
  reviewed: "2026-11-28",
  midpoint: "2027-03-18",
  end: "2027-06-04",
};

const PROGRAMMES: Record<string, string> = {
  "COOP-B001": "BSc Business Analytics",
  "COOP-B002": "BSc Data Science",
  "COOP-B003": "BA Design & Innovation",
  "COOP-B004": "BBA General Management",
};

/** Latest submitted profile per student (rule: ignore drafts, take highest version). */
export const students: StudentSummary[] = Object.values(
  sample.student_profiles
    .filter((p) => p.profile_status === "submitted")
    .reduce<Record<string, (typeof sample.student_profiles)[number]>>((acc, p) => {
      const cur = acc[p.student_id];
      if (!cur || p.profile_version > cur.profile_version) acc[p.student_id] = p;
      return acc;
    }, {}),
).map((p) => ({
  student_id: p.student_id,
  display_name: p.display_name,
  programme: PROGRAMMES[p.student_id] ?? "BUS2010 Internship Practicum",
  interests: p.interests,
  profile_version: p.profile_version,
}));

export const listings = sample.published_listings;
export const openListings = listings.filter(
  (l) => l.publication_status === "published" && l.listing_status === "open",
);

type Stage = Omit<JourneyStage, "status" | "detail"> & { status?: JourneyStage["status"]; detail?: string };
const S = (owner: JourneyStage["owner"], label: string): Stage => ({ owner, label });

/** Journey order: profile → listing → review → match → apply → prepare → co-op. */
const BASE: Stage[] = [
  S("P01", "Profile"),
  S("P02", "Opportunity submitted"),
  S("P03", "Reviewed & published"),
  S("P05", "Matched"),
  S("P04", "Applied & placed"),
  S("P06", "Prepared"),
  S("P07", "Co-op placement"),
];

function stages(list: [JourneyStage["status"], string, string?][]): JourneyStage[] {
  return BASE.map((b, i) => ({ ...b, status: list[i][0], detail: list[i][1], ref: list[i][2] ?? null }));
}

export function journeyFor(studentId: string, scenario: Scenario): JourneyStage[] {
  const step = ["fresh", "reviewed", "midpoint", "end"].indexOf(scenario);
  switch (studentId) {
    case "COOP-B001":
      return stages([
        ["done", step >= 1 ? "Profile v3 · Jira now reviewed" : "Profile v2 · SQL reviewed", "PRF-B001"],
        ["done", "Emirates Group · Aviation Analytics", "OP-028"],
        ["done", "Approved and published v2", "OP-028"],
        step === 0
          ? ["current", "3 matches · Jira gap found", "REC-7F3A2C91"]
          : ["done", "Re-matched · gap closed", "REC-7F3A2C91"],
        step === 0
          ? ["upcoming", "Apply once matched"]
          : step === 1
            ? ["current", "Offer accepted · awaiting confirmation", "APP-0028"]
            : ["done", "Placement confirmed", "PL-0001"],
        step === 0
          ? ["blocked", "Jira gap open · module not started", "GAP-0001"]
          : ["done", "Jira demonstrated (MOD-JIRA-101)", "GAP-0001"],
        step < 2
          ? ["upcoming", "Starts 1 Feb 2027"]
          : step === 2
            ? ["current", "Week 7 · midpoint review due", "PL-0001"]
            : ["done", "Final review submitted", "PL-0001"],
      ]);
    case "COOP-B002":
      return stages([
        ["done", "Profile v1 · Python reviewed", "PRF-B002"],
        ["done", "Desert Grid Energy · Energy Data", "OP-031"],
        ["done", "Published v1", "OP-031"],
        step === 0 ? ["current", "2 matches · ready to review"] : ["done", "OP-031 strong match"],
        step === 0 ? ["upcoming", "—"] : step === 1 ? ["current", "Application submitted", "APP-0031"] : ["done", "Placement confirmed", "PL-0002"],
        step < 2 ? ["upcoming", "No gaps reported"] : ["done", "No preparation needed"],
        step < 2 ? ["upcoming", "Starts 1 Feb 2027"] : step === 2 ? ["current", "Week 7 · on track", "PL-0002"] : ["current", "Final review pending", "PL-0002"],
      ]);
    case "COOP-B003":
      return stages([
        ["done", "Profile v1 · Communication reviewed", "PRF-B003"],
        ["done", "Oasis Ventures · Product Design", "OP-034"],
        ["done", "Published v1", "OP-034"],
        ["done", "OP-034 best match"],
        step === 0 ? ["current", "Application submitted", "APP-0034"] : step === 1 ? ["current", "Interview scheduled", "APP-0034"] : ["done", "Placement confirmed", "PL-0003"],
        step === 0 ? ["current", "Figma evidence in progress"] : ["done", "Figma demonstrated"],
        step < 2 ? ["upcoming", "Starts 15 Jan 2027"] : step === 2 ? ["current", "Logbook week 9 overdue", "PL-0003"] : ["done", "Final review submitted", "PL-0003"],
      ]);
    default:
      return stages([
        ["blocked", "Missing interests and availability", "PRF-B004"],
        ["done", "Listings available"],
        ["done", "3 open listings"],
        ["blocked", "Matching needs a complete profile"],
        ["upcoming", "—"],
        ["upcoming", "—"],
        ["upcoming", "—"],
      ]);
  }
}

const T = (t: Todo) => t;

export function todosFor(role: Role, studentId: string, scenario: Scenario): Todo[] {
  const name = students.find((s) => s.student_id === studentId)?.display_name.split(" ")[0] ?? "Student";
  const step = ["fresh", "reviewed", "midpoint", "end"].indexOf(scenario);
  const isLayla = studentId === "COOP-B001";
  switch (role) {
    case "student":
      if (studentId === "COOP-B004")
        return [
          T({ id: "t-s1", title: "Add your interests and availability", detail: "Matching can't run until your profile says when you're free and what you like.", owner: "P01", href: "/profile", priority: "high" }),
          T({ id: "t-s2", title: "Ask the assistant about placements abroad", detail: "Approved FAQ answers from the coordinator.", owner: "P03", href: "/assistant", priority: "low" }),
        ];
      if (step === 0)
        return [
          T({ id: "t-s1", title: "Review your recommendations", detail: isLayla ? "OP-028 fits you, but Jira is a gap." : "New matches are ready.", owner: "P05", href: "/matching", priority: "high", count: 3 }),
          ...(isLayla ? [T({ id: "t-s2", title: "Start the Jira module (MOD-JIRA-101)", detail: "Close the gap before you apply to OP-028.", owner: "P06", href: "/preparation", priority: "normal", due: "2026-12-05" })] : []),
          T({ id: "t-s3", title: "Browse open opportunities", detail: `${openListings.length} listings are published and open.`, owner: "P03", href: "/opportunities", priority: "low" }),
        ];
      if (step === 1)
        return [
          T({ id: "t-s1", title: "Wait for coordinator confirmation", detail: "Your accepted offer for OP-028 is with the coordinator.", owner: "P04", href: "/applications", priority: "normal" }),
          T({ id: "t-s2", title: "Draft learning agreement goals", detail: "Three goals, signed by you, your supervisor and advisor.", owner: "P07", href: "/placement", priority: "normal", due: "2027-01-25" }),
        ];
      if (step === 2)
        return [
          T({ id: "t-s1", title: "Submit logbook for week 7", detail: "Due Friday. Your supervisor acknowledges it.", owner: "P07", href: "/placement", priority: "high", due: "2027-03-19" }),
          T({ id: "t-s2", title: "Prepare for midpoint review", detail: "Bring evidence for each learning outcome.", owner: "P07", href: "/placement", priority: "normal", due: "2027-03-25" }),
        ];
      return [T({ id: "t-s1", title: "Read your final review", detail: "Outcomes and advisor feedback are ready.", owner: "P07", href: "/placement", priority: "normal" })];

    case "employer":
      return [
        T({ id: "t-e1", title: "Submit a new opportunity", detail: "HR authorisation is required before review.", owner: "P02", href: "/opportunities", priority: "normal" }),
        T({ id: "t-e2", title: step === 0 ? "Fix and resubmit OP-039" : "Review applicants for OP-028", detail: step === 0 ? "Returned: start and end dates are missing." : "2 applicants shortlisted by the coordinator.", owner: step === 0 ? "P02" : "P04", href: step === 0 ? "/opportunities" : "/applications", priority: "high", count: step === 0 ? undefined : 2 }),
        ...(step >= 2 ? [T({ id: "t-e3", title: "Give midpoint feedback", detail: `${name}'s supervisor feedback form.`, owner: "P07" as const, href: "/placement", priority: "normal" as const, due: "2027-03-25" })] : []),
      ];

    case "coordinator":
      return [
        ...(step <= 1 ? [T({ id: "t-c1", title: "Review employer submissions", detail: "Check against the 7-point review checklist.", owner: "P03", href: "/opportunities", priority: "high", count: 2 })] : []),
        T({ id: "t-c2", title: step === 1 ? "Confirm placement PL-0001" : step === 0 ? "Shortlist applications" : "Follow up overdue logbooks", detail: step === 1 ? "Layla accepted the Emirates Group offer." : step === 0 ? "4 new applications this week." : "Mei Chen · week 9 logbook overdue.", owner: step >= 2 ? "P07" : "P04", href: step >= 2 ? "/placement" : "/applications", priority: step === 1 ? "high" : "normal", count: step === 1 ? 1 : undefined }),
        T({ id: "t-c3", title: "Request clarification from Noor", detail: "Profile has no interests or availability.", owner: "P01", href: "/profile", priority: "normal" }),
        T({ id: "t-c4", title: "Answer an unanswered question", detail: "“Can I split my placement over two employers?”", owner: "P03", href: "/assistant", priority: "low", count: 1 }),
      ];

    case "reviewer":
      return step === 0
        ? [
            T({ id: "t-r1", title: "No evidence waiting yet", detail: "Layla's Jira evidence arrives once she finishes MOD-JIRA-101.", owner: "P06", href: "/preparation", priority: "low" }),
            T({ id: "t-r2", title: "Spot-check self-declared skills", detail: "6 skills across 4 profiles are still self-declared.", owner: "P01", href: "/profile", priority: "normal", count: 6 }),
          ]
        : [
            T({ id: "t-r1", title: step === 1 ? "Evidence reviewed" : "Review outcome evidence", detail: step === 1 ? "Jira marked demonstrated; profile v3 created." : `${name} added evidence for 2 outcomes.`, owner: step === 1 ? "P06" : "P07", href: step === 1 ? "/preparation" : "/placement", priority: step === 1 ? "low" : "high", count: step === 1 ? undefined : 2 }),
          ];

    case "supervisor":
      return step < 2
        ? [T({ id: "t-p1", title: "Sign the learning agreement", detail: `${name}'s goals are drafted and waiting for you.`, owner: "P07", href: "/placement", priority: step === 1 ? "high" : "low" })]
        : [
            T({ id: "t-p1", title: "Acknowledge logbook week 6", detail: `${name} submitted on time.`, owner: "P07", href: "/placement", priority: "high", count: 1 }),
            T({ id: "t-p2", title: "Close action: dashboard handover", detail: "Owner: you · due in 3 days.", owner: "P07", href: "/placement", priority: "normal", due: "2027-03-21" }),
          ];

    case "advisor":
      return [
        T({ id: "t-a1", title: step < 2 ? "Accept advisor assignment" : step === 2 ? "Run midpoint review" : "Write final review", detail: step < 2 ? `Assigned to ${name} for PL-0001.` : step === 2 ? "Check outcomes against evidence." : "No “achieved” without in-period or P06 evidence.", owner: "P07", href: "/placement", priority: "high" }),
        T({ id: "t-a2", title: "Check readiness summary", detail: "P06 preparation status feeds into P07 progress.", owner: "P06", href: "/preparation", priority: "low" }),
      ];
  }
}

export function countsFor(role: Role, studentId: string, scenario: Scenario): NavCounts {
  const todos = todosFor(role, studentId, scenario);
  const byHref = (h: string) => todos.filter((t) => t.href === h).reduce((n, t) => n + (t.count ?? 1), 0);
  return {
    home: todos.filter((t) => t.priority === "high").length,
    profile: byHref("/profile"),
    opportunities: role === "student" ? openListings.length : byHref("/opportunities"),
    applications: byHref("/applications"),
    matching: byHref("/matching"),
    preparation: byHref("/preparation"),
    placement: byHref("/placement"),
    assistant: byHref("/assistant"),
  };
}

type E = Omit<ActivityEvent, "id">;
const ALL_EVENTS: (E & { scenario: Scenario })[] = [
  { scenario: "fresh", at: "2026-11-10T09:12:00", actor: "Maya", role: "reviewer", action: "reviewed SQL evidence for Layla", ref: "E-SQL-01", owner: "P01", student_id: "COOP-B001" },
  { scenario: "fresh", at: "2026-11-11T10:30:00", actor: "Layla Hassan", role: "student", action: "submitted profile v2", ref: "PRF-B001", owner: "P01", student_id: "COOP-B001" },
  { scenario: "fresh", at: "2026-11-14T13:05:00", actor: "Emirates Group", role: "employer", action: "resubmitted Aviation Analytics Intern", ref: "OP-028 v2", owner: "P02" },
  { scenario: "fresh", at: "2026-11-17T08:40:00", actor: "Dr. Salma (coordinator)", role: "coordinator", action: "approved and published", ref: "OP-028", owner: "P03" },
  { scenario: "fresh", at: "2026-11-18T11:22:00", actor: "Gulf Health Data Office", role: "employer", action: "submitted Health Data Intern", ref: "OP-039", owner: "P02" },
  { scenario: "fresh", at: "2026-11-20T15:10:00", actor: "Dr. Salma (coordinator)", role: "coordinator", action: "closed listing (filled)", ref: "OP-036", owner: "P03" },
  { scenario: "fresh", at: "2026-11-23T09:00:00", actor: "Matching engine", role: "system", action: "recommended 3 listings to Layla · Jira gap", ref: "REC-7F3A2C91", owner: "P05", student_id: "COOP-B001" },
  { scenario: "fresh", at: "2026-11-23T09:01:00", actor: "Matching engine", role: "system", action: "sent skill gap to preparation", ref: "GAP-0001", owner: "P05", student_id: "COOP-B001" },
  { scenario: "reviewed", at: "2026-11-24T10:15:00", actor: "Layla Hassan", role: "student", action: "applied to Aviation Analytics Intern", ref: "APP-0028", owner: "P04", student_id: "COOP-B001" },
  { scenario: "reviewed", at: "2026-11-25T16:45:00", actor: "Layla Hassan", role: "student", action: "submitted Jira evidence (212 words)", ref: "MOD-JIRA-101", owner: "P06", student_id: "COOP-B001" },
  { scenario: "reviewed", at: "2026-11-26T09:30:00", actor: "Maya", role: "reviewer", action: "requested a revision on Jira evidence", ref: "MOD-JIRA-101", owner: "P06", student_id: "COOP-B001" },
  { scenario: "reviewed", at: "2026-11-27T14:00:00", actor: "Maya", role: "reviewer", action: "marked Jira demonstrated → profile v3", ref: "GAP-0001", owner: "P06", student_id: "COOP-B001" },
  { scenario: "reviewed", at: "2026-11-27T14:01:00", actor: "Matching engine", role: "system", action: "re-ran matching · gap closed", ref: "REC-7F3A2C91", owner: "P05", student_id: "COOP-B001" },
  { scenario: "reviewed", at: "2026-11-28T11:20:00", actor: "Layla Hassan", role: "student", action: "accepted offer from Emirates Group", ref: "APP-0028", owner: "P04", student_id: "COOP-B001" },
  { scenario: "midpoint", at: "2026-12-02T10:00:00", actor: "Dr. Salma (coordinator)", role: "coordinator", action: "confirmed placement", ref: "PL-0001", owner: "P04", student_id: "COOP-B001" },
  { scenario: "midpoint", at: "2027-01-28T12:00:00", actor: "R. Khan (supervisor)", role: "supervisor", action: "signed learning agreement", ref: "PL-0001", owner: "P07", student_id: "COOP-B001" },
  { scenario: "midpoint", at: "2027-03-12T17:30:00", actor: "Layla Hassan", role: "student", action: "submitted logbook week 6", ref: "PL-0001", owner: "P07", student_id: "COOP-B001" },
  { scenario: "midpoint", at: "2027-03-15T09:00:00", actor: "System", role: "system", action: "flagged Mei's week 9 logbook overdue", ref: "PL-0003", owner: "P07", student_id: "COOP-B003" },
  { scenario: "end", at: "2027-05-30T15:00:00", actor: "R. Khan (supervisor)", role: "supervisor", action: "submitted employer feedback", ref: "PL-0001", owner: "P07", student_id: "COOP-B001" },
  { scenario: "end", at: "2027-06-03T10:30:00", actor: "Dr. Omar (advisor)", role: "advisor", action: "submitted final review · 4/5 outcomes achieved", ref: "PL-0001", owner: "P07", student_id: "COOP-B001" },
];

export function eventsFor(scenario: Scenario, studentId?: string, limit = 12): ActivityEvent[] {
  const order: Scenario[] = ["fresh", "reviewed", "midpoint", "end"];
  const upto = order.indexOf(scenario);
  return ALL_EVENTS.filter((e) => order.indexOf(e.scenario) <= upto)
    .filter((e) => !studentId || e.student_id === studentId)
    .map(({ scenario: _s, ...e }, i) => ({ id: `EV-${String(i + 1).padStart(4, "0")}`, ...e }))
    .sort((a, b) => b.at.localeCompare(a.at))
    .slice(0, limit);
}

export const FAQ = [
  { section: "Placements", q: "Are placements on site?", a: "Yes. Placements are on site; remote roles are not approved." },
  { section: "Placements", q: "Can I work abroad?", a: "It is difficult to approve. Exceptions are reviewed case by case by the coordinator." },
  { section: "Grading", q: "Who enters my final grade?", a: "The faculty member assigned to your internship." },
  { section: "Employer submissions", q: "What must an employer include?", a: "Title, dates, location, work mode, a named supervisor, required skills, and the learning opportunities." },
  { section: "Review", q: "How is an opportunity approved?", a: "The coordinator checks it against a review checklist: completeness, on-site, duration, supervisor, learning value, employer reliability, and workplace safety." },
  { section: "Review", q: "Why was my opportunity returned?", a: "The reason is shown on its status. Fix the issue and resubmit." },
  { section: "Review", q: "How do I resubmit?", a: "Submit a new version. The old version is kept and never overwritten." },
  { section: "Students", q: "Does applying mean I got the placement?", a: "No. Applying only shows interest. Placements need coordinator approval." },
];
