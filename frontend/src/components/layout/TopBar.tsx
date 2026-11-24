import { ChevronRight, Menu, Sparkles } from "lucide-react";
import { useLocation } from "react-router-dom";
import { Button, OwnerChip } from "@/components/ui";
import { findNav } from "@/lib/nav";
import { DemoMenu } from "./DemoMenu";
import { RoleSwitcher, StudentPicker } from "./RoleSwitcher";
import { useUI } from "./UIContext";

export function TopBar({ onMenu }: { onMenu: () => void }) {
  const { pathname } = useLocation();
  const { openAssistant } = useUI();
  const match = findNav(pathname);
  const title = match?.item.label ?? "Not found";

  return (
    <header className="border-b border-line bg-surface/90 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3 nav:px-7">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <Button variant="ghost" size="icon" className="-ml-1.5 nav:hidden" aria-label="Open navigation" onClick={onMenu}>
            <Menu className="h-5 w-5" aria-hidden />
          </Button>
          <div className="min-w-0">
            <nav aria-label="Breadcrumb" className="hidden sm:block">
              <ol className="flex items-center gap-1 text-[12px] text-muted">
                <li>Coop Platform</li>
                {match && match.item.path !== "/" && (
                  <>
                    <ChevronRight className="h-3 w-3" aria-hidden />
                    <li>{match.group.label}</li>
                  </>
                )}
                <ChevronRight className="h-3 w-3" aria-hidden />
                <li aria-current="page" className="font-medium text-ink">
                  {title}
                </li>
              </ol>
            </nav>
            <div className="flex items-center gap-2">
              <h1 className="truncate text-[18px] leading-7 font-semibold">{title}</h1>
              {match && <OwnerChip owner={match.item.owner} />}
            </div>
          </div>
        </div>
        <Button variant="ai" size="icon" className="min-[1100px]:hidden" aria-label="Open assistant" onClick={() => openAssistant()}>
          <Sparkles className="h-4 w-4" aria-hidden />
        </Button>
        <div className="grid w-full grid-cols-2 gap-2 sm:flex sm:w-auto sm:flex-wrap sm:items-center">
          <RoleSwitcher className="sm:w-[210px]" />
          <StudentPicker className="sm:w-[200px]" />
          <DemoMenu className="col-span-2 justify-between sm:col-span-1" />
          <div className="hidden min-[1100px]:block">
            <Button variant="ai" onClick={() => openAssistant()}>
              <Sparkles className="h-4 w-4" aria-hidden />
              Assistant
            </Button>
          </div>
        </div>
      </div>
    </header>
  );
}
