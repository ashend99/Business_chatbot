"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { flattenTree } from "@/lib/catalog-tree";
import type {
  CategoryAttribute,
  CategoryTreeNode,
  ProductWithVariants,
  StockStatus,
  VariantInput,
} from "@/lib/types";

const STOCK_OPTIONS: { value: StockStatus; label: string }[] = [
  { value: "in_stock", label: "In stock" },
  { value: "out_of_stock", label: "Out of stock" },
  { value: "unlimited", label: "Unlimited (made to order)" },
];

/** Stable key for a choice combination, so per-row edits survive re-renders
 * when other checkboxes change (only the affected rows appear/disappear). */
function comboKey(combo: Record<string, string>): string {
  return Object.entries(combo)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${v}`)
    .join("|");
}

type RowData = { price: string };
const EMPTY_ROW: RowData = { price: "" };

export function AddProductModal({
  tree,
  defaultCategoryId,
  onClose,
  onCreated,
}: {
  tree: CategoryTreeNode[];
  defaultCategoryId: string | null;
  onClose: () => void;
  onCreated: (productId: string) => void;
}) {
  const categories = flattenTree(tree);

  const [name, setName] = useState("");
  const [categoryId, setCategoryId] = useState(defaultCategoryId ?? "");
  const [description, setDescription] = useState("");

  const [attributes, setAttributes] = useState<CategoryAttribute[]>([]);
  const [loadingAttrs, setLoadingAttrs] = useState(false);
  const [checked, setChecked] = useState<Record<string, Set<string>>>({});
  const [rowData, setRowData] = useState<Record<string, RowData>>({});

  // Simple single-price fields, used when the category offers no attributes
  // (or none are checked).
  const [simplePrice, setSimplePrice] = useState("");
  const [simpleSku, setSimpleSku] = useState("");
  const [simpleStock, setSimpleStock] = useState<StockStatus>("in_stock");

  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Load this category's effective (inherited + own) attributes whenever it changes.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!categoryId) {
        if (!cancelled) {
          setAttributes([]);
          setChecked({});
        }
        return;
      }
      setLoadingAttrs(true);
      try {
        const res = await fetch(`/api/tenant/categories/${categoryId}/effective-attributes`);
        const attrs: CategoryAttribute[] = res.ok ? await res.json() : [];
        if (cancelled) return;
        setAttributes(attrs);
        const initial: Record<string, Set<string>> = {};
        for (const a of attrs) initial[a.name] = new Set(a.choices);
        setChecked(initial);
      } finally {
        if (!cancelled) setLoadingAttrs(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [categoryId]);

  function toggleChoice(attrName: string, choice: string) {
    setChecked((c) => {
      const next = new Set(c[attrName] ?? []);
      if (next.has(choice)) next.delete(choice);
      else next.add(choice);
      return { ...c, [attrName]: next };
    });
  }

  // Cartesian product of the checked choices, skipping any attribute with
  // nothing checked (that's how you opt an inherited attribute out). Choice
  // order always follows the attribute's own `choices` list -- not check/
  // uncheck history -- so re-checking one never reshuffles the rows.
  const combinations = useMemo(() => {
    let combos: Record<string, string>[] = [{}];
    for (const attr of attributes) {
      const choices = attr.choices.filter((choice) => checked[attr.name]?.has(choice));
      if (choices.length === 0) continue;
      combos = combos.flatMap((combo) => choices.map((choice) => ({ ...combo, [attr.name]: choice })));
    }
    return combos.filter((c) => Object.keys(c).length > 0);
  }, [attributes, checked]);

  function updateRow(key: string, patch: Partial<RowData>) {
    setRowData((d) => ({ ...d, [key]: { ...(d[key] ?? EMPTY_ROW), ...patch } }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    let variants: VariantInput[];
    if (combinations.length > 0) {
      const missing = combinations.find((c) => !rowData[comboKey(c)]?.price);
      if (missing) {
        setError("Set a price for every variant below.");
        return;
      }
      variants = combinations.map((c) => ({
        name: Object.values(c).join(" / "),
        price: rowData[comboKey(c)].price,
        attribute_values: c,
      }));
    } else {
      if (!simplePrice) {
        setError("Set a price.");
        return;
      }
      variants = [{ name, price: simplePrice, sku: simpleSku || null, stock_status: simpleStock }];
    }

    setSaving(true);
    try {
      const res = await fetch("/api/tenant/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          category_id: categoryId || null,
          description: description || null,
          variants,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.error ?? "Could not create the product.");
        return;
      }
      const product = body as ProductWithVariants;
      onClose();
      onCreated(product.id);
    } catch {
      setError("Could not reach the server. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title="Add product" onClose={onClose} width={720} height={620}>
      <form onSubmit={onSubmit} className="flex flex-col gap-3.5">
        {error && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-[12.5px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
            {error}
          </p>
        )}

        <Field label="Name">
          <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} required />
        </Field>

        <Field label="Category">
          <Select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">Uncategorized</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {"—".repeat(c.depth)} {c.name}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Description" hint="Optional">
          <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
        </Field>

        {loadingAttrs && <p className="text-[12.5px] text-text-muted">Loading category attributes…</p>}

        {!loadingAttrs && attributes.length > 0 && (
          <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface-alt/40 p-3.5">
            <p className="text-[11.5px] text-text-muted">
              Uncheck a choice to leave it out of this product.
            </p>
            {attributes.map((attr) => (
              <div key={attr.id}>
                <p className="mb-1.5 text-[12.5px] font-semibold text-text-primary">{attr.name}</p>
                <div className="flex flex-wrap gap-1.5">
                  {attr.choices.map((choice) => {
                    const isChecked = checked[attr.name]?.has(choice) ?? false;
                    return (
                      <button
                        key={choice}
                        type="button"
                        onClick={() => toggleChoice(attr.name, choice)}
                        className={`rounded-full border px-2.5 py-1 text-[12px] transition-colors ${
                          isChecked
                            ? "border-accent bg-accent-soft font-medium text-accent"
                            : "border-border text-text-muted hover:bg-surface-alt"
                        }`}
                      >
                        {choice}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}

        {!loadingAttrs && combinations.length > 0 && (
          <div className="overflow-hidden rounded-xl border border-border">
            <div className="grid grid-cols-[1.5fr_1fr] gap-2 bg-surface-alt px-3 py-2 text-[11px] uppercase tracking-wide text-text-muted">
              <div>Variant</div>
              <div>Price</div>
            </div>
            <div className="max-h-56 overflow-y-auto">
              {combinations.map((c) => {
                const key = comboKey(c);
                const data = rowData[key] ?? EMPTY_ROW;
                return (
                  <div
                    key={key}
                    className="grid grid-cols-[1.5fr_1fr] items-center gap-2 border-t border-border-subtle px-3 py-2"
                  >
                    <span className="text-[12.5px] text-text-primary">{Object.values(c).join(" / ")}</span>
                    <Input
                      type="number"
                      min="0"
                      step="0.01"
                      placeholder="0.00"
                      value={data.price}
                      onChange={(e) => updateRow(key, { price: e.target.value })}
                      className="!py-1.5 text-[12.5px]"
                    />
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {!loadingAttrs && combinations.length === 0 && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Price">
              <Input
                type="number"
                min="0"
                step="0.01"
                placeholder="0.00"
                value={simplePrice}
                onChange={(e) => setSimplePrice(e.target.value)}
                required
              />
            </Field>
            <Field label="SKU" hint="Optional">
              <Input value={simpleSku} onChange={(e) => setSimpleSku(e.target.value)} />
            </Field>
            <div className="col-span-2">
              <Field label="Stock">
                <Select value={simpleStock} onChange={(e) => setSimpleStock(e.target.value as StockStatus)}>
                  {STOCK_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
          </div>
        )}

        <div className="mt-1 flex justify-end gap-2">
          <Button type="button" variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" disabled={saving}>
            {saving ? "Creating…" : "Create product"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
