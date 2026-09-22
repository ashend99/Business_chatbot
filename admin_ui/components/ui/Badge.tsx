type Tone = "positive" | "neutral" | "warning" | "danger";

const TONE_STYLES: Record<Tone, string> = {
  positive: "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-400",
  neutral: "bg-surface-alt text-text-secondary",
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

export function TenantStatusBadge({ isActive }: { isActive: boolean }) {
  return isActive ? <Badge tone="positive">Active</Badge> : <Badge tone="danger">Suspended</Badge>;
}

export function ActivationBadge({ activated }: { activated: boolean }) {
  return activated ? <Badge tone="positive">Activated</Badge> : <Badge tone="warning">Not activated</Badge>;
}

export function ApiKeyStatusBadge({ revokedAt }: { revokedAt: string | null }) {
  return revokedAt ? <Badge tone="neutral">Revoked</Badge> : <Badge tone="positive">Active</Badge>;
}
