import { Check, Lock } from "lucide-react";
import type { ComponentType } from "react";
import { Link } from "react-router-dom";
import { buttonStyles, Card, EmptyState, OwnerChip } from "@/components/ui";
import { roleLabel, useDemo } from "@/context/DemoContext";
import { canSee, type NavItem } from "@/lib/nav";

/** Role guard for a module page; renders the real page, or a placeholder if a module has none yet. */
export default function ModulePage({ item, page: Page }: { item: NavItem; page?: ComponentType }) {
  const { role } = useDemo();
  const Icon = item.icon;

  if (!canSee(item, role)) {
    return (
      <Card>
        <EmptyState
          icon={<Lock className="h-6 w-6" />}
          title={`${item.label} isn't part of the ${roleLabel(role).toLowerCase()} view`}
          action={
            <Link to="/" className={buttonStyles("primary")}>Back to Home</Link>
          }
        >
          Switch role with “Demo as” in the top bar to see this module.
        </EmptyState>
      </Card>
    );
  }

  if (Page)
    return (
      <div className="space-y-4">
        <p className="max-w-3xl text-[14px] text-muted">{item.summary}</p>
        <Page />
      </div>
    );

  return (
    <div className="space-y-5">
      <p className="max-w-3xl text-[14.5px] text-muted">{item.summary}</p>
      <Card>
        <EmptyState
          icon={<Icon className="h-6 w-6" />}
          title={`Nothing here yet`}
          action={
            <Link to="/" className={buttonStyles("secondary")}>Back to Home</Link>
          }
        >
          The {item.label.toLowerCase()} module is being connected to the shared backend. Records will appear here for the{" "}
          {roleLabel(role).toLowerCase()} view.
        </EmptyState>
        {item.plans.length > 0 && (
          <div className="border-t border-line px-5 py-4">
            <div className="mb-2 flex items-center gap-2 text-[12px] font-semibold tracking-wide text-muted uppercase">
              Coming in this module <OwnerChip owner={item.owner} />
            </div>
            <ul className="grid gap-2 sm:grid-cols-3">
              {item.plans.map((p) => (
                <li key={p} className="flex items-start gap-2 rounded-ctl bg-bg px-3 py-2.5 text-[13px]">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-ok" aria-hidden />
                  {p}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>
    </div>
  );
}
