import { FlaskConical } from "lucide-react";

/** Always-visible reminder that nothing here is real. Rendered by AppShell on every page. */
export function DemoBanner() {
  return (
    <div
      role="note"
      aria-label="Demo notice"
      data-testid="demo-banner"
      className="flex items-center justify-center gap-2 border-b border-gold/40 bg-gold-50 px-4 py-1.5 text-center text-[12.5px] font-medium text-gold-ink"
    >
      <FlaskConical className="h-3.5 w-3.5 shrink-0" aria-hidden />
      <span>Synthetic data · simulated roles · demo only</span>
    </div>
  );
}
