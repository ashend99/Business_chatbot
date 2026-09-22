/** Mirrors src/app/schemas/tenants.py and src/app/schemas/settings.py --
 * keep in sync by hand, there's no shared codegen between the two apps. */

export type TenantListItem = {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  email: string | null;
  created_at: string;
};

export type TenantListResponse = {
  items: TenantListItem[];
  total: number;
  page: number;
  page_size: number;
};

export type TenantRead = {
  id: string;
  name: string;
  slug: string;
  is_active: boolean;
  email: string | null;
  contact_person: string | null;
  contact_number: string | null;
  address: string | null;
  created_at: string;
};

/** GET/{id} returns this richer shape; create/update/suspend/reactivate
 * return plain TenantRead (see src/app/api/superadmin/tenants.py). */
export type TenantDetail = TenantRead & {
  // whether the tenant has completed activation (has a TenantAdmin login)
  activated: boolean;
  admin_username: string | null;
};

export type TenantUpdatePayload = Partial<{
  name: string;
  email: string;
  contact_person: string | null;
  contact_number: string | null;
  address: string | null;
}>;

/** The optional inline block TenantCreate accepts -- same shape as
 * AdminSettingsUpdate, but only used at creation time here. */
export type AdminSettingsCreatePayload = Partial<{
  ordering_allowed: boolean;
  catalog_allowed: boolean;
  documents_allowed: boolean;
  leads_allowed: boolean;
  allowed_channels: string[];
  llm_model: string | null;
  monthly_message_limit: number | null;
  max_documents: number | null;
}>;

export type TenantCreatePayload = {
  name: string;
  slug: string;
  email: string;
  contact_person?: string | null;
  contact_number?: string | null;
  address?: string | null;
  currency_code: string;
  timezone?: string;
  admin_settings?: AdminSettingsCreatePayload;
};

export const KNOWN_CHANNELS = ["website_widget", "facebook", "instagram", "whatsapp"] as const;
export type Channel = (typeof KNOWN_CHANNELS)[number];

export type AdminSettingsRead = {
  tenant_id: string;
  currency_code: string;
  ordering_allowed: boolean;
  catalog_allowed: boolean;
  documents_allowed: boolean;
  leads_allowed: boolean;
  allowed_channels: string[];
  llm_model: string | null;
  monthly_message_limit: number | null;
  max_documents: number | null;
};

/** PATCH payload -- only include a key when it's actually changing. Only
 * llm_model/monthly_message_limit/max_documents may be sent as explicit
 * null (the backend 422s on null for any other field). */
export type AdminSettingsUpdatePayload = Partial<AdminSettingsRead> & { tenant_id?: never };

export type ApiKeyType = "widget_site_key" | "api_secret";

export type ApiKeyRead = {
  id: string;
  key_prefix: string;
  key_type: ApiKeyType;
  created_at: string;
  revoked_at: string | null;
};

export type ApiKeyCreated = ApiKeyRead & { secret: string };
