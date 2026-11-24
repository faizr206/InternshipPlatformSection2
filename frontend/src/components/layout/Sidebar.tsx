import { NavLink } from "react-router-dom";
import { useDemo, roleLabel } from "@/context/DemoContext";
import { useNavCounts, useStudents } from "@/api/hooks";
import { navForRole } from "@/lib/nav";
import { PERSONAS } from "@/lib/personas";
import { cn } from "@/lib/cn";
import { Avatar } from "@/components/ui";
import { Brand } from "./Brand";

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { role, studentId } = useDemo();
  const { data: counts } = useNavCounts({ role, student_id: studentId });
  const { data: students } = useStudents();
  const student = students?.find((s) => s.student_id === studentId);
  const groups = navForRole(role);
  const who = role === "student" ? { name: student?.display_name ?? studentId, org: student?.programme ?? "" } : PERSONAS[role];

  return (
    <div className="on-navy flex h-full flex-col bg-gradient-to-b from-navy to-navy-3 text-nav-ink">
      <Brand />
      <nav aria-label="Main" className="scrollbar-thin flex-1 overflow-y-auto px-3 pb-4">
        {groups.map((g) => (
          <div key={g.label} className="mt-3 first:mt-1">
            <div className="px-3 pb-1.5 text-[10.5px] font-semibold tracking-[0.1em] text-nav-muted uppercase">{g.label}</div>
            <ul className="flex flex-col gap-0.5">
              {g.items.map((item) => {
                const n = counts?.[item.key] ?? 0;
                const Icon = item.icon;
                return (
                  <li key={item.key}>
                    <NavLink
                      to={item.path}
                      end={item.path === "/"}
                      onClick={onNavigate}
                      className={({ isActive }) =>
                        cn(
                          "group flex items-center gap-3 rounded-ctl px-3 py-2 text-[14px] font-medium transition-colors",
                          isActive
                            ? "bg-gold/15 text-white shadow-[inset_0_0_0_1px_rgb(217_186_130/0.35)]"
                            : "hover:bg-white/[0.06] hover:text-white",
                        )
                      }
                    >
                      {({ isActive }) => (
                        <>
                          <Icon className={cn("h-[18px] w-[18px] shrink-0", isActive ? "text-gold" : "text-nav-muted group-hover:text-nav-ink")} aria-hidden />
                          <span className="min-w-0 flex-1 truncate">{item.label}</span>
                          {n > 0 && (
                            <span
                              aria-label={`${n} pending`}
                              className="min-w-5 rounded-full bg-gold px-1.5 text-center text-[11px] leading-5 font-bold text-navy"
                            >
                              {n}
                            </span>
                          )}
                        </>
                      )}
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
      <div className="m-3 flex items-center gap-3 rounded-card border border-white/10 bg-white/[0.04] p-3">
        <Avatar name={who.name} className="bg-gold/20 text-gold" />
        <div className="min-w-0">
          <div className="truncate text-[13px] font-semibold text-white">{who.name}</div>
          <div className="truncate text-[11.5px] text-nav-muted">Demo as {roleLabel(role)}</div>
        </div>
      </div>
    </div>
  );
}
