"use client";

import { useEffect, useState } from "react";

import { ConversationStatusBadge } from "@/components/ui/Badge";
import { formatDateTime } from "@/lib/format";
import type { ConversationChannel, ConversationDetail } from "@/lib/types";

const CHANNEL_LABEL: Record<ConversationChannel, string> = {
  website_widget: "Website",
  facebook: "Facebook",
  instagram: "Instagram",
  whatsapp: "WhatsApp",
};

export function ConversationDetailPanel({
  conversationId,
  onClose,
}: {
  conversationId: string;
  onClose: () => void;
}) {
  const [conversation, setConversation] = useState<ConversationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Keyed on `conversationId` by the parent, so it remounts fresh on selection change.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/tenant/conversations/${conversationId}`);
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? "Failed to load");
        const data = (await res.json()) as ConversationDetail;
        if (cancelled) return;
        setConversation(data);
      } catch (e) {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  return (
    <aside className="flex h-full min-w-0 flex-1 flex-col overflow-auto border-l border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border-subtle px-5 py-3.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="truncate text-[13.5px] font-semibold text-text-primary">
            {conversation?.external_user_id ?? "Conversation"}
          </span>
          {conversation && <ConversationStatusBadge status={conversation.status} />}
          {conversation && (
            <span className="text-[11px] text-text-muted">{CHANNEL_LABEL[conversation.channel_type]}</span>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="shrink-0 rounded p-1.5 text-text-muted hover:bg-surface-alt hover:text-text-primary"
        >
          <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      {loading && <p className="p-5 text-[12.5px] text-text-muted">Loading…</p>}
      {loadError && !loading && (
        <p className="m-5 rounded-lg bg-red-50 px-3 py-2 text-[12.5px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
          {loadError}
        </p>
      )}

      {conversation && !loading && (
        <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-5">
          {conversation.messages.length === 0 ? (
            <p className="text-[12.5px] text-text-muted">No messages yet.</p>
          ) : (
            conversation.messages.map((m) =>
              m.role === "system" ? (
                <p key={m.id} className="self-center text-[11px] text-text-muted">
                  {m.content}
                </p>
              ) : (
                <div
                  key={m.id}
                  className={`flex max-w-[75%] flex-col gap-1 rounded-xl px-3 py-2 text-[12.5px] ${
                    m.role === "user"
                      ? "self-start rounded-bl-sm bg-surface-alt text-text-primary"
                      : "self-end rounded-br-sm bg-accent text-white"
                  }`}
                >
                  <span className="whitespace-pre-wrap">{m.content}</span>
                  <span
                    className={`text-[10px] ${m.role === "user" ? "text-text-muted" : "text-white/70"}`}
                    suppressHydrationWarning
                  >
                    {formatDateTime(m.created_at)}
                  </span>
                </div>
              ),
            )
          )}
        </div>
      )}
    </aside>
  );
}
