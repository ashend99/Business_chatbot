"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useRef } from "react";

import { useCurrency } from "@/components/CurrencyProvider";
import { LeadDetailPanel } from "@/components/leads/LeadDetailPanel";
import { LeadStatusBadge } from "@/components/ui/Badge";
import { CalendarIcon, ChevronDownIcon, SearchIcon } from "@/components/icons";
import { LEAD_PAGE_SIZE } from "@/lib/constants";
import { formatMoney, initials, leadDisplayName, relativeTime } from "@/lib/format";
import type { LeadListItem } from "@/lib/types";

const STATUS_TABS: { value: string; label: string }[] = [
  { value: "", label: "All" },
  { value: "new", label: "New" },
  { value: "interested", label: "Interested" },
  { value: "contacted", label: "Contacted" },
  { value: "converted", label: "Converted" },
  { value: "lost", label: "Lost" },
];

const DATE_RANGES: { value: string; label: string; days: number | null }[] = [
  { value: "", label: "All time", days: null },
  { value: "7", label: "Last 7 days", days: 7 },
  { value: "30", label: "Last 30 days", days: 30 },
  { value: "90", label: "Last 90 days", days: 90 },
];

export function LeadsView({
  leads,
  total,
  page,
}: {
  leads: LeadListItem[];
  total: number;
  page: number;
}) {
  const currency = useCurrency();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  const status = params.get("status") ?? "";
  const range = params.get("range") ?? "";
  const selectedId = params.get("id");
  const searchParam = params.get("search") ?? "";

  const setParams = useCallback(
    (patch: Record<string, string | null>, opts: { resetPage?: boolean } = {}) => {
      const next = new URLSearchParams(params.toString());
      for (const [key, value] of Object.entries(patch)) {
        if (value === null || value === "") next.delete(key);
        else next.set(key, value);
      }
      if (opts.resetPage !== false && !("page" in patch)) next.delete("page");
      router.push(`${pathname}?${next.toString()}`);
    },
    [params, pathname, router],
  );

  // Debounced search → URL. The input is uncontrolled (keyed on the URL value)
  // so external navigation resets it without a syncing effect.
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onSearchChange = (value: string) => {
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => setParams({ search: value || null }), 350);
  };

  const onRangeChange = (value: string) => {
    const preset = DATE_RANGES.find((r) => r.value === value);
    const createdAfter =
      preset?.days != null
        ? new Date(Date.now() - preset.days * 86_400_000).toISOString()
        : null;
    setParams({ range: value || null, created_after: createdAfter });
  };

  const totalPages = Math.max(1, Math.ceil(total / LEAD_PAGE_SIZE));

  return (
    <div className="flex flex-1 overflow-hidden">
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Filter bar */}
        <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface px-7 py-3">
          {STATUS_TABS.map((tab) => {
            const active = tab.value === status;
            return (
              <button
                key={tab.value}
                type="button"
                onClick={() => setParams({ status: tab.value || null })}
                className={`rounded-lg px-3 py-1.5 text-[12.5px] transition-colors ${
                  active
                    ? "bg-accent font-semibold text-white"
                    : "text-text-secondary hover:bg-surface-alt"
                }`}
              >
                {tab.label}
              </button>
            );
          })}

          <div className="ml-auto flex items-center gap-2">
            <div className="flex w-52 items-center gap-2 rounded-lg bg-surface-alt px-3 py-1.5">
              <SearchIcon size={14} className="text-text-muted" />
              <input
                key={searchParam}
                type="search"
                defaultValue={searchParam}
                onChange={(e) => onSearchChange(e.target.value)}
                placeholder="Search leads…"
                className="w-full bg-transparent text-[12.5px] text-text-primary placeholder:text-text-muted focus:outline-none"
              />
            </div>

            <label className="relative flex items-center">
              <CalendarIcon
                size={13}
                className="pointer-events-none absolute left-2.5 text-text-secondary"
              />
              <ChevronDownIcon
                size={12}
                className="pointer-events-none absolute right-2.5 text-text-muted"
              />
              <select
                value={range}
                onChange={(e) => onRangeChange(e.target.value)}
                className="appearance-none rounded-lg border border-border bg-surface py-1.5 pl-8 pr-7 text-[12.5px] text-text-secondary focus:outline-none"
              >
                {DATE_RANGES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-auto">
          {leads.length === 0 ? (
            <p className="p-8 text-center text-sm text-text-muted">
              No leads match these filters.
            </p>
          ) : (
            <table className="w-full">
              <thead className="sticky top-0 bg-bg">
                <tr className="text-left text-[11px] uppercase tracking-wide text-text-muted">
                  <th className="px-5 py-2.5 font-medium">Name</th>
                  <th className="px-5 py-2.5 font-medium">Status</th>
                  <th className="px-5 py-2.5 font-medium">Value</th>
                  <th className="px-5 py-2.5 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {leads.map((lead) => {
                  const name = leadDisplayName(lead.fields);
                  return (
                    <tr
                      key={lead.id}
                      onClick={() => setParams({ id: lead.id }, { resetPage: false })}
                      className={`cursor-pointer border-b border-border-subtle transition-colors ${
                        selectedId === lead.id ? "bg-accent-soft" : "hover:bg-surface-alt"
                      }`}
                    >
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-2.5">
                          <div className="flex h-[26px] w-[26px] items-center justify-center rounded-full bg-surface-alt text-[10.5px] font-semibold text-text-secondary">
                            {initials(name)}
                          </div>
                          <span className="text-[13px] font-medium text-text-primary">
                            {name}
                          </span>
                        </div>
                      </td>
                      <td className="px-5 py-3">
                        <LeadStatusBadge status={lead.status} />
                      </td>
                      <td className="px-5 py-3 text-[12.5px] text-text-primary">
                        {formatMoney(lead.deal_value, currency)}
                      </td>
                      <td
                        className="px-5 py-3 text-[12px] text-text-muted"
                        suppressHydrationWarning
                      >
                        {relativeTime(lead.created_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-border bg-surface px-7 py-2.5 text-[12px] text-text-muted">
            <span>
              {total} lead{total === 1 ? "" : "s"} · page {page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setParams({ page: String(page - 1) }, { resetPage: false })}
                className="rounded-md border border-border px-2.5 py-1 disabled:opacity-40 enabled:hover:bg-surface-alt"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setParams({ page: String(page + 1) }, { resetPage: false })}
                className="rounded-md border border-border px-2.5 py-1 disabled:opacity-40 enabled:hover:bg-surface-alt"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {selectedId && (
        <LeadDetailPanel
          key={selectedId}
          leadId={selectedId}
          onClose={() => setParams({ id: null }, { resetPage: false })}
        />
      )}
    </div>
  );
}
