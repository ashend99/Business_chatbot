import "server-only";

import { apiFetch } from "@/lib/api";
import type { DocumentDetail, DocumentListResponse, DocumentStatus } from "@/lib/types";

export type DocumentListParams = {
  status?: DocumentStatus;
  /** Documents whose active_until has passed -- independent of `status`,
   * since the lazy cleanup sweep may not have flipped it to inactive yet. */
  expiredOnly?: boolean;
  page?: number;
  pageSize?: number;
};

export function listDocuments(params: DocumentListParams = {}): Promise<DocumentListResponse> {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  if (params.expiredOnly) q.set("expired", "true");
  q.set("page", String(params.page ?? 1));
  q.set("page_size", String(params.pageSize ?? 50));
  return apiFetch<DocumentListResponse>(`/tenant/documents?${q.toString()}`);
}

export function getDocument(id: string): Promise<DocumentDetail> {
  return apiFetch<DocumentDetail>(`/tenant/documents/${id}`);
}
