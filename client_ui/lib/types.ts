/**
 * Shapes mirrored from the backend Pydantic schemas (`src/app/schemas/*`).
 * Keep these in sync by hand for now — small surface, changes rarely.
 */

// Values match the backend enum `.value` (lowercase), which is what the API
// serialises and accepts.
export type LeadStatus =
  | "interested"
  | "new"
  | "contacted"
  | "converted"
  | "lost";

export type LeadFieldType = "text" | "phone" | "email" | "date" | "textarea";

export type MessageRole = "user" | "assistant" | "system";

export interface LeadFieldDef {
  id: string;
  field_key: string;
  label: string;
  field_type: LeadFieldType;
  required: boolean;
  sort_order: number;
}

export interface LeadListItem {
  id: string;
  status: LeadStatus;
  fields: Record<string, string>;
  matched_variant_id: string | null;
  deal_value: string | null;
  created_at: string;
}

export interface LeadListResponse {
  items: LeadListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface TranscriptMessage {
  role: MessageRole;
  content: string;
  created_at: string;
}

export interface Lead {
  id: string;
  conversation_id: string | null;
  matched_variant_id: string | null;
  status: LeadStatus;
  fields: Record<string, string>;
  source_channel: string | null;
  deal_value: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeadDetail extends Lead {
  transcript: TranscriptMessage[];
}

export interface LeadUpdate {
  status?: LeadStatus;
  notes?: string | null;
  deal_value?: string | null;
}

// ---- Catalog ----------------------------------------------------------

export type StockStatus = "in_stock" | "out_of_stock" | "unlimited";

export interface Category {
  id: string;
  name: string;
  parent_id: string | null;
  sort_order: number;
}

export interface CategoryTreeNode {
  id: string;
  name: string;
  parent_id: string | null;
  sort_order: number;
  children: CategoryTreeNode[];
}

export interface Variant {
  id: string;
  product_id: string;
  name: string;
  sku: string | null;
  price: string;
  stock_status: StockStatus;
  stock_qty: number | null;
  stock_message: string | null;
  active: boolean;
  /** Which attribute choice this variant represents, e.g. {"Size": "Large"} — display-only. */
  attribute_values: Record<string, string> | null;
}

/** A reusable variant-building block defined on a category, e.g. "Pizza" -> Size: [Small, Medium, Large]. */
export interface CategoryAttribute {
  id: string;
  category_id: string;
  name: string;
  choices: string[];
  sort_order: number;
}

export interface CategoryAttributeInput {
  name: string;
  choices: string[];
  sort_order?: number;
}

export interface Product {
  id: string;
  name: string;
  category_id: string | null;
  description: string | null;
  image_url: string | null;
}

export interface ProductWithVariants extends Product {
  variants: Variant[];
}

export interface VariantInput {
  name: string;
  sku?: string | null;
  price: string;
  stock_status?: StockStatus;
  stock_qty?: number | null;
  stock_message?: string | null;
  attribute_values?: Record<string, string> | null;
}

export interface ProductCreate {
  name: string;
  category_id?: string | null;
  description?: string | null;
  image_url?: string | null;
  variants?: VariantInput[];
  price?: string;
  sku?: string | null;
  stock_status?: StockStatus;
  stock_qty?: number | null;
  stock_message?: string | null;
}
