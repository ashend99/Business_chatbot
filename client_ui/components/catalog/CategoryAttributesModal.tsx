"use client";

import { useEffect, useState } from "react";

import { PlusIcon, TrashIcon } from "@/components/icons";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { TagInput } from "@/components/ui/TagInput";
import type { CategoryAttribute } from "@/lib/types";

type Row = { name: string; choices: string[] };

function toRows(attrs: CategoryAttribute[]): Row[] {
  return attrs.map((a) => ({ name: a.name, choices: a.choices }));
}

export function CategoryAttributesModal({
  categoryId,
  categoryName,
  onClose,
  onSaved,
}: {
  categoryId: string;
  categoryName: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/tenant/categories/${categoryId}/attributes`);
        if (!res.ok) throw new Error("Could not load attributes.");
        const data = (await res.json()) as CategoryAttribute[];
        if (!cancelled) setRows(toRows(data));
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load attributes.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [categoryId]);

  function updateRow(i: number, patch: Partial<Row>) {
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  }

  function removeRow(i: number) {
    setRows((r) => r.filter((_, idx) => idx !== i));
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const attributes = rows
        .map((r, i) => ({ name: r.name.trim(), choices: r.choices, sort_order: i }))
        .filter((a) => a.name && a.choices.length > 0);

      const res = await fetch(`/api/tenant/categories/${categoryId}/attributes`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ attributes }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? "Could not save.");
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save attributes.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title={`Attributes — ${categoryName}`} onClose={onClose} width={480}>
      <p className="mb-4 text-[12px] text-text-muted">
        Products in this category — and any of its subcategories — can offer these as variant
        choices (e.g. Size: Small, Medium, Large). A subcategory can add its own on top, or
        redefine one of these with the same name to override it.
      </p>

      {error && (
        <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-[12.5px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
          {error}
        </p>
      )}

      {loading ? (
        <p className="text-[12.5px] text-text-muted">Loading…</p>
      ) : (
        <div className="flex flex-col gap-3">
          {rows.map((row, i) => (
            <div key={i} className="flex items-start gap-2">
              <div className="w-32 shrink-0">
                <Field label={i === 0 ? "Attribute name" : undefined}>
                  <Input
                    placeholder="e.g. Size"
                    value={row.name}
                    onChange={(e) => updateRow(i, { name: e.target.value })}
                  />
                </Field>
              </div>
              <div className="flex-1">
                <Field label={i === 0 ? "Choices — type and press Enter" : undefined}>
                  <TagInput
                    tags={row.choices}
                    onChange={(choices) => updateRow(i, { choices })}
                    placeholder="Small, Medium, Large…"
                  />
                </Field>
              </div>
              <button
                type="button"
                onClick={() => removeRow(i)}
                title="Remove"
                className={`rounded p-1.5 text-text-muted hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40 dark:hover:text-red-400 ${i === 0 ? "mt-6" : ""}`}
              >
                <TrashIcon size={14} />
              </button>
            </div>
          ))}

          <button
            type="button"
            onClick={() => setRows((r) => [...r, { name: "", choices: [] }])}
            className="flex w-fit items-center gap-1 text-[12.5px] font-semibold text-accent hover:underline"
          >
            <PlusIcon size={13} />
            Add attribute
          </button>

          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="secondary" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button type="button" size="sm" onClick={save} disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
