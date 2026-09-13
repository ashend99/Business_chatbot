"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge, DocumentStatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { Field, Input, Textarea } from "@/components/ui/Field";
import { TagInput } from "@/components/ui/TagInput";
import { formatDateTime, fromDateTimeInput, toDateTimeInput } from "@/lib/format";
import type { DocumentDetail } from "@/lib/types";

const SOURCE_LABEL: Record<string, string> = {
  upload: "Uploaded file",
  paste: "Pasted text",
  url: "Imported URL",
};

export function DocumentDetailPanel({
  documentId,
  onClose,
  onDeleted,
}: {
  documentId: string;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const router = useRouter();
  const confirm = useConfirm();
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [content, setContent] = useState("");
  const [activeFrom, setActiveFrom] = useState("");
  const [activeUntil, setActiveUntil] = useState("");
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState<string | null>(null); // publish/retry/deactivate/delete in flight
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // This panel is keyed on `documentId` by the parent, so it remounts (fresh
  // state) whenever the selection changes.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/tenant/documents/${documentId}`);
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? "Failed to load");
        const data = (await res.json()) as DocumentDetail;
        if (cancelled) return;
        setDoc(data);
        setTitle(data.title);
        setTags(data.tags ?? []);
        setContent(data.draft_content);
        setActiveFrom(toDateTimeInput(data.active_from));
        setActiveUntil(toDateTimeInput(data.active_until));
      } catch (e) {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  const dirty =
    doc != null &&
    (title !== doc.title ||
      content !== doc.draft_content ||
      JSON.stringify(tags) !== JSON.stringify(doc.tags ?? []) ||
      activeFrom !== toDateTimeInput(doc.active_from) ||
      activeUntil !== toDateTimeInput(doc.active_until));

  async function saveDraft() {
    if (!doc) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const res = await fetch(`/api/tenant/documents/${doc.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          tags,
          draft_content: content,
          active_from: fromDateTimeInput(activeFrom),
          active_until: fromDateTimeInput(activeUntil),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error ?? "Could not save the draft.");
      setDoc(data);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the draft.");
    } finally {
      setSaving(false);
    }
  }

  async function runAction(action: "publish" | "retry" | "deactivate", confirmMsg?: string) {
    if (!doc) return;
    if (confirmMsg) {
      const ok = await confirm({
        title: action === "retry" ? "Retry publish" : action === "deactivate" ? "Deactivate document" : "Publish document",
        message: confirmMsg,
        confirmLabel: action === "retry" ? "Retry" : action === "deactivate" ? "Deactivate" : "Publish",
      });
      if (!ok) return;
    }
    setBusy(action);
    setError(null);
    try {
      const method = action === "deactivate" ? "PATCH" : "POST";
      const res = await fetch(`/api/tenant/documents/${doc.id}/${action}`, { method });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error ?? `Could not ${action} the document.`);
      setDoc(data);
      setTitle(data.title);
      setTags(data.tags ?? []);
      setContent(data.draft_content);
      router.refresh(); // reflect the new status in the list
    } catch (e) {
      setError(e instanceof Error ? e.message : `Could not ${action} the document.`);
    } finally {
      setBusy(null);
    }
  }

  async function deleteDocument() {
    if (!doc) return;
    const ok = await confirm({
      title: "Delete document",
      message: `Delete "${doc.title}"? This can't be undone.`,
      confirmLabel: "Delete",
      danger: true,
    });
    if (!ok) return;
    setBusy("delete");
    const res = await fetch(`/api/tenant/documents/${doc.id}`, { method: "DELETE" });
    if (!res.ok) {
      setError((await res.json().catch(() => ({}))).error ?? "Could not delete the document.");
      setBusy(null);
      return;
    }
    onDeleted();
  }

  return (
    <aside className="flex h-full min-w-0 flex-1 flex-col overflow-auto border-l border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border-subtle px-5 py-3.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="truncate text-[13.5px] font-semibold text-text-primary">
            {doc?.title ?? "Document"}
          </span>
          {doc && <DocumentStatusBadge status={doc.status} />}
          {doc?.is_expired && <Badge tone="warning">Expired</Badge>}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {doc && (
            <Button variant="danger" size="sm" onClick={deleteDocument} disabled={busy !== null}>
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

      {doc && !loading && (
        <div className="flex flex-1 flex-col gap-4 p-5">
          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-[12.5px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
              {error}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-text-muted">
            <span>Source: {SOURCE_LABEL[doc.content_source] ?? doc.content_source}</span>
            {doc.source_ref && <span className="truncate">({doc.source_ref})</span>}
            {doc.last_published_at && <span>Last published {formatDateTime(doc.last_published_at)}</span>}
          </div>

          <Field label="Title">
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>

          <Field label="Tags" hint="Type and press Enter to add">
            <TagInput tags={tags} onChange={setTags} placeholder="e.g. policies, delivery" />
          </Field>

          <div>
            <span className="text-[12.5px] font-medium text-text-secondary">Active window</span>
            <p className="mb-2 text-[11.5px] text-text-muted">
              For a temporary document (a seasonal offer, a holiday notice) — leave both blank to
              keep it always active once published.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <Field label="From" hint="Optional">
                <Input type="datetime-local" value={activeFrom} onChange={(e) => setActiveFrom(e.target.value)} />
              </Field>
              <Field label="Until" hint="Optional">
                <Input type="datetime-local" value={activeUntil} onChange={(e) => setActiveUntil(e.target.value)} />
              </Field>
            </div>
          </div>

          <div className="flex flex-1 flex-col gap-1.5">
            <span className="text-[12.5px] font-medium text-text-secondary">Content</span>
            <Textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="min-h-64 flex-1 resize-none font-mono text-[12.5px] leading-relaxed"
            />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border-subtle pt-4">
            <div className="flex items-center gap-2">
              {doc.status === "failed" ? (
                <Button
                  size="sm"
                  onClick={() =>
                    runAction("retry", "Retry publishing this document? It will be re-embedded and go live.")
                  }
                  disabled={busy !== null}
                >
                  {busy === "retry" ? "Retrying…" : "Retry publish"}
                </Button>
              ) : (
                <Button
                  size="sm"
                  onClick={() =>
                    runAction(
                      "publish",
                      "Publish this document? It will be embedded and made live for the bot.",
                    )
                  }
                  disabled={busy !== null || doc.status === "processing" || !content.trim() || dirty}
                  title={dirty ? "Save your changes before publishing" : undefined}
                >
                  {busy === "publish" ? "Publishing…" : "Publish"}
                </Button>
              )}
              {doc.status === "active" && (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => runAction("deactivate")}
                  disabled={busy !== null}
                >
                  {busy === "deactivate" ? "Deactivating…" : "Deactivate"}
                </Button>
              )}
            </div>

            <div className="flex items-center gap-3">
              {saved && !dirty && <span className="text-[12px] text-positive">Saved</span>}
              <Button size="sm" variant="secondary" onClick={saveDraft} disabled={!dirty || saving}>
                {saving ? "Saving…" : "Save draft"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
