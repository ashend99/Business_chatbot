"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Field";
import { Toggle } from "@/components/ui/Toggle";
import { ActivationBadge, ApiKeyStatusBadge, TenantStatusBadge } from "@/components/ui/Badge";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { CheckIcon, CopyIcon, KeyIcon } from "@/components/icons";
import { formatDateTime } from "@/lib/format";
import {
  KNOWN_CHANNELS,
  type AdminSettingsRead,
  type ApiKeyCreated,
  type ApiKeyRead,
  type Channel,
  type TenantDetail,
} from "@/lib/types";

function Section({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-border-subtle">
      <div className="px-5 py-3">
        <h3 className="text-[12px] font-semibold uppercase tracking-wide text-text-muted">{title}</h3>
        {description && <p className="mt-0.5 text-[11.5px] text-text-muted">{description}</p>}
      </div>
      <div className="flex flex-col gap-3 px-5 pb-4">{children}</div>
    </section>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[12.5px] font-medium text-text-secondary">{label}</span>
      {children}
      {hint && <span className="text-[11.5px] text-text-muted">{hint}</span>}
    </label>
  );
}

function ToggleRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-[12.5px] text-text-primary">{label}</span>
      <Toggle label={label} checked={checked} onChange={onChange} />
    </div>
  );
}

const ENTITLEMENT_LABELS: Record<string, string> = {
  ordering_allowed: "Ordering",
  catalog_allowed: "Catalog",
  documents_allowed: "Documents",
  leads_allowed: "Leads",
};

export function TenantDetailPanel({ tenantId, onClose }: { tenantId: string; onClose: () => void }) {
  const router = useRouter();
  const confirm = useConfirm();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [tenant, setTenant] = useState<TenantDetail | null>(null);
  const [savedSettings, setSavedSettings] = useState<AdminSettingsRead | null>(null);
  const [settings, setSettings] = useState<AdminSettingsRead | null>(null);
  const [keys, setKeys] = useState<ApiKeyRead[]>([]);

  // Profile form
  const [profile, setProfile] = useState({ name: "", email: "", contact_person: "", contact_number: "", address: "" });
  const [profileSaving, setProfileSaving] = useState(false);

  const [settingsSaving, setSettingsSaving] = useState(false);
  const [statusBusy, setStatusBusy] = useState(false);
  const [inviteBusy, setInviteBusy] = useState(false);

  const [newSecret, setNewSecret] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [keyBusy, setKeyBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [tRes, sRes, kRes] = await Promise.all([
          fetch(`/api/tenants/${tenantId}`),
          fetch(`/api/tenants/${tenantId}/settings`),
          fetch(`/api/tenants/${tenantId}/api-keys`),
        ]);
        if (!tRes.ok) throw new Error((await tRes.json().catch(() => ({}))).error ?? "Failed to load");
        const t = (await tRes.json()) as TenantDetail;
        const s = sRes.ok ? ((await sRes.json()) as AdminSettingsRead) : null;
        const k = kRes.ok ? ((await kRes.json()) as ApiKeyRead[]) : [];
        if (cancelled) return;
        setTenant(t);
        setProfile({
          name: t.name,
          email: t.email ?? "",
          contact_person: t.contact_person ?? "",
          contact_number: t.contact_number ?? "",
          address: t.address ?? "",
        });
        setSavedSettings(s);
        setSettings(s);
        setKeys(k);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenantId]);

  const profileDirty =
    tenant != null &&
    (profile.name !== tenant.name ||
      profile.email !== (tenant.email ?? "") ||
      profile.contact_person !== (tenant.contact_person ?? "") ||
      profile.contact_number !== (tenant.contact_number ?? "") ||
      profile.address !== (tenant.address ?? ""));

  const settingsDirty = useMemo(() => {
    if (!settings || !savedSettings) return false;
    return JSON.stringify(settings) !== JSON.stringify(savedSettings);
  }, [settings, savedSettings]);

  async function saveProfile() {
    if (!tenant) return;
    setProfileSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/tenants/${tenantId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: profile.name,
          email: profile.email,
          contact_person: profile.contact_person || null,
          contact_number: profile.contact_number || null,
          address: profile.address || null,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error ?? "Save failed");
      setTenant((prev) => (prev ? { ...prev, ...data } : prev));
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setProfileSaving(false);
    }
  }

  async function saveSettings() {
    if (!settings || !savedSettings) return;
    setSettingsSaving(true);
    setError(null);
    // Only send fields that actually changed. Every field except
    // llm_model/monthly_message_limit/max_documents must be omitted rather
    // than sent as null -- the backend 422s otherwise.
    const diff: Record<string, unknown> = {};
    for (const key of Object.keys(settings) as (keyof AdminSettingsRead)[]) {
      if (key === "tenant_id") continue;
      if (JSON.stringify(settings[key]) === JSON.stringify(savedSettings[key])) continue;
      diff[key] = settings[key];
    }
    try {
      const res = await fetch(`/api/tenants/${tenantId}/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(diff),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error ?? "Save failed");
      setSavedSettings(data);
      setSettings(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSettingsSaving(false);
    }
  }

  async function toggleSuspend() {
    if (!tenant) return;
    const suspending = tenant.is_active;
    if (
      !(await confirm({
        title: suspending ? "Suspend tenant?" : "Reactivate tenant?",
        message: suspending
          ? "The tenant's dashboard login and bot will stop working until reactivated."
          : "The tenant's dashboard login and bot will work again.",
        danger: suspending,
        confirmLabel: suspending ? "Suspend" : "Reactivate",
      }))
    )
      return;
    setStatusBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/tenants/${tenantId}/${suspending ? "suspend" : "reactivate"}`, {
        method: "POST",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error ?? "Failed");
      setTenant((prev) => (prev ? { ...prev, ...data } : prev));
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setStatusBusy(false);
    }
  }

  async function resendInvite() {
    setInviteBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/tenants/${tenantId}/resend-invite`, { method: "POST" });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? "Failed to resend invite");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to resend invite");
    } finally {
      setInviteBusy(false);
    }
  }

  async function createKey() {
    setKeyBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/tenants/${tenantId}/api-keys`, { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error ?? "Failed to create key");
      const created = data as ApiKeyCreated;
      setKeys((prev) => [created, ...prev]);
      setNewSecret(created.secret);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create key");
    } finally {
      setKeyBusy(false);
    }
  }

  async function revokeKey(keyId: string) {
    if (!(await confirm({ title: "Revoke API key?", message: "Anything using this key will stop working immediately.", danger: true, confirmLabel: "Revoke" })))
      return;
    setKeyBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/tenants/${tenantId}/api-keys/${keyId}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error ?? "Failed to revoke key");
      setKeys((prev) => prev.map((k) => (k.id === keyId ? data : k)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to revoke key");
    } finally {
      setKeyBusy(false);
    }
  }

  return (
    <aside className="flex w-[440px] shrink-0 flex-col overflow-auto border-l border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border-subtle px-5 py-3.5">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">Tenant</span>
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
      {error && (
        <p className="m-5 rounded-lg bg-red-50 px-3 py-2 text-[12.5px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
          {error}
        </p>
      )}

      {tenant && !loading && (
        <>
          <div className="flex items-center gap-3 border-b border-border-subtle px-5 py-4">
            <div className="min-w-0 flex-1">
              <p className="truncate text-[14.5px] font-semibold text-text-primary">{tenant.name}</p>
              <p className="text-xs text-text-muted">{tenant.slug}</p>
            </div>
            <div className="flex flex-col items-end gap-1">
              <TenantStatusBadge isActive={tenant.is_active} />
              <ActivationBadge activated={tenant.activated} />
            </div>
          </div>

          <Section title="Profile">
            <Row label="Name">
              <Input value={profile.name} onChange={(e) => setProfile((p) => ({ ...p, name: e.target.value }))} />
            </Row>
            <Row label="Email">
              <Input
                type="email"
                value={profile.email}
                onChange={(e) => setProfile((p) => ({ ...p, email: e.target.value }))}
              />
            </Row>
            <Row label="Contact person">
              <Input
                value={profile.contact_person}
                onChange={(e) => setProfile((p) => ({ ...p, contact_person: e.target.value }))}
              />
            </Row>
            <Row label="Contact number">
              <Input
                value={profile.contact_number}
                onChange={(e) => setProfile((p) => ({ ...p, contact_number: e.target.value }))}
              />
            </Row>
            <Row label="Address">
              <Input value={profile.address} onChange={(e) => setProfile((p) => ({ ...p, address: e.target.value }))} />
            </Row>
            {tenant.admin_username && (
              <p className="text-[11.5px] text-text-muted">Dashboard login: {tenant.admin_username}</p>
            )}
            <div className="flex flex-wrap items-center gap-2">
              <Button size="sm" onClick={saveProfile} disabled={!profileDirty || profileSaving}>
                {profileSaving ? "Saving…" : "Save changes"}
              </Button>
              <Button
                size="sm"
                variant={tenant.is_active ? "danger" : "secondary"}
                onClick={toggleSuspend}
                disabled={statusBusy}
              >
                {tenant.is_active ? "Suspend" : "Reactivate"}
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={resendInvite}
                disabled={!tenant.is_active || inviteBusy}
                title={!tenant.is_active ? "Reactivate the tenant first" : undefined}
              >
                {inviteBusy ? "Sending…" : "Resend invite"}
              </Button>
            </div>
          </Section>

          {settings && (
            <Section title="Admin settings" description="Entitlements and platform limits for this tenant.">
              <Row
                label="Currency"
                hint="Changing this relabels existing order history -- orders store bare numbers with no currency of their own before this change."
              >
                <Input
                  value={settings.currency_code}
                  maxLength={3}
                  onChange={(e) => setSettings((s) => (s ? { ...s, currency_code: e.target.value.toUpperCase() } : s))}
                />
              </Row>

              {(Object.keys(ENTITLEMENT_LABELS) as (keyof AdminSettingsRead)[]).map((key) => (
                <ToggleRow
                  key={key}
                  label={ENTITLEMENT_LABELS[key]}
                  checked={Boolean(settings[key])}
                  onChange={(v) => setSettings((s) => (s ? { ...s, [key]: v } : s))}
                />
              ))}

              <div className="flex flex-col gap-1.5">
                <span className="text-[12.5px] font-medium text-text-secondary">Allowed channels</span>
                {KNOWN_CHANNELS.map((c: Channel) => (
                  <label key={c} className="flex items-center gap-2 text-[12.5px] text-text-primary">
                    <input
                      type="checkbox"
                      checked={settings.allowed_channels.includes(c)}
                      onChange={() =>
                        setSettings((s) =>
                          s
                            ? {
                                ...s,
                                allowed_channels: s.allowed_channels.includes(c)
                                  ? s.allowed_channels.filter((x) => x !== c)
                                  : [...s.allowed_channels, c],
                              }
                            : s,
                        )
                      }
                    />
                    {c}
                  </label>
                ))}
              </div>

              <Row label="LLM model" hint="Empty = platform default.">
                <Input
                  value={settings.llm_model ?? ""}
                  onChange={(e) => setSettings((s) => (s ? { ...s, llm_model: e.target.value || null } : s))}
                />
              </Row>
              <Row label="Monthly message limit" hint="Stored only -- not yet enforced. Empty = no limit.">
                <Input
                  type="number"
                  min="0"
                  value={settings.monthly_message_limit ?? ""}
                  onChange={(e) =>
                    setSettings((s) =>
                      s ? { ...s, monthly_message_limit: e.target.value === "" ? null : Number(e.target.value) } : s,
                    )
                  }
                />
              </Row>
              <Row label="Max documents" hint="Stored only -- not yet enforced. Empty = no limit.">
                <Input
                  type="number"
                  min="0"
                  value={settings.max_documents ?? ""}
                  onChange={(e) =>
                    setSettings((s) => (s ? { ...s, max_documents: e.target.value === "" ? null : Number(e.target.value) } : s))
                  }
                />
              </Row>

              <Button size="sm" onClick={saveSettings} disabled={!settingsDirty || settingsSaving}>
                {settingsSaving ? "Saving…" : "Save changes"}
              </Button>
            </Section>
          )}

          <Section title="API keys" description="Used by /bot/message callers (n8n, the website widget backend).">
            {newSecret && (
              <div className="flex flex-col gap-2 rounded-lg border border-accent bg-accent-soft p-3">
                <p className="text-[11.5px] font-medium text-accent-soft-fg">
                  Copy this now -- it won&apos;t be shown again.
                </p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 truncate rounded-md bg-surface px-2 py-1.5 text-[12px] text-text-primary">
                    {newSecret}
                  </code>
                  <button
                    type="button"
                    aria-label="Copy"
                    onClick={() => {
                      navigator.clipboard.writeText(newSecret).catch(() => {});
                      setCopied(true);
                      setTimeout(() => setCopied(false), 1500);
                    }}
                    className="rounded-md p-1.5 text-text-secondary hover:bg-surface-alt"
                  >
                    {copied ? <CheckIcon size={15} /> : <CopyIcon size={15} />}
                  </button>
                </div>
                <Button size="sm" variant="secondary" onClick={() => setNewSecret(null)}>
                  Done
                </Button>
              </div>
            )}

            {keys.length === 0 ? (
              <p className="text-[12.5px] text-text-muted">No API keys yet.</p>
            ) : (
              <div className="flex flex-col gap-2">
                {keys.map((k) => (
                  <div key={k.id} className="flex items-center justify-between gap-3 rounded-lg border border-border-subtle px-3 py-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <KeyIcon size={13} className="text-text-muted" />
                        <span className="truncate text-[12.5px] font-medium text-text-primary">{k.key_prefix}…</span>
                      </div>
                      <p className="text-[11px] text-text-muted">
                        {k.key_type} · created {formatDateTime(k.created_at)}
                        {k.revoked_at && ` · revoked ${formatDateTime(k.revoked_at)}`}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <ApiKeyStatusBadge revokedAt={k.revoked_at} />
                      {!k.revoked_at && (
                        <Button size="sm" variant="danger" onClick={() => revokeKey(k.id)} disabled={keyBusy}>
                          Revoke
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <Button size="sm" variant="secondary" onClick={createKey} disabled={keyBusy}>
              {keyBusy ? "Creating…" : "Create key"}
            </Button>
          </Section>
        </>
      )}
    </aside>
  );
}
