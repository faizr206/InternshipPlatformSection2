import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Role } from "@/api/types";

export const STORAGE_KEY = "coop-demo-v1";

export const ROLES: { value: Role; label: string; hint: string }[] = [
  { value: "student", label: "Student", hint: "Builds a profile, applies, prepares" },
  { value: "employer", label: "Employer", hint: "Submits opportunities, picks applicants" },
  { value: "coordinator", label: "Coordinator", hint: "Reviews, publishes, confirms placements" },
  { value: "reviewer", label: "Learning reviewer", hint: "Reviews skill evidence" },
  { value: "supervisor", label: "Workplace supervisor", hint: "Signs agreement, acknowledges logbooks" },
  { value: "advisor", label: "Academic advisor", hint: "Runs midpoint and final reviews" },
];

export const DEFAULT_STUDENT = "COOP-B001";

interface DemoState {
  role: Role;
  studentId: string;
}

interface DemoContextValue extends DemoState {
  setRole: (r: Role) => void;
  setStudentId: (id: string) => void;
}

const Ctx = createContext<DemoContextValue | null>(null);

function load(): DemoState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const v = JSON.parse(raw) as Partial<DemoState>;
      if (v.role && ROLES.some((r) => r.value === v.role) && typeof v.studentId === "string")
        return { role: v.role, studentId: v.studentId };
    }
  } catch {
    /* storage unavailable or corrupt: fall back to defaults */
  }
  return { role: "student", studentId: DEFAULT_STUDENT };
}

export function DemoProvider({ children, initial }: { children: ReactNode; initial?: Partial<DemoState> }) {
  const [state, setState] = useState<DemoState>(() => ({ ...load(), ...initial }));

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      /* ignore */
    }
  }, [state]);

  const setRole = useCallback((role: Role) => setState((s) => ({ ...s, role })), []);
  const setStudentId = useCallback((studentId: string) => setState((s) => ({ ...s, studentId })), []);
  const value = useMemo(() => ({ ...state, setRole, setStudentId }), [state, setRole, setStudentId]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDemo() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useDemo must be used inside <DemoProvider>");
  return v;
}

export const roleLabel = (r: Role) => ROLES.find((x) => x.value === r)?.label ?? r;
