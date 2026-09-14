"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { VariantRow } from "@/components/catalog/VariantRow";
import { PlusIcon } from "@/components/icons";
import { Button } from "@/components/ui/Button";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { flattenTree } from "@/lib/catalog-tree";
import type { CategoryTreeNode, ProductWithVariants, StockStatus, Variant } from "@/lib/types";

const STOCK_OPTIONS: { value: StockStatus; label: string }[] = [
  { value: "in_stock", label: "In stock" },
  { value: "out_of_stock", label: "Out of stock" },
  { value: "unlimited", label: "Unlimited" },
];

function AddVariantForm({
  productId,
  onAdd,
  onCancel,
}: {
  productId: string;
  onAdd: (v: Variant) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [sku, setSku] = useState("");
  const [price, setPrice] = useState("");
  const [stockStatus, setStockStatus] = useState<StockStatus>("in_stock");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/tenant/products/${productId}/variants`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, sku: sku || null, price, stock_status: stockStatus }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error ?? "Could not add the variant.");
      onAdd(data as Variant);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add the variant.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={submit}
      className="grid grid-cols-[1.4fr_1fr_0.8fr_1fr_auto] items-center gap-2 border-t border-border-subtle bg-surface-alt/40 px-5 py-2.5"
    >
      <Input
        autoFocus
        placeholder="Variant name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
        className="!py-1.5 text-[12.5px]"
      />
      <Input
        placeholder="SKU"
        value={sku}
        onChange={(e) => setSku(e.target.value)}
        className="!py-1.5 text-[12.5px]"
      />
      <Input
        type="number"
        min="0"
        step="0.01"
        placeholder="0.00"
        value={price}
        onChange={(e) => setPrice(e.target.value)}
        required
        className="!py-1.5 text-[12.5px]"
      />
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
      <div className="flex items-center gap-1">
        <Button type="submit" size="sm" disabled={saving}>
          {saving ? "…" : "Add"}
        </Button>
        <Button type="button" size="sm" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
      </div>
      {error && <p className="col-span-5 text-[11.5px] text-red-600 dark:text-red-400">{error}</p>}
    </form>
  );
}

export function ProductDetailPanel({
  productId,
  tree,
  onClose,
  onDeleted,
}: {
  productId: string;
  tree: CategoryTreeNode[];
  onClose: () => void;
  onDeleted: () => void;
}) {
  const router = useRouter();
  const confirm = useConfirm();
  const [product, setProduct] = useState<ProductWithVariants | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [addingVariant, setAddingVariant] = useState(false);

  const categories = flattenTree(tree);

  // This panel is keyed on `productId` by the parent, so it remounts (fresh
  // state) whenever the selection changes.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/tenant/products/${productId}`);
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? "Failed to load");
        const data = (await res.json()) as ProductWithVariants;
        if (cancelled) return;
        setProduct(data);
        setName(data.name);
        setCategoryId(data.category_id ?? "");
        setDescription(data.description ?? "");
      } catch (e) {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [productId]);

  async function saveProduct() {
    if (!product) return;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`/api/tenant/products/${product.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          category_id: categoryId || null,
          description: description || null,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error ?? "Could not save the product.");
      setProduct((p) => (p ? { ...p, ...data } : p));
      setEditing(false);
      router.refresh(); // reflect the (possibly new) name/category in the tree
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the product.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteProduct() {
    if (!product) return;
    const ok = await confirm({
      title: "Delete product",
      message: `Delete "${product.name}" and all its variants? This can't be undone.`,
      confirmLabel: "Delete",
      danger: true,
    });
    if (!ok) return;
    const res = await fetch(`/api/tenant/products/${product.id}`, { method: "DELETE" });
    if (!res.ok) {
      setError((await res.json().catch(() => ({}))).error ?? "Could not delete the product.");
      return;
    }
    onDeleted();
  }

  return (
    <aside className="flex h-full min-w-0 flex-1 flex-col overflow-auto border-l border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border-subtle px-5 py-3.5">
        <span className="truncate text-[13.5px] font-semibold text-text-primary">
          {product?.name ?? "Product"}
        </span>
        <div className="flex items-center gap-1">
          {product && (
            <Button variant="danger" size="sm" onClick={deleteProduct}>
              Delete
            </Button>
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1.5 text-text-muted hover:bg-surface-alt hover:text-text-primary"
          >
            <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {loading && <p className="p-5 text-[12.5px] text-text-muted">Loading…</p>}
      {loadError && !loading && (
        <p className="m-5 rounded-lg bg-red-50 px-3 py-2 text-[12.5px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
          {loadError}
        </p>
      )}

      {product && !loading && (
        <div className="flex flex-col gap-5 p-5">
          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-[12.5px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
              {error}
            </p>
          )}

          <section className="rounded-xl border border-border bg-surface p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-[13.5px] font-semibold text-text-primary">Product details</h2>
              {!editing && (
                <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
                  Edit
                </Button>
              )}
            </div>

            {editing ? (
              <div className="flex flex-col gap-3">
                <Field label="Name">
                  <Input value={name} onChange={(e) => setName(e.target.value)} />
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
                <Field label="Description">
                  <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
                </Field>
                <div className="flex justify-end gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => {
                      setEditing(false);
                      setName(product.name);
                      setCategoryId(product.category_id ?? "");
                      setDescription(product.description ?? "");
                    }}
                  >
                    Cancel
                  </Button>
                  <Button size="sm" onClick={saveProduct} disabled={saving}>
                    {saving ? "Saving…" : "Save"}
                  </Button>
                </div>
              </div>
            ) : (
              <dl className="flex flex-col gap-2 text-[13px]">
                <div className="flex justify-between">
                  <dt className="text-text-muted">Category</dt>
                  <dd className="text-text-primary">
                    {product.category_id
                      ? (categories.find((c) => c.id === product.category_id)?.name ?? "—")
                      : "Uncategorized"}
                  </dd>
                </div>
                <div className="flex flex-col gap-1">
                  <dt className="text-text-muted">Description</dt>
                  <dd className="text-text-primary">{product.description || "—"}</dd>
                </div>
              </dl>
            )}
          </section>

          <section className="overflow-hidden rounded-xl border border-border bg-surface">
            <div className="flex items-center justify-between border-b border-border-subtle px-5 py-3.5">
              <h2 className="text-[13.5px] font-semibold text-text-primary">Variants</h2>
              {!addingVariant && (
                <button
                  type="button"
                  onClick={() => setAddingVariant(true)}
                  className="flex items-center gap-1 text-[12.5px] font-semibold text-accent hover:underline"
                >
                  <PlusIcon size={13} />
                  Add variant
                </button>
              )}
            </div>

            <div className="grid grid-cols-[1.4fr_1fr_0.8fr_1fr_0.7fr_auto] gap-2 px-5 py-2 text-[11px] uppercase tracking-wide text-text-muted">
              <div>Name</div>
              <div>SKU</div>
              <div>Price</div>
              <div>Stock</div>
              <div>Active</div>
              <div />
            </div>

            {product.variants.map((v) => (
              <VariantRow
                key={v.id}
                productId={product.id}
                variant={v}
                onChange={(updated) =>
                  setProduct((p) =>
                    p
                      ? { ...p, variants: p.variants.map((x) => (x.id === updated.id ? updated : x)) }
                      : p,
                  )
                }
                onDelete={(id) =>
                  setProduct((p) => (p ? { ...p, variants: p.variants.filter((x) => x.id !== id) } : p))
                }
              />
            ))}

            {addingVariant && (
              <AddVariantForm
                productId={product.id}
                onAdd={(v) => {
                  setProduct((p) => (p ? { ...p, variants: [...p.variants, v] } : p));
                  setAddingVariant(false);
                }}
                onCancel={() => setAddingVariant(false)}
              />
            )}
          </section>
        </div>
      )}
    </aside>
  );
}
