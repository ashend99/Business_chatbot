import "server-only";

import { apiFetch } from "@/lib/api";
import type { ConversationChannel, ConversationListResponse, ConversationStatus } from "@/lib/types";

export type ConversationListParams = {
  channel?: ConversationChannel;
  status?: ConversationStatus;
  page?: number;
  pageSize?: number;
};

export function listConversations(params: ConversationListParams = {}): Promise<ConversationListResponse> {
  const q = new URLSearchParams();
  if (params.channel) q.set("channel", params.channel);
  if (params.status) q.set("status", params.status);
  q.set("page", String(params.page ?? 1));
  q.set("page_size", String(params.pageSize ?? 50));
  return apiFetch<ConversationListResponse>(`/tenant/conversations?${q.toString()}`);
}
