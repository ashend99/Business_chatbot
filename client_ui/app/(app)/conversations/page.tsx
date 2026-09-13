import { redirect } from "next/navigation";

import { ConversationsView } from "@/components/conversations/ConversationsView";
import { Topbar } from "@/components/Topbar";
import { ApiError } from "@/lib/api";
import { listConversations } from "@/lib/conversations";
import type { ConversationChannel, ConversationStatus } from "@/lib/types";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function ConversationsPage({ searchParams }: { searchParams: SearchParams }) {
  const sp = await searchParams;
  const status = typeof sp.status === "string" ? (sp.status as ConversationStatus) : undefined;
  const channel = typeof sp.channel === "string" ? (sp.channel as ConversationChannel) : undefined;

  let data:
    | { ok: true; list: Awaited<ReturnType<typeof listConversations>> }
    | { ok: false; message: string };
  try {
    const list = await listConversations({ status, channel });
    data = { ok: true, list };
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
      redirect("/login");
    }
    const message =
      e instanceof ApiError
        ? e.status === 0
          ? "Can't reach the server. Check that the API is running."
          : `The server returned an error (${e.status}).`
        : "Something went wrong loading conversations.";
    data = { ok: false, message };
  }

  if (!data.ok) {
    return (
      <>
        <Topbar title="Conversations" />
        <div className="flex flex-1 items-center justify-center p-8">
          <p className="text-sm text-text-muted">{data.message}</p>
        </div>
      </>
    );
  }

  return <ConversationsView conversations={data.list.items} total={data.list.total} />;
}
