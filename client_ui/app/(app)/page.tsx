import { LeadStatusBadge } from "@/components/ui/Badge";
import { StatCard } from "@/components/ui/StatCard";
import { Topbar } from "@/components/Topbar";
import type { LeadStatus } from "@/lib/types";

/*
 * Placeholder data. There's no `/tenant/overview` stats endpoint on the
 * backend yet — wire these to it once it exists (or derive client-side from
 * the leads / conversations / documents list endpoints).
 */
const STATS = [
  { label: "New leads this week", value: "18", sub: "↑ 12% vs last week", subTone: "positive" as const },
  { label: "Open conversations", value: "7", sub: "2 waiting > 1hr" },
  { label: "Documents published", value: "24", sub: "of 26 total" },
  { label: "Lead → conversion", value: "31%", sub: "↓ 3% vs last week", subTone: "negative" as const, highlight: true },
];

const RECENT_LEADS: {
  name: string;
  status: LeadStatus;
  channel: string;
  created: string;
}[] = [
  { name: "Nadeesha Perera", status: "new", channel: "Website", created: "2h ago" },
  { name: "Kasun Silva", status: "contacted", channel: "WhatsApp", created: "5h ago" },
  { name: "Ishara Fernando", status: "interested", channel: "Facebook", created: "1d ago" },
  { name: "Tharindu Jayasuriya", status: "converted", channel: "Website", created: "2d ago" },
];

const RECENT_CONVERSATIONS = [
  { name: "Nadeesha Perera", preview: "Do you deliver to Nugegoda?" },
  { name: "Kasun Silva", preview: "Price for the BBQ Pork Ribs?" },
  { name: "Ishara Fernando", preview: "What are your opening hours?" },
];

export default function OverviewPage() {
  return (
    <>
      <Topbar title="Overview" />
      <div className="flex-1 overflow-auto px-7 py-6">
        <div className="grid grid-cols-4 gap-4">
          {STATS.map((s) => (
            <StatCard key={s.label} {...s} />
          ))}
        </div>

        <div className="mt-4 grid grid-cols-[1.6fr_1fr] gap-4">
          <section className="overflow-hidden rounded-xl border border-border bg-surface">
            <div className="flex items-center justify-between border-b border-border-subtle px-[18px] py-4">
              <h2 className="text-[13.5px] font-semibold text-text-primary">Recent leads</h2>
              <a href="/leads" className="text-[12.5px] text-accent hover:underline">
                View all
              </a>
            </div>
            <table className="w-full">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-text-muted">
                  <th className="px-[18px] py-2 font-medium">Name</th>
                  <th className="px-[18px] py-2 font-medium">Status</th>
                  <th className="px-[18px] py-2 font-medium">Channel</th>
                  <th className="px-[18px] py-2 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {RECENT_LEADS.map((lead) => (
                  <tr key={lead.name} className="border-t border-border-subtle">
                    <td className="px-[18px] py-2.5 text-[13px] font-medium text-text-primary">
                      {lead.name}
                    </td>
                    <td className="px-[18px] py-2.5">
                      <LeadStatusBadge status={lead.status} />
                    </td>
                    <td className="px-[18px] py-2.5 text-[12.5px] text-text-secondary">
                      {lead.channel}
                    </td>
                    <td className="px-[18px] py-2.5 text-[12.5px] text-text-muted">
                      {lead.created}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="rounded-xl border border-border bg-surface p-[18px]">
            <h2 className="mb-3.5 text-[13.5px] font-semibold text-text-primary">
              Recent conversations
            </h2>
            <ul className="flex flex-col gap-3.5">
              {RECENT_CONVERSATIONS.map((c) => (
                <li key={c.name} className="flex gap-2.5">
                  <div className="h-[30px] w-[30px] shrink-0 rounded-full bg-accent-soft" />
                  <div className="flex flex-col gap-0.5">
                    <span className="text-[12.5px] font-medium text-text-primary">
                      {c.name}
                    </span>
                    <span className="text-xs text-text-muted">&ldquo;{c.preview}&rdquo;</span>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </>
  );
}
