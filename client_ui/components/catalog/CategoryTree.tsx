"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { CategoryAttributesModal } from "@/components/catalog/CategoryAttributesModal";
import { CatalogIcon, ChevronDownIcon, MoreIcon, PlusIcon } from "@/components/icons";
import { flattenTree } from "@/lib/catalog-tree";
import type { CategoryTreeNode, Product } from "@/lib/types";

async function apiCall(path: string, method: string, body?: unknown) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error ?? "Request failed");
  }
}

function InlineNameForm({
  defaultValue = "",
  placeholder,
  indent,
  onSubmit,
  onCancel,
}: {
  defaultValue?: string;
  placeholder?: string;
  indent: number;
  onSubmit: (name: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(defaultValue);
  return (
    <form
      style={{ paddingLeft: indent * 14 + 8 }}
      className="flex items-center gap-1.5 py-1"
      onSubmit={(e) => {
        e.preventDefault();
        const trimmed = value.trim();
        if (trimmed) onSubmit(trimmed);
        else onCancel();
      }}
    >
      <input
        autoFocus
        value={value}
        placeholder={placeholder}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && onCancel()}
        onBlur={onCancel}
        className="w-full rounded-md border border-accent bg-surface px-2 py-1 text-[12.5px] text-text-primary focus:outline-none"
      />
    </form>
  );
}

function MovePicker({
  tree,
  nodeId,
  indent,
  onPick,
  onCancel,
}: {
  tree: CategoryTreeNode[];
  nodeId: string;
  indent: number;
  onPick: (parentId: string | null) => void;
  onCancel: () => void;
}) {
  const options = flattenTree(tree, 0, nodeId);
  return (
    <div style={{ paddingLeft: indent * 14 + 8 }} className="flex items-center gap-1.5 py-1">
      <select
        autoFocus
        defaultValue=""
        onChange={(e) => onPick(e.target.value === "" ? null : e.target.value)}
        onBlur={onCancel}
        className="w-full rounded-md border border-accent bg-surface px-2 py-1 text-[12.5px] text-text-primary focus:outline-none"
      >
        <option value="" disabled>
          Move to…
        </option>
        <option value="">Top level</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {"—".repeat(o.depth)} {o.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function ProductRow({
  product,
  depth,
  active,
  onSelect,
}: {
  product: Product;
  depth: number;
  active: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(product.id)}
      style={{ paddingLeft: depth * 14 + 8 }}
      className={`flex h-7 w-full items-center gap-1.5 rounded-lg pr-1.5 text-left ${
        active ? "bg-accent-soft text-accent" : "text-text-secondary"
      }`}
    >
      <span className="inline-block w-[13px]" />
      <CatalogIcon size={13} className={`shrink-0 ${active ? "text-accent" : "text-text-muted"}`} />
      <span className="min-w-0 flex-1 truncate text-[13px]">{product.name}</span>
    </button>
  );
}

type Mode = "view" | "rename" | "addChild" | "move";

function CategoryNode({
  node,
  depth,
  rootTree,
  products,
  selectedId,
  onSelect,
  selectedProductId,
  onSelectProduct,
  onMutate,
  onManageAttributes,
  setError,
}: {
  node: CategoryTreeNode;
  depth: number;
  rootTree: CategoryTreeNode[];
  products: Product[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  selectedProductId: string | null;
  onSelectProduct: (id: string) => void;
  onMutate: () => void;
  onManageAttributes: (node: CategoryTreeNode) => void;
  setError: (msg: string | null) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const [mode, setMode] = useState<Mode>("view");
  const [menuOpen, setMenuOpen] = useState(false);
  const ownProducts = products.filter((p) => p.category_id === node.id);
  const hasChildren = node.children.length > 0 || ownProducts.length > 0;
  const active = selectedId === node.id;

  async function run(action: () => Promise<void>) {
    try {
      setError(null);
      await action();
      onMutate();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    }
  }

  if (mode === "rename") {
    return (
      <InlineNameForm
        defaultValue={node.name}
        indent={depth}
        onSubmit={(name) => {
          setMode("view");
          run(() => apiCall(`/api/tenant/categories/${node.id}`, "PATCH", { name }));
        }}
        onCancel={() => setMode("view")}
      />
    );
  }

  return (
    <div>
      <div
        className="flex h-7 items-center gap-1 rounded-lg pr-1.5"
        style={{ paddingLeft: depth * 14 + 8 }}
      >
        {hasChildren ? (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-text-muted"
            aria-label={expanded ? "Collapse" : "Expand"}
          >
            <ChevronDownIcon size={13} className={expanded ? "" : "-rotate-90"} />
          </button>
        ) : (
          <span className="inline-block w-[13px]" />
        )}

        <button
          type="button"
          onClick={() => onSelect(node.id)}
          className={`min-w-0 flex-1 truncate text-left text-[13px] ${
            active ? "font-semibold text-accent" : "text-text-primary"
          }`}
        >
          {node.name}
        </button>

        <div className="flex items-center gap-0.5">
          <button
            type="button"
            title="Add subcategory"
            onClick={() => setMode("addChild")}
            className="rounded p-1 text-text-muted"
          >
            <PlusIcon size={13} />
          </button>
          <div className="relative">
            <button
              type="button"
              title="More"
              onClick={() => setMenuOpen((v) => !v)}
              className="rounded p-1 text-text-muted"
            >
              <MoreIcon size={13} />
            </button>
            {menuOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                <div className="absolute right-0 z-20 mt-1 w-44 rounded-lg border border-border bg-surface p-1 shadow-lg">
                  <button
                    type="button"
                    onClick={() => {
                      setMode("rename");
                      setMenuOpen(false);
                    }}
                    className="block w-full rounded px-2 py-1.5 text-left text-[12.5px] text-text-primary hover:bg-surface-alt"
                  >
                    Rename
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setMode("move");
                      setMenuOpen(false);
                    }}
                    className="block w-full rounded px-2 py-1.5 text-left text-[12.5px] text-text-primary hover:bg-surface-alt"
                  >
                    Move to…
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      onManageAttributes(node);
                    }}
                    className="block w-full rounded px-2 py-1.5 text-left text-[12.5px] text-text-primary hover:bg-surface-alt"
                  >
                    Manage attributes
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      if (!confirm(`Delete "${node.name}"?`)) return;
                      run(() => apiCall(`/api/tenant/categories/${node.id}`, "DELETE"));
                    }}
                    className="block w-full rounded px-2 py-1.5 text-left text-[12.5px] text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40"
                  >
                    Delete
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {mode === "addChild" && (
        <InlineNameForm
          indent={depth + 1}
          placeholder="Subcategory name"
          onSubmit={(name) => {
            setMode("view");
            setExpanded(true);
            run(() => apiCall("/api/tenant/categories", "POST", { name, parent_id: node.id }));
          }}
          onCancel={() => setMode("view")}
        />
      )}
      {mode === "move" && (
        <MovePicker
          tree={rootTree}
          nodeId={node.id}
          indent={depth}
          onPick={(parentId) => {
            setMode("view");
            run(() =>
              apiCall(`/api/tenant/categories/${node.id}/reparent`, "PATCH", { parent_id: parentId }),
            );
          }}
          onCancel={() => setMode("view")}
        />
      )}

      {expanded && (
        <>
          {node.children.map((child) => (
            <CategoryNode
              key={child.id}
              node={child}
              depth={depth + 1}
              rootTree={rootTree}
              products={products}
              selectedId={selectedId}
              onSelect={onSelect}
              selectedProductId={selectedProductId}
              onSelectProduct={onSelectProduct}
              onMutate={onMutate}
              onManageAttributes={onManageAttributes}
              setError={setError}
            />
          ))}
          {ownProducts.map((p) => (
            <ProductRow
              key={p.id}
              product={p}
              depth={depth + 1}
              active={selectedProductId === p.id}
              onSelect={onSelectProduct}
            />
          ))}
        </>
      )}
    </div>
  );
}

export function CategoryTree({
  tree,
  products,
}: {
  tree: CategoryTreeNode[];
  products: Product[];
}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const selectedId = params.get("category");
  const selectedProductId = params.get("product");

  const [addingRoot, setAddingRoot] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attrModalFor, setAttrModalFor] = useState<CategoryTreeNode | null>(null);

  const rootProducts = products.filter((p) => p.category_id === null);

  function select(id: string | null) {
    const next = new URLSearchParams(params.toString());
    if (id) next.set("category", id);
    else next.delete("category");
    router.push(`${pathname}${next.toString() ? `?${next}` : ""}`);
  }

  function selectProduct(id: string) {
    const next = new URLSearchParams(params.toString());
    next.set("product", id);
    router.push(`${pathname}?${next}`);
  }

  async function createRoot(name: string) {
    try {
      setError(null);
      await apiCall("/api/tenant/categories", "POST", { name, parent_id: null });
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    }
  }

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col overflow-auto py-4 pl-3.5 pr-2.5">
      <div className="mb-2 flex items-center justify-between px-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">
          Catalog
        </span>
        <button
          type="button"
          title="Add category"
          onClick={() => setAddingRoot(true)}
          className="rounded p-1 text-text-muted"
        >
          <PlusIcon size={14} />
        </button>
      </div>

      {error && (
        <p className="mx-1 mb-2 rounded-md bg-red-50 px-2 py-1.5 text-[11.5px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
          {error}
        </p>
      )}

      {addingRoot && (
        <InlineNameForm
          indent={0}
          placeholder="Category name"
          onSubmit={(name) => {
            setAddingRoot(false);
            createRoot(name);
          }}
          onCancel={() => setAddingRoot(false)}
        />
      )}

      <div className="flex flex-col">
        {tree.map((node) => (
          <CategoryNode
            key={node.id}
            node={node}
            depth={0}
            rootTree={tree}
            products={products}
            selectedId={selectedId}
            onSelect={select}
            selectedProductId={selectedProductId}
            onSelectProduct={selectProduct}
            onMutate={() => router.refresh()}
            onManageAttributes={setAttrModalFor}
            setError={setError}
          />
        ))}
        {rootProducts.map((p) => (
          <ProductRow
            key={p.id}
            product={p}
            depth={0}
            active={selectedProductId === p.id}
            onSelect={selectProduct}
          />
        ))}
        {tree.length === 0 && rootProducts.length === 0 && !addingRoot && (
          <p className="px-2 py-3 text-[12.5px] text-text-muted">
            No categories yet — add one to start organizing products.
          </p>
        )}
      </div>

      {attrModalFor && (
        <CategoryAttributesModal
          categoryId={attrModalFor.id}
          categoryName={attrModalFor.name}
          onClose={() => setAttrModalFor(null)}
          onSaved={() => router.refresh()}
        />
      )}
    </div>
  );
}
