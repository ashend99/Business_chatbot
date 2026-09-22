import "server-only";

import { apiFetch } from "@/lib/api";
import type {
  TenantCreatePayload,
  TenantDetail,
  TenantListResponse,
  TenantRead,
  TenantUpdatePayload,
} from "@/lib/types";

export async function listTenants(params: {
  isActive?: boolean;
  search?: string;
  page?: number;
  pageSize?: number;
}): Promise<TenantListResponse> {
  const q = new URLSearchParams();
  if (params.isActive !== undefined) q.set("is_active", String(params.isActive));
  if (params.search) q.set("search", params.search);
  if (params.page) q.set("page", String(params.page));
  if (params.pageSize) q.set("page_size", String(params.pageSize));
  return apiFetch<TenantListResponse>(`/superadmin/tenants?${q.toString()}`);
}

export async function getTenant(id: string): Promise<TenantDetail> {
  return apiFetch<TenantDetail>(`/superadmin/tenants/${id}`);
}

export async function createTenant(body: TenantCreatePayload): Promise<TenantRead> {
  return apiFetch<TenantRead>("/superadmin/tenants", { method: "POST", body });
}

export async function updateTenant(id: string, body: TenantUpdatePayload): Promise<TenantRead> {
  return apiFetch<TenantRead>(`/superadmin/tenants/${id}`, { method: "PATCH", body });
}

export async function suspendTenant(id: string): Promise<TenantRead> {
  return apiFetch<TenantRead>(`/superadmin/tenants/${id}/suspend`, { method: "POST" });
}

export async function reactivateTenant(id: string): Promise<TenantRead> {
  return apiFetch<TenantRead>(`/superadmin/tenants/${id}/reactivate`, { method: "POST" });
}

export async function resendInvite(id: string): Promise<void> {
  await apiFetch<void>(`/superadmin/tenants/${id}/resend-invite`, { method: "POST" });
}
