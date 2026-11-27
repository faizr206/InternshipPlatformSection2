import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Download, ScrollText, Waypoints } from "lucide-react";
import { useState } from "react";
import { records } from "@/api/modules";
import { Input, Loading, Section, StatusBadge } from "@/components/kit";
import { Badge, Button, OwnerChip, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui";

function download(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function RecordsPage() {
  const handoffs = useQuery({ queryKey: ["handoffs"], queryFn: records.handoffs });
  const events = useQuery({ queryKey: ["all-events"], queryFn: () => records.events(500) });
  const [q, setQ] = useState("");
  const shown = (events.data ?? []).filter((e) => !q || `${e.text} ${e.ref} ${e.actor_name} ${e.module}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <Tabs defaultValue="handoffs" className="space-y-4">
      <TabsList><TabsTrigger value="handoffs">Cross-team handoffs</TabsTrigger><TabsTrigger value="events">Activity log</TabsTrigger></TabsList>
      <TabsContent value="handoffs">
        <Section icon={<Waypoints className="h-4 w-4" />} title="Handoff records" subtitle="Every live handoff between modules, in the fields the teams agreed (data dictionary v3)"
          action={<Button size="sm" onClick={() => download("coop-handoffs.json", handoffs.data)}><Download className="h-3.5 w-3.5" />Export JSON</Button>}>
          {!handoffs.data ? <Loading /> : handoffs.data.length === 0 ? <p className="text-[13px] text-muted">No handoffs yet.</p> : (
            <div className="space-y-2">
              {handoffs.data.map((h) => (
                <details key={h.handoff_id} className="rounded-ctl border border-line px-3 py-2 text-[13px]">
                  <summary className="flex cursor-pointer flex-wrap items-center gap-2">
                    <span className="font-mono text-[12px]">{h.handoff_id}</span><OwnerChip owner={h.from_module} /><ArrowRight className="h-3.5 w-3.5 text-muted" aria-hidden /><OwnerChip owner={h.to_module} />
                    <span>{h.kind.replace(/_/g, " ")}</span><Badge tone="neutral">{h.ref}</Badge><StatusBadge status={h.status} />
                    <span className="ml-auto text-[12px] text-muted">{new Date(h.created_at).toLocaleString("en-GB")}</span>
                  </summary>
                  <pre className="mt-2 overflow-x-auto rounded-ctl bg-navy p-3 text-[12px] text-nav-ink">{JSON.stringify(h.payload, null, 2)}</pre>
                </details>
              ))}
            </div>
          )}
        </Section>
      </TabsContent>
      <TabsContent value="events">
        <Section icon={<ScrollText className="h-4 w-4" />} title="Activity log" subtitle="Who did what, when, to which record"
          action={<Button size="sm" onClick={() => download("coop-activity.json", events.data)}><Download className="h-3.5 w-3.5" />Export JSON</Button>}>
          <Input aria-label="Filter the activity log" placeholder="Filter by text, record ID, person or module" value={q} onChange={(e) => setQ(e.target.value)} className="mb-3 max-w-md" />
          {!events.data ? <Loading /> : (
            <table className="w-full text-left text-[13px]">
              <thead className="text-[11.5px] tracking-wide text-muted uppercase"><tr><th className="py-1.5">When</th><th>Module</th><th>Who</th><th>What</th><th>Record</th></tr></thead>
              <tbody>{shown.map((e) => (
                <tr key={e.id} className="border-t border-line align-top">
                  <td className="py-2 pr-3 whitespace-nowrap text-muted">{new Date(e.at).toLocaleString("en-GB")}</td>
                  <td className="pr-3"><OwnerChip owner={e.module} /></td>
                  <td className="pr-3">{e.actor_name}<div className="text-[11.5px] text-muted">{e.actor_role}</div></td>
                  <td className="pr-3">{e.text}</td>
                  <td className="font-mono text-[12px]">{e.ref}</td>
                </tr>
              ))}</tbody>
            </table>
          )}
        </Section>
      </TabsContent>
    </Tabs>
  );
}
