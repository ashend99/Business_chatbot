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
