"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { ConversationDetailPanel } from "@/components/conversations/ConversationDetailPanel";
import { Topbar } from "@/components/Topbar";
import { ConversationStatusBadge } from "@/components/ui/Badge";
import { relativeTime } from "@/lib/format";
import type { ConversationChannel, ConversationListItem } from "@/lib/types";

const STATUS_TABS: { key: string; label: string }[] = [
  { key: "", label: "All" },
  { key: "open", label: "Open" },
  { key: "idle", label: "Idle" },
  { key: "closed", label: "Closed" },
];

const CHANNEL_LABEL: Record<ConversationChannel, string> = {
  website_widget: "Website",
  facebook: "Facebook",
  instagram: "Instagram",
  whatsapp: "WhatsApp",
};

export function ConversationsView({
  conversations,
  total,
}: {
  conversations: ConversationListItem[];
  total: number;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const status = params.get("status") ?? "";
  const channel = params.get("channel") ?? "";
  const selectedId = params.get("conversation");

  function selectStatus(key: string) {
    const next = new URLSearchParams(params.toString());
    if (key) next.set("status", key);
    else next.delete("status");
    router.push(`${pathname}${next.toString() ? `?${next}` : ""}`);
  }

  function selectChannel(value: string) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set("channel", value);
    else next.delete("channel");
    router.push(`${pathname}${next.toString() ? `?${next}` : ""}`);
  }

  function selectConversation(id: string) {
    const next = new URLSearchParams(params.toString());
    next.set("conversation", id);
    router.push(`${pathname}?${next}`);
  }

  function closeConversation() {
    const next = new URLSearchParams(params.toString());
    next.delete("conversation");
    router.push(`${pathname}${next.toString() ? `?${next}` : ""}`);
  }

  return (
    <>
      <Topbar title="Conversations" />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden border-r border-border">
          <div className="flex items-center justify-between gap-2 border-b border-border px-5 py-3">
            <div className="flex items-center gap-2">
              {STATUS_TABS.map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => selectStatus(tab.key)}
                  className={`rounded-lg px-3 py-1.5 text-[12.5px] ${
                    status === tab.key
                      ? "bg-accent font-semibold text-white"
                      : "text-text-secondary hover:bg-surface-alt"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <select
              value={channel}
              onChange={(e) => selectChannel(e.target.value)}
              className="rounded-lg border border-border bg-surface px-2.5 py-1.5 text-[12.5px] text-text-secondary"
            >
              <option value="">All channels</option>
              {Object.entries(CHANNEL_LABEL).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex-1 overflow-auto">
            {conversations.length === 0 ? (
              <p className="p-8 text-center text-sm text-text-muted">
                {status || channel ? "No conversations match this filter." : "No conversations yet."}
              </p>
            ) : (
              <ul>
                {conversations.map((conv) => (
                  <li
                    key={conv.id}
                    onClick={() => selectConversation(conv.id)}
                    className={`cursor-pointer border-t border-border-subtle px-5 py-3 first:border-t-0 ${
                      selectedId === conv.id ? "bg-accent-soft" : "hover:bg-surface-alt"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-[13px] font-medium text-text-primary">
                        {conv.external_user_id}
                      </span>
                      <span className="shrink-0 text-[11px] text-text-muted" suppressHydrationWarning>
                        {relativeTime(conv.last_message_at)}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-1.5">
                      <ConversationStatusBadge status={conv.status} />
                      <span className="text-[11px] text-text-muted">{CHANNEL_LABEL[conv.channel_type]}</span>
                    </div>
                    {conv.last_message_preview && (
                      <p className="mt-1.5 truncate text-[12.5px] text-text-secondary">
                        {conv.last_message_preview}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="border-t border-border px-5 py-2 text-[12px] text-text-muted">
            {total} conversation{total === 1 ? "" : "s"}
          </div>
        </div>

        {selectedId ? (
          <ConversationDetailPanel
            key={selectedId}
            conversationId={selectedId}
            onClose={closeConversation}
          />
        ) : (
          <div className="flex h-full min-w-0 flex-1 items-center justify-center bg-surface">
            <p className="text-sm text-text-muted">No conversation is selected</p>
          </div>
        )}
      </div>
    </>
  );
}
