"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { Topbar } from "@/components/Topbar";
import { Button } from "@/components/ui/Button";
import { Input, Select, Textarea } from "@/components/ui/Field";
import { TagInput } from "@/components/ui/TagInput";
import { Toggle } from "@/components/ui/Toggle";
import type {
  BotTone,
  NegotiationMode,
  OrderConfirmationMode,
  TenantCapabilities,
  TenantSettings,
  TenantSettingsResponse,
} from "@/lib/types";

const CUSTOM_INSTRUCTIONS_MAX = 2000;

function Section({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-border bg-surface">
      <div className="border-b border-border-subtle px-5 py-3.5">
        <h2 className="text-[13.5px] font-semibold text-text-primary">{title}</h2>
        {description && <p className="mt-0.5 text-[12px] text-text-muted">{description}</p>}
      </div>
      <div className="flex flex-col divide-y divide-border-subtle">{children}</div>
    </section>
  );
}

function Row({
  label,
  hint,
  children,
  stacked,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
  stacked?: boolean;
}) {
  return (
    <div className={`flex gap-4 px-5 py-3.5 ${stacked ? "flex-col" : "items-center justify-between"}`}>
      <div className="min-w-0">
        <p className="text-[13px] font-medium text-text-primary">{label}</p>
        {hint && <p className="mt-0.5 text-[12px] text-text-muted">{hint}</p>}
      </div>
      <div className={stacked ? "w-full" : "w-[280px] shrink-0"}>{children}</div>
    </div>
  );
}

function ToggleRow({
  label,
  hint,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-4 px-5 py-3.5">
      <div className="min-w-0">
        <p className="text-[13px] font-medium text-text-primary">{label}</p>
        {hint && <p className="mt-0.5 text-[12px] text-text-muted">{hint}</p>}
      </div>
      <Toggle label={label} checked={checked} onChange={onChange} disabled={disabled} />
    </div>
  );
}

const NOT_INCLUDED = "Not included in your plan";

export function SettingsView({ initial }: { initial: TenantSettingsResponse }) {
  const router = useRouter();
  const capabilities: TenantCapabilities = initial.capabilities;
  const [saved, setSaved] = useState<TenantSettings>(initial.settings);
  const [form, setForm] = useState<TenantSettings>(initial.settings);
  const [saving, setSaving] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof TenantSettings>(key: K, value: TenantSettings[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setJustSaved(false);
  }

  // Only the fields that actually changed are sent (the backend PATCH only
  // touches what it receives).
  const changes = useMemo(() => {
    const diff: Record<string, unknown> = {};
    for (const key of Object.keys(form) as (keyof TenantSettings)[]) {
      if (JSON.stringify(form[key]) !== JSON.stringify(saved[key])) diff[key] = form[key];
    }
    return diff;
  }, [form, saved]);
  const dirty = Object.keys(changes).length > 0;

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/tenant/settings", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(changes),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error ?? "Could not save settings.");
      const next = (data as TenantSettingsResponse).settings;
      setSaved(next);
      setForm(next);
      setJustSaved(true);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save settings.");
    } finally {
      setSaving(false);
    }
  }

  const timezones =
    typeof Intl !== "undefined" && "supportedValuesOf" in Intl
      ? (Intl as unknown as { supportedValuesOf: (k: string) => string[] }).supportedValuesOf("timeZone")
      : [];
  const instructionsLen = (form.custom_instructions ?? "").length;

  return (
    <>
      <Topbar
        title="Settings"
        actions={
          <div className="flex items-center gap-3">
            {justSaved && !dirty && <span className="text-[12px] text-positive">Saved</span>}
            <Button size="sm" onClick={save} disabled={!dirty || saving}>
              {saving ? "Saving…" : "Save changes"}
            </Button>
          </div>
        }
      />
      <div className="flex-1 overflow-auto">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-7 py-6">
          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-[12.5px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
              {error}
            </p>
          )}

          <Section title="Business & assistant" description="How your assistant presents itself and what it knows about your business.">
            <ToggleRow
              label="Assistant replies to customers"
              hint="Turn off to take over conversations yourself. Messages are still saved and visible in Conversations."
              checked={form.bot_enabled}
              onChange={(v) => set("bot_enabled", v)}
            />
            <Row label="Timezone" hint="Used to understand “today”, “tonight” and pickup times.">
              <Input list="timezones" value={form.timezone} onChange={(e) => set("timezone", e.target.value)} />
              <datalist id="timezones">
                {timezones.map((tz) => (
                  <option key={tz} value={tz} />
                ))}
              </datalist>
            </Row>
            <Row label="Assistant name" hint="Optional.">
              <Input
                value={form.bot_name ?? ""}
                placeholder="e.g. Dula"
                onChange={(e) => set("bot_name", e.target.value === "" ? null : e.target.value)}
              />
            </Row>
            <Row label="Tone">
              <Select value={form.tone} onChange={(e) => set("tone", e.target.value as BotTone)}>
                <option value="friendly">Friendly</option>
                <option value="casual">Casual</option>
                <option value="formal">Formal</option>
              </Select>
            </Row>
            <Row label="Language" hint="The language it replies in.">
              <Input value={form.language} onChange={(e) => set("language", e.target.value)} />
            </Row>
            <Row label="Welcome message" hint="Used when a customer opens with a greeting." stacked>
              <Textarea
                value={form.welcome_message ?? ""}
                onChange={(e) => set("welcome_message", e.target.value === "" ? null : e.target.value)}
              />
            </Row>
            <Row label="Fallback message" hint="Sent if the assistant hits an error and can't answer." stacked>
              <Textarea
                value={form.fallback_message ?? ""}
                onChange={(e) => set("fallback_message", e.target.value === "" ? null : e.target.value)}
              />
            </Row>
            <Row
              label="Custom instructions"
              hint="Extra guidance for your assistant (e.g. “We're closed on Sundays”). It can never override pricing, payment, or order-confirmation rules."
              stacked
            >
              <Textarea
                value={form.custom_instructions ?? ""}
                maxLength={CUSTOM_INSTRUCTIONS_MAX}
                className="min-h-28"
                onChange={(e) => set("custom_instructions", e.target.value === "" ? null : e.target.value)}
              />
              <p className="mt-1 text-right text-[11px] text-text-muted">
                {instructionsLen}/{CUSTOM_INSTRUCTIONS_MAX}
              </p>
            </Row>
          </Section>

          <Section title="What the assistant can do" description="Switch off anything you don't want it to handle.">
            <ToggleRow
              label="Answer from the knowledge base"
              checked={form.documents_enabled && capabilities.documents_allowed}
              disabled={!capabilities.documents_allowed}
              hint={capabilities.documents_allowed ? undefined : NOT_INCLUDED}
              onChange={(v) => set("documents_enabled", v)}
            />
            <ToggleRow
              label="Show the catalog and prices"
              checked={form.catalog_enabled && capabilities.catalog_allowed}
              disabled={!capabilities.catalog_allowed}
              hint={capabilities.catalog_allowed ? undefined : NOT_INCLUDED}
              onChange={(v) => set("catalog_enabled", v)}
            />
            <ToggleRow
              label="Capture leads"
              checked={form.leads_enabled && capabilities.leads_allowed}
              disabled={!capabilities.leads_allowed}
              hint={capabilities.leads_allowed ? undefined : NOT_INCLUDED}
              onChange={(v) => set("leads_enabled", v)}
            />
            <ToggleRow
              label="Take orders"
              checked={form.ordering_enabled && capabilities.ordering_allowed}
              disabled={!capabilities.ordering_allowed}
              hint={
                capabilities.ordering_allowed
                  ? "Off = the assistant can't place orders and just captures the customer's interest."
                  : NOT_INCLUDED
              }
              onChange={(v) => set("ordering_enabled", v)}
            />
          </Section>

          <Section title="Ordering & delivery" description="Rules applied before an order can be submitted.">
            <ToggleRow label="Offer delivery" checked={form.delivery_enabled} onChange={(v) => set("delivery_enabled", v)} />
            <ToggleRow label="Offer pickup" checked={form.pickup_enabled} onChange={(v) => set("pickup_enabled", v)} />
            <ToggleRow
              label="Cash on delivery"
              hint="The assistant will tell customers delivery orders are paid in cash on delivery. It never collects payment details."
              checked={form.cash_on_delivery}
              disabled={!form.delivery_enabled}
              onChange={(v) => set("cash_on_delivery", v)}
            />
            <Row label={`Minimum order value (${capabilities.currency_code})`} hint="Leave empty for no minimum.">
              <Input
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                value={form.min_order_value ?? ""}
                onChange={(e) => set("min_order_value", e.target.value === "" ? null : e.target.value)}
              />
            </Row>
            <Row label="Order confirmation" hint="Who confirms an order once the customer agrees.">
              <Select
                value={form.order_confirmation_mode}
                onChange={(e) => set("order_confirmation_mode", e.target.value as OrderConfirmationMode)}
              >
                <option value="bot">Assistant places it automatically</option>
                <option value="human">I confirm each order (Orders → Pending)</option>
              </Select>
            </Row>
            <Row label="Price negotiation" hint="What happens when a customer asks for a discount.">
              <Select value={form.negotiation_mode} onChange={(e) => set("negotiation_mode", e.target.value as NegotiationMode)}>
                <option value="fixed">Prices are fixed</option>
                <option value="escalate">Pass the request to me</option>
              </Select>
            </Row>
          </Section>

          <Section title="Notifications" description="Email alerts when the assistant captures a lead or receives an order.">
            <Row label="Send alerts to" hint="Empty = your account email." stacked>
              <TagInput
                tags={form.notify_emails}
                onChange={(tags) => set("notify_emails", tags)}
                placeholder="Add an email and press Enter"
              />
            </Row>
            <ToggleRow label="New leads" checked={form.notify_new_lead} onChange={(v) => set("notify_new_lead", v)} />
            <ToggleRow label="New orders" checked={form.notify_new_order} onChange={(v) => set("notify_new_order", v)} />
          </Section>

          <Section title="Your plan" description="Set by the platform administrator — contact support to change these.">
            <Row label="Currency">
              <p className="text-[13px] font-medium text-text-primary">{capabilities.currency_code}</p>
            </Row>
          </Section>
        </div>
      </div>
    </>
  );
}
