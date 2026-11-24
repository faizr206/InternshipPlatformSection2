import type { Role } from "@/api/types";

/** Synthetic demo actor for each simulated role (student role uses the picked student). */
export const PERSONAS: Record<Exclude<Role, "student">, { name: string; org: string }> = {
  employer: { name: "Emirates Group HR", org: "Employer partner" },
  coordinator: { name: "Dr. Salma", org: "Co-op office" },
  reviewer: { name: "Maya", org: "Learning reviewer" },
  supervisor: { name: "R. Khan", org: "Workplace supervisor · Emirates Group" },
  advisor: { name: "Dr. Omar", org: "Academic advisor" },
};
