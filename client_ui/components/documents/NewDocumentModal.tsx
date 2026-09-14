"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Input, Textarea } from "@/components/ui/Field";
import { Modal } from "@/components/ui/Modal";
import { fromDateTimeInput } from "@/lib/format";
import type { DocumentDetail } from "@/lib/types";

type Source = "paste" | "upload" | "url";

const TABS: { value: Source; label: string }[] = [
  { value: "paste", label: "Paste text" },
  { value: "upload", label: "Upload file" },
  { value: "url", label: "Import URL" },
];

export function NewDocumentModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (documentId: string) => void;
}) {
  const [source, setSource] = useState<Source>("paste");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [showWindow, setShowWindow] = useState(false);
  const [activeFrom, setActiveFrom] = useState("");
  const [activeUntil, setActiveUntil] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (source === "paste" && !content.trim()) {
      setError("Paste some content, or switch to Upload / Import URL.");
      return;
    }
    if (source === "upload" && !file) {
      setError("Choose a file to upload.");
      return;
    }
    if (source === "url" && !url.trim()) {
      setError("Enter a URL to import.");
      return;
    }

    const window = showWindow
      ? {
          active_from: fromDateTimeInput(activeFrom),
          active_until: fromDateTimeInput(activeUntil),
        }
      : {};

    setSaving(true);
    try {
      let document: DocumentDetail;

      if (source === "url") {
        const res = await fetch("/api/tenant/documents/import-url", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, url, ...window }),
        });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(body.error ?? "Could not import that URL.");
        document = body;
      } else if (source === "upload") {
        const createRes = await fetch("/api/tenant/documents", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, content_source: "upload", ...window }),
        });
        const created = await createRes.json().catch(() => ({}));
        if (!createRes.ok) throw new Error(created.error ?? "Could not create the document.");

        const formData = new FormData();
        formData.append("file", file as File);
        const uploadRes = await fetch(`/api/tenant/documents/${created.id}/upload`, {
          method: "POST",
          body: formData,
        });
        const uploaded = await uploadRes.json().catch(() => ({}));
        if (!uploadRes.ok) throw new Error(uploaded.error ?? "Could not extract text from that file.");
        document = uploaded;
      } else {
        const res = await fetch("/api/tenant/documents", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title, content_source: "paste", draft_content: content, ...window }),
        });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(body.error ?? "Could not create the document.");
        document = body;
      }

      onClose();
      onCreated(document.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title="New document" onClose={onClose} width={560} height={560}>
      <form onSubmit={onSubmit} className="flex h-full flex-col gap-3.5">
        <div className="flex gap-1 rounded-lg bg-surface-alt p-1">
          {TABS.map((tab) => (
            <button
              key={tab.value}
              type="button"
              onClick={() => setSource(tab.value)}
              className={`flex-1 rounded-md py-1.5 text-[12.5px] font-medium transition-colors ${
                source === tab.value ? "bg-surface text-text-primary shadow-sm" : "text-text-muted"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {error && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-[12.5px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
            {error}
          </p>
        )}

        <Field label="Title">
          <Input autoFocus value={title} onChange={(e) => setTitle(e.target.value)} required />
        </Field>

        {source === "paste" && (
          <div className="flex flex-1 flex-col gap-1.5">
            <span className="text-[12.5px] font-medium text-text-secondary">Content</span>
            <Textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Paste the document's text here…"
              className="min-h-40 flex-1 resize-none text-[12.5px]"
            />
          </div>
        )}

        {source === "upload" && (
          <Field label="File" hint="PDF, DOCX, or TXT">
            <input
              type="file"
              accept=".pdf,.docx,.txt"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-[12.5px] text-text-primary file:mr-3 file:rounded-md file:border-0 file:bg-surface-alt file:px-2.5 file:py-1 file:text-[12px] file:text-text-primary"
            />
          </Field>
        )}

        {source === "url" && (
          <Field label="URL">
            <Input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/faq"
            />
          </Field>
        )}

        {showWindow ? (
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[12.5px] font-medium text-text-secondary">Active window</span>
              <button
                type="button"
                onClick={() => {
                  setShowWindow(false);
                  setActiveFrom("");
                  setActiveUntil("");
                }}
                className="text-[12px] text-text-muted hover:text-text-primary"
              >
                Remove
              </button>
            </div>
            <p className="mb-2 text-[11.5px] text-text-muted">
              For a seasonal offer or holiday notice — leave blank to keep it always active.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <Field label="From" hint="Optional">
                <Input
                  type="datetime-local"
                  value={activeFrom}
                  onChange={(e) => setActiveFrom(e.target.value)}
                />
              </Field>
              <Field label="Until" hint="Optional">
                <Input
                  type="datetime-local"
                  value={activeUntil}
                  onChange={(e) => setActiveUntil(e.target.value)}
                />
              </Field>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setShowWindow(true)}
            className="w-fit text-[12.5px] font-semibold text-accent hover:underline"
          >
            + Set an active window (optional)
          </button>
        )}

        <div className="mt-auto flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" disabled={saving}>
            {saving ? "Creating…" : "Create document"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
