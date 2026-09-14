"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/Button";
import { Input, Select, Textarea } from "@/components/ui/Field";
import { LeadStatusBadge } from "@/components/ui/Badge";
import { formatDateTime, initials, leadDisplayName, relativeTime } from "@/lib/format";
import type { LeadDetail, LeadFieldDef, LeadStatus } from "@/lib/types";

const STATUS_OPTIONS: LeadStatus[] = ["interested", "new", "contacted", "converted", "lost"];
const STATUS_LABELS: Record<LeadStatus, string> = {
  interested: "Interested",
  new: "New",
  contacted: "Contacted",
  converted: "Converted",
  lost: "Lost",
};

export function LeadDetailPanel({
  leadId,
  onClose,
}: {
  leadId: string;
  onClose: () => void;
}) {
  const router = useRouter();
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [fieldDefs, setFieldDefs] = useState<LeadFieldDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // This component is keyed on `leadId` by the parent, so it remounts (fresh
  // state) whenever the selection changes — the effect below only ever runs
  // once per mount.

  // Editable fields.
  const [status, setStatus] = useState<LeadStatus>("new");
  const [dealValue, setDealValue] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [leadRes, defsRes] = await Promise.all([
          fetch(`/api/tenant/leads/${leadId}`),
          fetch("/api/tenant/lead-field-defs"),
        ]);
        if (!leadRes.ok) {
          throw new Error((await leadRes.json().catch(() => ({}))).error ?? "Failed to load");
        }
        const data = (await leadRes.json()) as LeadDetail;
        const defs = defsRes.ok ? ((await defsRes.json()) as LeadFieldDef[]) : [];
        if (cancelled) return;
        setLead(data);
        setFieldDefs(defs);
        setStatus(data.status);
        setDealValue(data.deal_value ?? "");
        setNotes(data.notes ?? "");
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [leadId]);

  const dirty =
    lead != null &&
    (status !== lead.status ||
      (dealValue || "") !== (lead.deal_value ?? "") ||
      (notes || "") !== (lead.notes ?? ""));

  async function save() {
    if (!lead) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const res = await fetch(`/api/tenant/leads/${leadId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status,
          deal_value: dealValue === "" ? null : dealValue,
          notes: notes === "" ? null : notes,
        }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? "Save failed");
      const updated = await res.json();
      setLead({ ...lead, ...updated });
      setSaved(true);
      router.refresh(); // reflect the new status in the list
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <aside className="flex w-[400px] shrink-0 flex-col overflow-auto border-l border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border-subtle px-5 py-3.5">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
          Lead
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="rounded p-1 text-text-muted hover:bg-surface-alt hover:text-text-primary"
        >
          <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      {loading && <p className="p-5 text-[12.5px] text-text-muted">Loading…</p>}
      {error && !loading && (
        <p className="m-5 rounded-lg bg-red-50 px-3 py-2 text-[12.5px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
          {error}
        </p>
      )}

      {lead && !loading && (
        <>
          <div className="flex items-center gap-3 border-b border-border-subtle px-5 py-4">
            <div className="flex h-[42px] w-[42px] items-center justify-center rounded-full bg-accent-soft text-sm font-semibold text-accent-soft-fg">
              {initials(leadDisplayName(lead.fields))}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[14.5px] font-semibold text-text-primary">
                {leadDisplayName(lead.fields)}
              </p>
              <p className="text-xs text-text-muted">
                {(lead.source_channel ?? "Unknown channel")} · {relativeTime(lead.created_at)}
              </p>
            </div>
            <LeadStatusBadge status={lead.status} />
          </div>

          {fieldDefs.length > 0 && (
            <div className="flex flex-col gap-2.5 border-b border-border-subtle px-5 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                Captured details
              </p>
              {fieldDefs.map((def) => (
                <div key={def.id} className="flex justify-between gap-3">
                  <span className="text-[12.5px] text-text-muted">{def.label}</span>
                  <span className="text-right text-[12.5px] font-medium text-text-primary">
                    {lead.fields[def.field_key] || "—"}
                  </span>
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-col gap-3 border-b border-border-subtle px-5 py-4">
            <label className="flex flex-col gap-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                Status
              </span>
              <Select value={status} onChange={(e) => setStatus(e.target.value as LeadStatus)}>
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABELS[s]}
                  </option>
                ))}
              </Select>
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                Deal value
              </span>
              <Input
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                placeholder="0.00"
                value={dealValue}
                onChange={(e) => setDealValue(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                Notes
              </span>
              <Textarea
                placeholder="Internal notes about this lead…"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </label>
            <div className="flex items-center gap-3">
              <Button size="sm" onClick={save} disabled={!dirty || saving}>
                {saving ? "Saving…" : "Save changes"}
              </Button>
              {saved && !dirty && (
                <span className="text-[12px] text-positive">Saved</span>
              )}
            </div>
          </div>

          <div className="flex flex-col gap-3 px-5 py-4">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
              Conversation
            </p>
            {lead.transcript.length === 0 ? (
              <p className="text-[12.5px] text-text-muted">
                No linked conversation.
              </p>
            ) : (
              <div className="flex flex-col gap-2">
                {lead.transcript.map((m, i) =>
                  m.role === "system" ? (
                    <p key={i} className="self-center text-[11px] text-text-muted">
                      {m.content}
                    </p>
                  ) : (
                    <div
                      key={i}
                      className={`max-w-[85%] rounded-xl px-3 py-2 text-[12.5px] ${
                        m.role === "user"
                          ? "self-start rounded-bl-sm bg-surface-alt text-text-primary"
                          : "self-end rounded-br-sm bg-accent text-white"
                      }`}
                      title={formatDateTime(m.created_at)}
                    >
                      {m.content}
                    </div>
                  ),
                )}
              </div>
            )}
          </div>
        </>
      )}
    </aside>
  );
}
