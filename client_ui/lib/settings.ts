import "server-only";

import { apiFetch } from "@/lib/api";
import type { TenantSettingsResponse } from "@/lib/types";

export function getSettings(): Promise<TenantSettingsResponse> {
  return apiFetch<TenantSettingsResponse>("/tenant/settings");
}
