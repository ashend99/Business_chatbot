"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { TenantStatusBadge } from "@/components/ui/Badge";
import { PlusIcon, SearchIcon } from "@/components/icons";
import { CreateTenantDialog } from "@/components/tenants/CreateTenantDialog";
import { TenantDetailPanel } from "@/components/tenants/TenantDetailPanel";
import { TENANT_PAGE_SIZE } from "@/lib/constants";
import { relativeTime } from "@/lib/format";
import type { TenantListItem } from "@/lib/types";

const STATUS_TABS: { value: string; label: string }[] = [
  { value: "", label: "All" },
  { value: "active", label: "Active" },
  { value: "suspended", label: "Suspended" },
];

export function TenantsView({
  tenants,
  total,
  page,
}: {
  tenants: TenantListItem[];
  total: number;
  page: number;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [creating, setCreating] = useState(false);

  const status = params.get("status") ?? "";
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

  const totalPages = Math.max(1, Math.ceil(total / TENANT_PAGE_SIZE));

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
                placeholder="Search tenants…"
                className="w-full bg-transparent text-[12.5px] text-text-primary placeholder:text-text-muted focus:outline-none"
              />
            </div>
            <Button size="sm" onClick={() => setCreating(true)}>
              <PlusIcon size={14} />
              New tenant
            </Button>
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-auto">
          {tenants.length === 0 ? (
            <p className="p-8 text-center text-sm text-text-muted">No tenants match these filters.</p>
          ) : (
            <table className="w-full">
              <thead className="sticky top-0 bg-bg">
                <tr className="text-left text-[11px] uppercase tracking-wide text-text-muted">
                  <th className="px-5 py-2.5 font-medium">Name</th>
                  <th className="px-5 py-2.5 font-medium">Slug</th>
                  <th className="px-5 py-2.5 font-medium">Email</th>
                  <th className="px-5 py-2.5 font-medium">Status</th>
                  <th className="px-5 py-2.5 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {tenants.map((t) => (
                  <tr
                    key={t.id}
                    onClick={() => setParams({ id: t.id }, { resetPage: false })}
                    className={`cursor-pointer border-b border-border-subtle transition-colors ${
                      selectedId === t.id ? "bg-accent-soft" : "hover:bg-surface-alt"
                    }`}
                  >
                    <td className="px-5 py-3 text-[13px] font-medium text-text-primary">{t.name}</td>
                    <td className="px-5 py-3 text-[12.5px] text-text-secondary">{t.slug}</td>
                    <td className="px-5 py-3 text-[12.5px] text-text-secondary">{t.email ?? "—"}</td>
                    <td className="px-5 py-3">
                      <TenantStatusBadge isActive={t.is_active} />
                    </td>
                    <td className="px-5 py-3 text-[12px] text-text-muted" suppressHydrationWarning>
                      {relativeTime(t.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between border-t border-border bg-surface px-7 py-2.5 text-[12px] text-text-muted">
            <span>
              {total} tenant{total === 1 ? "" : "s"} · page {page} of {totalPages}
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
        <TenantDetailPanel
          key={selectedId}
          tenantId={selectedId}
          onClose={() => setParams({ id: null }, { resetPage: false })}
        />
      )}

      {creating && (
        <CreateTenantDialog
          onClose={() => setCreating(false)}
          onCreated={(tenant) => {
            setCreating(false);
            setParams({ id: tenant.id }, { resetPage: false });
            router.refresh();
          }}
        />
      )}
    </div>
  );
}
