"use client";

import { useEffect, useState } from "react";

import { OrderStatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useConfirm } from "@/components/ui/ConfirmDialog";
import { formatDateTime, formatMoney } from "@/lib/format";
import type { OrderDetail, OrderStatus } from "@/lib/types";

const FULFILLMENT_LABELS: Record<string, string> = {
  type: "Type",
  address: "Address",
  time: "Time",
  needed_by: "Needed by",
};

export function OrderDetailPanel({
  orderId,
  onClose,
  onChanged,
}: {
  orderId: string;
  onClose: () => void;
  onChanged: () => void;
}) {
  const confirm = useConfirm();
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<OrderStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Keyed on `orderId` by the parent, so it remounts fresh on selection change.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/tenant/orders/${orderId}`);
        if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error ?? "Failed to load");
        const data = (await res.json()) as OrderDetail;
        if (cancelled) return;
        setOrder(data);
      } catch (e) {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [orderId]);

  async function setStatus(status: OrderStatus, confirmMsg?: string) {
    if (!order) return;
    if (confirmMsg) {
      const ok = await confirm({
        title: status === "cancelled" ? "Cancel order" : "Mark completed",
        message: confirmMsg,
        confirmLabel: status === "cancelled" ? "Cancel order" : "Mark completed",
        danger: status === "cancelled",
      });
      if (!ok) return;
    }
    setBusy(status);
    setError(null);
    try {
      const res = await fetch(`/api/tenant/orders/${order.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error ?? "Could not update the order.");
      setOrder((prev) => (prev ? { ...prev, status: data.status } : prev));
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update the order.");
    } finally {
      setBusy(null);
    }
  }

  const leadEntries = order ? Object.entries(order.lead_fields) : [];
  const fulfillmentEntries = order?.fulfillment ? Object.entries(order.fulfillment) : [];

  return (
    <aside className="flex h-full min-w-0 flex-1 flex-col overflow-auto border-l border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border-subtle px-5 py-3.5">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="truncate text-[13.5px] font-semibold text-text-primary">
            {order ? formatMoney(order.total) : "Order"}
          </span>
          {order && <OrderStatusBadge status={order.status} />}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {order?.status === "placed" && (
            <>
              <Button size="sm" onClick={() => setStatus("completed")} disabled={busy !== null}>
                {busy === "completed" ? "Saving…" : "Mark completed"}
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={() => setStatus("cancelled", "Cancel this order? This can't be undone.")}
                disabled={busy !== null}
              >
                Cancel
              </Button>
            </>
          )}
          {order?.status === "draft" && (
            <Button
              variant="danger"
              size="sm"
              onClick={() => setStatus("cancelled", "Cancel this draft cart? This can't be undone.")}
              disabled={busy !== null}
            >
              Cancel
            </Button>
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1.5 text-text-muted hover:bg-surface-alt hover:text-text-primary"
          >
            <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {loading && <p className="p-5 text-[12.5px] text-text-muted">Loading…</p>}
      {loadError && !loading && (
        <p className="m-5 rounded-lg bg-red-50 px-3 py-2 text-[12.5px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
          {loadError}
        </p>
      )}
      {error && (
        <p className="mx-5 mt-3 rounded-lg bg-red-50 px-3 py-2 text-[12.5px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
          {error}
        </p>
      )}

      {order && !loading && (
        <div className="flex flex-col gap-5 p-5">
          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-muted">Items</p>
            <div className="overflow-hidden rounded-lg border border-border-subtle">
              <table className="w-full">
                <tbody>
                  {order.items.map((item, i) => (
                    <tr key={i} className={i > 0 ? "border-t border-border-subtle" : ""}>
                      <td className="px-3 py-2 text-[12.5px] text-text-primary">
                        {item.quantity}x {item.product_name}
                        {item.variant_label && (
                          <span className="text-text-muted"> ({item.variant_label})</span>
                        )}
                      </td>
                      <td className="px-3 py-2 text-right text-[12.5px] text-text-secondary">
                        {formatMoney(item.line_total)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-2 flex justify-between px-1 text-[13px] font-semibold text-text-primary">
              <span>Total</span>
              <span>{formatMoney(order.total)}</span>
            </div>
          </div>

          {fulfillmentEntries.length > 0 && (
            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                Fulfillment
              </p>
              <div className="flex flex-col gap-1.5">
                {fulfillmentEntries.map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-3">
                    <span className="text-[12.5px] text-text-muted">{FULFILLMENT_LABELS[key] ?? key}</span>
                    <span className="text-right text-[12.5px] font-medium text-text-primary">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {leadEntries.length > 0 && (
            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                Contact
              </p>
              <div className="flex flex-col gap-1.5">
                {leadEntries.map(([key, value]) => (
                  <div key={key} className="flex justify-between gap-3">
                    <span className="text-[12.5px] capitalize text-text-muted">{key}</span>
                    <span className="text-right text-[12.5px] font-medium text-text-primary">{value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {order.notes && (
            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-muted">Notes</p>
              <p className="text-[12.5px] text-text-primary">{order.notes}</p>
            </div>
          )}

          <div>
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
              Conversation
            </p>
            {order.transcript.length === 0 ? (
              <p className="text-[12.5px] text-text-muted">No linked conversation.</p>
            ) : (
              <div className="flex flex-col gap-2">
                {order.transcript.map((m, i) =>
                  m.role === "system" ? (
                    <p key={i} className="self-center text-[11px] text-text-muted">
                      {m.content}
                    </p>
                  ) : (
                    <div
                      key={i}
                      className={`max-w-[85%] rounded-xl px-3 py-2 text-[12.5px] ${
                        m.role === "user"
                          ? "self-start rounded-bl-sm bg-surface-alt text-text-primary"
                          : "self-end rounded-br-sm bg-accent text-white"
                      }`}
                      title={formatDateTime(m.created_at)}
                    >
                      {m.content}
                    </div>
                  ),
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}
