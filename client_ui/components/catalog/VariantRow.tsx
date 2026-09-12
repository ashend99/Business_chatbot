"use client";

import { useState } from "react";

import { PencilIcon, TrashIcon } from "@/components/icons";
import { Button } from "@/components/ui/Button";
import { Input, Select } from "@/components/ui/Field";
import { formatMoney } from "@/lib/format";
import type { StockStatus, Variant } from "@/lib/types";

const STOCK_OPTIONS: { value: StockStatus; label: string }[] = [
  { value: "in_stock", label: "In stock" },
  { value: "out_of_stock", label: "Out of stock" },
  { value: "unlimited", label: "Unlimited" },
];

const STOCK_BADGE: Record<StockStatus, string> = {
  in_stock: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-400",
  out_of_stock: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-400",
  unlimited: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
};
const STOCK_LABEL: Record<StockStatus, string> = {
  in_stock: "In stock",
  out_of_stock: "Out of stock",
  unlimited: "Unlimited",
};

async function patchVariant(productId: string, variantId: string, body: unknown) {
  const res = await fetch(`/api/tenant/products/${productId}/variants/${variantId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error ?? "Could not update the variant.");
  return data as Variant;
}

export function VariantRow({
  productId,
  variant,
  onChange,
  onDelete,
}: {
  productId: string;
  variant: Variant;
  onChange: (v: Variant) => void;
  onDelete: (id: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(variant.name);
  const [sku, setSku] = useState(variant.sku ?? "");
  const [price, setPrice] = useState(variant.price);
  const [stockStatus, setStockStatus] = useState<StockStatus>(variant.stock_status);
  const [stockQty, setStockQty] = useState(variant.stock_qty?.toString() ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const updated = await patchVariant(productId, variant.id, {
        name,
        sku: sku || null,
        price,
        stock_status: stockStatus,
        stock_qty: stockQty === "" ? null : Number(stockQty),
      });
      onChange(updated);
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update the variant.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive() {
    try {
      const updated = await patchVariant(productId, variant.id, { active: !variant.active });
      onChange(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update the variant.");
    }
  }

  async function remove() {
    if (!confirm(`Delete variant "${variant.name}"?`)) return;
    try {
      const res = await fetch(`/api/tenant/products/${productId}/variants/${variant.id}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? "Could not delete.");
      onDelete(variant.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not delete the variant.");
    }
  }

  if (editing) {
    return (
      <div className="grid grid-cols-[1.4fr_1fr_0.8fr_1fr_0.7fr_auto] items-center gap-2 border-b border-border-subtle px-5 py-2.5">
        <Input value={name} onChange={(e) => setName(e.target.value)} className="!py-1.5 text-[12.5px]" />
        <Input value={sku} onChange={(e) => setSku(e.target.value)} placeholder="SKU" className="!py-1.5 text-[12.5px]" />
        <Input
          type="number"
          min="0"
          step="0.01"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          className="!py-1.5 text-[12.5px]"
        />
        <div className="flex items-center gap-1.5">
          <Select
            value={stockStatus}
            onChange={(e) => setStockStatus(e.target.value as StockStatus)}
            className="!py-1.5 text-[12.5px]"
          >
            {STOCK_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </div>
        <Input
          type="number"
          min="0"
          placeholder="Qty"
          value={stockQty}
          onChange={(e) => setStockQty(e.target.value)}
          className="!py-1.5 text-[12.5px]"
        />
        <div className="flex items-center gap-1">
          <Button size="sm" onClick={save} disabled={saving}>
            {saving ? "…" : "Save"}
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </div>
        {error && (
          <p className="col-span-6 text-[11.5px] text-red-600 dark:text-red-400">{error}</p>
        )}
      </div>
    );
  }

  return (
    <div
      className={`grid grid-cols-[1.4fr_1fr_0.8fr_1fr_0.7fr_auto] items-center gap-2 border-b border-border-subtle px-5 py-2.5 last:border-b-0 ${
        variant.active ? "" : "opacity-50"
      }`}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[13px] font-medium text-text-primary">{variant.name}</span>
        {variant.attribute_values &&
          Object.entries(variant.attribute_values).map(([k, v]) => (
            <span
              key={k}
              className="rounded-full bg-surface-alt px-1.5 py-0.5 text-[10.5px] text-text-muted"
              title={k}
            >
              {v}
            </span>
          ))}
      </div>
      <span className="text-[12.5px] text-text-muted">{variant.sku || "—"}</span>
      <span className="text-[12.5px] text-text-primary">{formatMoney(variant.price)}</span>
      <div>
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${STOCK_BADGE[variant.stock_status]}`}
        >
          {STOCK_LABEL[variant.stock_status]}
          {variant.stock_qty != null ? ` (${variant.stock_qty})` : ""}
        </span>
      </div>
      <button
        type="button"
        onClick={toggleActive}
        role="switch"
        aria-checked={variant.active}
        title={variant.active ? "Active — click to deactivate" : "Inactive — click to activate"}
        className={`relative h-[18px] w-8 rounded-full transition-colors ${
          variant.active ? "bg-accent" : "border border-border bg-surface-alt"
        }`}
      >
        <span
          className={`absolute top-[2px] h-[13px] w-[13px] rounded-full bg-white transition-all ${
            variant.active ? "right-[2px]" : "left-[2px] bg-text-muted"
          }`}
        />
      </button>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => setEditing(true)}
          title="Edit"
          className="rounded p-1.5 text-text-muted hover:bg-surface-alt hover:text-text-primary"
        >
          <PencilIcon size={14} />
        </button>
        <button
          type="button"
          onClick={remove}
          title="Delete"
          className="rounded p-1.5 text-text-muted hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40 dark:hover:text-red-400"
        >
          <TrashIcon size={14} />
        </button>
      </div>
      {error && <p className="col-span-6 text-[11.5px] text-red-600 dark:text-red-400">{error}</p>}
    </div>
  );
}
