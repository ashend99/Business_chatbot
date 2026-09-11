import "server-only";

import { apiFetch } from "@/lib/api";
import { LEAD_PAGE_SIZE } from "@/lib/constants";
import type { LeadDetail, LeadFieldDef, LeadListResponse } from "@/lib/types";

export type LeadListParams = {
  status?: string;
  search?: string;
  createdAfter?: string;
  createdBefore?: string;
  page?: number;
};

export function listLeads(params: LeadListParams): Promise<LeadListResponse> {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  if (params.search) q.set("search", params.search);
  if (params.createdAfter) q.set("created_after", params.createdAfter);
  if (params.createdBefore) q.set("created_before", params.createdBefore);
  q.set("page", String(params.page ?? 1));
  q.set("page_size", String(LEAD_PAGE_SIZE));
  return apiFetch<LeadListResponse>(`/tenant/leads?${q.toString()}`);
}

export function getLead(id: string): Promise<LeadDetail> {
  return apiFetch<LeadDetail>(`/tenant/leads/${id}`);
}

export function listLeadFieldDefs(): Promise<LeadFieldDef[]> {
  return apiFetch<LeadFieldDef[]>("/tenant/lead-field-defs");
}
