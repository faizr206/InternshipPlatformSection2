import {
  Bot,
  BriefcaseBusiness,
  ClipboardList,
  GraduationCap,
  House,
  Building2,
  ScrollText,
  Sparkles,
  UserRound,
  type LucideIcon,
} from "lucide-react";
import type { NavKey, Role } from "@/api/types";

export interface NavItem {
  key: NavKey;
  path: string;
  label: string;
  /** Owner chip shown on the page header, e.g. "P03" or "P02 · P03 · P04". */
  owner: string;
  icon: LucideIcon;
  roles: Role[] | "all";
  summary: string;
  /** What the finished module will let people do (shown in empty state). */
  plans: string[];
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

const ALL = "all" as const;

export const NAV: NavGroup[] = [
  {
    label: "Overview",
    items: [
      {
        key: "home", path: "/", label: "Home", owner: "Core", icon: House, roles: ALL,
        summary: "Your journey, tasks and recent activity.", plans: [],
      },
    ],
  },
  {
    label: "Get ready",
    items: [
      {
        key: "profile", path: "/profile", label: "Profile", owner: "P01", icon: UserRound,
        roles: ["student", "coordinator", "reviewer", "advisor"],
        summary: "Student skills, interests and availability, with reviewed evidence.",
        plans: ["Draft, submit and revise a profile", "Coordinator clarification requests", "Every correction is a new version"],
      },
      {
        key: "opportunities", path: "/opportunities", label: "Opportunities", owner: "P02 · P03 · P04", icon: Building2,
        roles: ["student", "employer", "coordinator"],
        summary: "Employers submit listings, the coordinator reviews and publishes them, students browse.",
        plans: ["Employer submission with HR authorisation", "7-point review checklist: approve, return or decline", "Publish and close listings"],
      },
    ],
  },
  {
    label: "Apply & match",
    items: [
      {
        key: "applications", path: "/applications", label: "Applications", owner: "P04", icon: BriefcaseBusiness,
        roles: ["student", "employer", "coordinator"],
        summary: "Applications, offers and coordinator-confirmed placements.",
        plans: ["Apply to published, open listings", "Offers and acceptances", "Coordinator confirms the placement"],
      },
      {
        key: "matching", path: "/matching", label: "Matching", owner: "P05", icon: Sparkles,
        roles: ["student", "coordinator", "advisor"],
        summary: "AI recommendations with reasons and skill gaps. A recommendation is not a placement.",
        plans: ["Ranked matches with explanations", "Skill gaps sent to Preparation", "Auto re-run when the profile changes"],
      },
    ],
  },
  {
    label: "Prepare & work",
    items: [
      {
        key: "preparation", path: "/preparation", label: "Preparation", owner: "P06", icon: GraduationCap,
        roles: ["student", "reviewer", "coordinator", "advisor"],
        summary: "Learning modules that close skill gaps, with reviewed evidence.",
        plans: ["Preparation plan per student", "Jira board practice and evidence", "Reviewer marks a skill demonstrated"],
      },
      {
        key: "placement", path: "/placement", label: "Co-op placement", owner: "P07", icon: ClipboardList,
        roles: ["student", "employer", "supervisor", "advisor", "coordinator"],
        summary: "Learning agreement, logbook, milestones and final review.",
        plans: ["Three-way learning agreement sign-off", "Weekly logbook and acknowledgements", "Midpoint and final reviews backed by evidence"],
      },
    ],
  },
  {
    label: "Support",
    items: [
      {
        key: "assistant", path: "/assistant", label: "Assistant", owner: "P03 · P07", icon: Bot, roles: ALL,
        summary: "Answers from the approved FAQ. Questions it can't answer go to the coordinator.",
        plans: ["Approved FAQ answers with sources", "Unanswered questions queue", "Optional LLM mode when configured"],
      },
      {
        key: "records", path: "/records", label: "Records", owner: "Core", icon: ScrollText,
        roles: ["coordinator", "reviewer", "advisor"],
        summary: "Audit trail of every decision: who, what, when and why.",
        plans: ["Searchable event log", "Version history per record", "Export for the practicum report"],
      },
    ],
  },
];

export const NAV_ITEMS: NavItem[] = NAV.flatMap((g) => g.items);

export const canSee = (item: NavItem, role: Role) => item.roles === "all" || item.roles.includes(role);

export function navForRole(role: Role): NavGroup[] {
  return NAV.map((g) => ({ ...g, items: g.items.filter((i) => canSee(i, role)) })).filter((g) => g.items.length > 0);
}

export function findNav(pathname: string): { item: NavItem; group: NavGroup } | undefined {
  for (const group of NAV) {
    const item = group.items.find((i) => (i.path === "/" ? pathname === "/" : pathname.startsWith(i.path)));
    if (item) return { item, group };
  }
  return undefined;
}
