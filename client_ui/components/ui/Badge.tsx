import type { ConversationStatus, DocumentStatus, LeadStatus } from "@/lib/types";

const LEAD_STATUS_STYLES: Record<LeadStatus, string> = {
  interested:
    "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-400",
  new: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-400",
  contacted:
    "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300",
  converted: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
  lost: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-400",
};

const LEAD_STATUS_LABELS: Record<LeadStatus, string> = {
  interested: "Interested",
  new: "New",
  contacted: "Contacted",
  converted: "Converted",
  lost: "Lost",
};

export function LeadStatusBadge({ status }: { status: LeadStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${LEAD_STATUS_STYLES[status]}`}
    >
      {LEAD_STATUS_LABELS[status]}
    </span>
  );
}

type Tone = "positive" | "neutral" | "warning" | "danger";

const TONE_STYLES: Record<Tone, string> = {
  positive: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-400",
  neutral:
    "bg-surface-alt text-text-secondary",
  warning: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-400",
  danger: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-400",
};

export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: Tone;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${TONE_STYLES[tone]}`}
    >
      {children}
    </span>
  );
}

const DOCUMENT_STATUS: Record<DocumentStatus, { label: string; tone: Tone }> = {
  draft: { label: "Draft", tone: "neutral" },
  processing: { label: "Processing", tone: "warning" },
  active: { label: "Published", tone: "positive" },
  failed: { label: "Failed", tone: "danger" },
  inactive: { label: "Inactive", tone: "neutral" },
};

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const { label, tone } = DOCUMENT_STATUS[status];
  return <Badge tone={tone}>{label}</Badge>;
}

const CONVERSATION_STATUS: Record<ConversationStatus, { label: string; tone: Tone }> = {
  open: { label: "Open", tone: "positive" },
  idle: { label: "Idle", tone: "warning" },
  closed: { label: "Closed", tone: "neutral" },
};

export function ConversationStatusBadge({ status }: { status: ConversationStatus }) {
  const { label, tone } = CONVERSATION_STATUS[status];
  return <Badge tone={tone}>{label}</Badge>;
}
