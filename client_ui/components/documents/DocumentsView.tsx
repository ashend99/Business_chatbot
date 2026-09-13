"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { DocumentDetailPanel } from "@/components/documents/DocumentDetailPanel";
import { NewDocumentModal } from "@/components/documents/NewDocumentModal";
import { PlusIcon } from "@/components/icons";
import { Topbar } from "@/components/Topbar";
import { Button } from "@/components/ui/Button";
import { Badge, DocumentStatusBadge } from "@/components/ui/Badge";
import { relativeTime } from "@/lib/format";
import type { DocumentListItem, DocumentStatus } from "@/lib/types";

// "expired" isn't a `status` value -- it's a date comparison independent of
// status (see repos/documents.py) -- so it's tracked via its own `?expired=`
// param, mutually exclusive with `?status=` in this tab bar.
const TABS: { key: string; label: string }[] = [
  { key: "", label: "All" },
  { key: "draft", label: "Draft" },
  { key: "active", label: "Published" },
  { key: "processing", label: "Processing" },
  { key: "failed", label: "Failed" },
  { key: "inactive", label: "Inactive" },
  { key: "expired", label: "Expired" },
];

const SOURCE_LABEL: Record<string, string> = {
  upload: "Uploaded file",
  paste: "Pasted text",
  url: "Imported URL",
};

export function DocumentsView({
  documents,
  total,
}: {
  documents: DocumentListItem[];
  total: number;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const expiredOnly = params.get("expired") === "true";
  const status = expiredOnly ? "" : params.get("status") ?? "";
  const activeTab = expiredOnly ? "expired" : status;
  const selectedId = params.get("document");

  const [newOpen, setNewOpen] = useState(false);

  function selectTab(key: string) {
    const next = new URLSearchParams(params.toString());
    next.delete("status");
    next.delete("expired");
    if (key === "expired") next.set("expired", "true");
    else if (key) next.set("status", key);
    router.push(`${pathname}${next.toString() ? `?${next}` : ""}`);
  }

  function selectDocument(id: string) {
    const next = new URLSearchParams(params.toString());
    next.set("document", id);
    router.push(`${pathname}?${next}`);
  }

  function closeDocument() {
    const next = new URLSearchParams(params.toString());
    next.delete("document");
    router.push(`${pathname}${next.toString() ? `?${next}` : ""}`);
  }

  function openDocument(id: string) {
    const next = new URLSearchParams(params.toString());
    next.set("document", id);
    router.push(`${pathname}?${next}`);
    router.refresh();
  }

  return (
    <>
      <Topbar
        title="Knowledge base"
        actions={
          <Button size="sm" onClick={() => setNewOpen(true)}>
            <PlusIcon size={14} />
            New document
          </Button>
        }
      />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden border-r border-border">
          <div className="flex items-center gap-2 border-b border-border px-5 py-3">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => selectTab(tab.key)}
                className={`rounded-lg px-3 py-1.5 text-[12.5px] ${
                  activeTab === tab.key
                    ? "bg-accent font-semibold text-white"
                    : "text-text-secondary hover:bg-surface-alt"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-auto">
            {documents.length === 0 ? (
              <p className="p-8 text-center text-sm text-text-muted">
                {expiredOnly
                  ? "No expired documents."
                  : status
                    ? "No documents in this status."
                    : "No documents yet."}
              </p>
            ) : (
              <table className="w-full">
                <thead className="sticky top-0 bg-bg">
                  <tr className="text-left text-[11px] uppercase tracking-wide text-text-muted">
                    <th className="px-5 py-2.5 font-medium">Title</th>
                    <th className="px-5 py-2.5 font-medium">Status</th>
                    <th className="px-5 py-2.5 font-medium">Source</th>
                    <th className="px-5 py-2.5 font-medium">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => (
                    <tr
                      key={doc.id}
                      onClick={() => selectDocument(doc.id)}
                      className={`cursor-pointer border-t border-border-subtle ${
                        selectedId === doc.id ? "bg-accent-soft" : "hover:bg-surface-alt"
                      }`}
                    >
                      <td className="max-w-0 px-5 py-3 text-[13px] font-medium text-text-primary">
                        <span className="block truncate">{doc.title}</span>
                      </td>
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-1.5">
                          <DocumentStatusBadge status={doc.status as DocumentStatus} />
                          {doc.is_expired && <Badge tone="warning">Expired</Badge>}
                        </div>
                      </td>
                      <td className="px-5 py-3 text-[12.5px] text-text-secondary">
                        {SOURCE_LABEL[doc.content_source] ?? doc.content_source}
                      </td>
                      <td className="px-5 py-3 text-[12px] text-text-muted" suppressHydrationWarning>
                        {relativeTime(doc.updated_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="border-t border-border px-5 py-2 text-[12px] text-text-muted">
            {total} document{total === 1 ? "" : "s"}
          </div>
        </div>

        {selectedId ? (
          <DocumentDetailPanel
            key={selectedId}
            documentId={selectedId}
            onClose={closeDocument}
            onDeleted={() => {
              closeDocument();
              router.refresh();
            }}
          />
        ) : (
          <div className="flex h-full min-w-0 flex-1 items-center justify-center bg-surface">
            <p className="text-sm text-text-muted">No document is selected</p>
          </div>
        )}
      </div>

      {newOpen && <NewDocumentModal onClose={() => setNewOpen(false)} onCreated={openDocument} />}
    </>
  );
}
