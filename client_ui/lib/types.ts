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

// ---- Conversations ------------------------------------------------------

export type ConversationChannel = "website_widget" | "facebook" | "instagram" | "whatsapp";
export type ConversationStatus = "open" | "idle" | "closed";

export interface ConversationListItem {
  id: string;
  channel_type: ConversationChannel;
  external_user_id: string;
  status: ConversationStatus;
  last_message_at: string;
  last_message_preview: string | null;
}

export interface ConversationListResponse {
  items: ConversationListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface MessageRead {
  id: string;
  role: MessageRole;
  content: string;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  channel_type: ConversationChannel;
  external_user_id: string;
  status: ConversationStatus;
  last_message_at: string;
  messages: MessageRead[];
}

// ---- Orders ---------------------------------------------------------------

export type OrderStatus = "draft" | "placed" | "completed" | "cancelled";

export interface OrderItem {
  variant_id: string;
  product_name: string;
  variant_label: string | null;
  quantity: number;
  unit_price: string;
  line_total: string;
}

export interface OrderListItem {
  id: string;
  status: OrderStatus;
  items: OrderItem[];
  total: string;
  fulfillment: Record<string, string> | null;
  created_at: string;
}

export interface OrderListResponse {
  items: OrderListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface OrderDetail {
  id: string;
  conversation_id: string | null;
  lead_id: string | null;
  status: OrderStatus;
  items: OrderItem[];
  total: string;
  fulfillment: Record<string, string> | null;
  notes: string | null;
  source_channel: string | null;
  created_at: string;
  updated_at: string;
  lead_fields: Record<string, string>;
  transcript: TranscriptMessage[];
}

export interface OrderUpdate {
  status: OrderStatus;
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

// ---- Documents / Knowledge base ----------------------------------------

export type DocumentStatus = "draft" | "processing" | "active" | "failed" | "inactive";
export type ContentSource = "upload" | "paste" | "url";

export interface DocumentListItem {
  id: string;
  title: string;
  content_source: ContentSource;
  tags: string[] | null;
  status: DocumentStatus;
  last_published_at: string | null;
  /** Optional "temporary document" window, e.g. a seasonal offer. Both null = always active once published. */
  active_from: string | null;
  active_until: string | null;
  /** Computed server-side: true once `active_until` has passed, even if `status` hasn't been swept to inactive yet. */
  is_expired: boolean;
  updated_at: string;
}

export interface DocumentListResponse {
  items: DocumentListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface DocumentDetail {
  id: string;
  title: string;
  content_source: ContentSource;
  source_ref: string | null;
  draft_content: string;
  tags: string[] | null;
  status: DocumentStatus;
  last_published_at: string | null;
  active_from: string | null;
  active_until: string | null;
  is_expired: boolean;
  created_at: string;
  updated_at: string;
}

export interface DocumentUpdate {
  title?: string;
  tags?: string[] | null;
  draft_content?: string;
  active_from?: string | null;
  active_until?: string | null;
}
