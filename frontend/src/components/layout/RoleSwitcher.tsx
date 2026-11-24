import { useNavigate, useLocation } from "react-router-dom";
import type { Role } from "@/api/types";
import { ROLES, useDemo } from "@/context/DemoContext";
import { Select } from "@/components/ui";
import { findNav, canSee } from "@/lib/nav";
import { useStudents } from "@/api/hooks";

export function RoleSwitcher({ className }: { className?: string }) {
  const { role, setRole } = useDemo();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  return (
    <Select
      label="Demo as role"
      prefix="Demo as"
      className={className}
      value={role}
      onValueChange={(v) => {
        const r = v as Role;
        setRole(r);
        // If the current page isn't part of the new role's journey, go home.
        const here = findNav(pathname);
        if (here && !canSee(here.item, r)) navigate("/");
      }}
      options={ROLES.map((r) => ({ value: r.value, label: r.label, hint: r.hint }))}
    />
  );
}

export function StudentPicker({ className }: { className?: string }) {
  const { studentId, setStudentId } = useDemo();
  const { data: students = [] } = useStudents();
  const options = students.length
    ? students.map((s) => ({ value: s.student_id, label: s.display_name, hint: `${s.student_id} · ${s.programme}` }))
    : [{ value: studentId, label: studentId }];
  return (
    <Select
      label="Student"
      prefix="Student"
      className={className}
      value={studentId}
      onValueChange={setStudentId}
      options={options}
    />
  );
}
