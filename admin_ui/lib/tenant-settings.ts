import "server-only";

import { apiFetch } from "@/lib/api";
import type { AdminSettingsRead, AdminSettingsUpdatePayload, ApiKeyCreated, ApiKeyRead } from "@/lib/types";

export async function getAdminSettings(tenantId: string): Promise<AdminSettingsRead> {
  return apiFetch<AdminSettingsRead>(`/superadmin/tenants/${tenantId}/settings`);
}

export async function updateAdminSettings(
  tenantId: string,
  patch: AdminSettingsUpdatePayload,
): Promise<AdminSettingsRead> {
  return apiFetch<AdminSettingsRead>(`/superadmin/tenants/${tenantId}/settings`, {
    method: "PATCH",
    body: patch,
  });
}

export async function listApiKeys(tenantId: string): Promise<ApiKeyRead[]> {
  return apiFetch<ApiKeyRead[]>(`/superadmin/tenants/${tenantId}/api-keys`);
}

export async function createApiKey(tenantId: string): Promise<ApiKeyCreated> {
  return apiFetch<ApiKeyCreated>(`/superadmin/tenants/${tenantId}/api-keys`, { method: "POST" });
}

export async function revokeApiKey(tenantId: string, keyId: string): Promise<ApiKeyRead> {
  return apiFetch<ApiKeyRead>(`/superadmin/tenants/${tenantId}/api-keys/${keyId}`, { method: "DELETE" });
}
