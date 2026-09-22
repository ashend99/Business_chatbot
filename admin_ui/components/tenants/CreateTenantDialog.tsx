"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { Toggle } from "@/components/ui/Toggle";
import { KNOWN_CHANNELS, type Channel, type TenantCreatePayload, type TenantRead } from "@/lib/types";

const DEFAULT_ENTITLEMENTS = { ordering_allowed: true, catalog_allowed: true, documents_allowed: true, leads_allowed: true };

export function CreateTenantDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (tenant: TenantRead) => void;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [email, setEmail] = useState("");
  const [contactPerson, setContactPerson] = useState("");
  const [contactNumber, setContactNumber] = useState("");
  const [address, setAddress] = useState("");
  const [currency, setCurrency] = useState("");
  const [timezone, setTimezone] = useState("UTC");
  const [entitlements, setEntitlements] = useState(DEFAULT_ENTITLEMENTS);
  const [channels, setChannels] = useState<Channel[]>(["website_widget"]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleChannel(c: Channel) {
    setChannels((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const payload: TenantCreatePayload = {
      name,
      slug,
      email,
      contact_person: contactPerson || null,
      contact_number: contactNumber || null,
      address: address || null,
      currency_code: currency.toUpperCase(),
      timezone,
      admin_settings: { ...entitlements, allowed_channels: channels },
    };
    try {
      const res = await fetch("/api/tenants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error ?? "Could not create tenant.");
      onCreated(data as TenantRead);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create tenant.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title="New tenant" onClose={onClose} width={480}>
      <form onSubmit={submit} className="flex flex-col gap-3.5">
        {error && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-[12.5px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
            {error}
          </p>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Field label="Business name">
            <Input value={name} onChange={(e) => setName(e.target.value)} required />
          </Field>
          <Field label="Slug" hint="Used as the dashboard login identifier.">
            <Input
              value={slug}
              onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, "-"))}
              required
            />
          </Field>
        </div>

        <Field label="Contact email">
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Contact person">
            <Input value={contactPerson} onChange={(e) => setContactPerson(e.target.value)} />
          </Field>
          <Field label="Contact number">
            <Input value={contactNumber} onChange={(e) => setContactNumber(e.target.value)} />
          </Field>
        </div>

        <Field label="Address">
          <Input value={address} onChange={(e) => setAddress(e.target.value)} />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Currency" hint="3-letter ISO code, e.g. USD, LKR.">
            <Input
              value={currency}
              onChange={(e) => setCurrency(e.target.value.toUpperCase())}
              maxLength={3}
              placeholder="USD"
              required
            />
          </Field>
          <Field label="Initial timezone">
            <Input value={timezone} onChange={(e) => setTimezone(e.target.value)} />
          </Field>
        </div>

        <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">Entitlements</p>
          {(Object.keys(DEFAULT_ENTITLEMENTS) as (keyof typeof DEFAULT_ENTITLEMENTS)[]).map((key) => (
            <div key={key} className="flex items-center justify-between">
              <span className="text-[12.5px] text-text-primary">{key.replace("_allowed", "")}</span>
              <Toggle
                label={key}
                checked={entitlements[key]}
                onChange={(v) => setEntitlements((prev) => ({ ...prev, [key]: v }))}
              />
            </div>
          ))}
        </div>

        <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">Allowed channels</p>
          {KNOWN_CHANNELS.map((c) => (
            <label key={c} className="flex items-center gap-2 text-[12.5px] text-text-primary">
              <input type="checkbox" checked={channels.includes(c)} onChange={() => toggleChannel(c)} />
              {c}
            </label>
          ))}
        </div>

        <div className="mt-1 flex justify-end gap-2">
          <Button type="button" variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" disabled={saving}>
            {saving ? "Creating…" : "Create tenant"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
