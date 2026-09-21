"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { useCurrency } from "@/components/CurrencyProvider";
import { OrderDetailPanel } from "@/components/orders/OrderDetailPanel";
import { Topbar } from "@/components/Topbar";
import { OrderStatusBadge } from "@/components/ui/Badge";
import { formatMoney, relativeTime } from "@/lib/format";
import type { OrderListItem } from "@/lib/types";

const TABS: { key: string; label: string }[] = [
  { key: "", label: "All" },
  { key: "draft", label: "Draft" },
  { key: "pending_confirmation", label: "Pending" },
  { key: "placed", label: "Placed" },
  { key: "completed", label: "Completed" },
  { key: "cancelled", label: "Cancelled" },
];

function itemsSummary(items: OrderListItem["items"]): string {
  if (items.length === 0) return "(empty cart)";
  const [first, ...rest] = items;
  const label = `${first.quantity}x ${first.product_name}${first.variant_label ? ` (${first.variant_label})` : ""}`;
  return rest.length === 0 ? label : `${label} +${rest.length} more`;
}

export function OrdersView({ orders, total }: { orders: OrderListItem[]; total: number }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const currency = useCurrency();
  const status = params.get("status") ?? "";
  const selectedId = params.get("order");

  function selectTab(key: string) {
    const next = new URLSearchParams(params.toString());
    if (key) next.set("status", key);
    else next.delete("status");
    router.push(`${pathname}${next.toString() ? `?${next}` : ""}`);
  }

  function selectOrder(id: string) {
    const next = new URLSearchParams(params.toString());
    next.set("order", id);
    router.push(`${pathname}?${next}`);
  }

  function closeOrder() {
    const next = new URLSearchParams(params.toString());
    next.delete("order");
    router.push(`${pathname}${next.toString() ? `?${next}` : ""}`);
  }

  return (
    <>
      <Topbar title="Orders" />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden border-r border-border">
          <div className="flex items-center gap-2 border-b border-border px-5 py-3">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => selectTab(tab.key)}
                className={`rounded-lg px-3 py-1.5 text-[12.5px] ${
                  status === tab.key
                    ? "bg-accent font-semibold text-white"
                    : "text-text-secondary hover:bg-surface-alt"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-auto">
            {orders.length === 0 ? (
              <p className="p-8 text-center text-sm text-text-muted">
                {status ? "No orders in this status." : "No orders yet."}
              </p>
            ) : (
              <table className="w-full">
                <thead className="sticky top-0 bg-bg">
                  <tr className="text-left text-[11px] uppercase tracking-wide text-text-muted">
                    <th className="px-5 py-2.5 font-medium">Items</th>
                    <th className="px-5 py-2.5 font-medium">Total</th>
                    <th className="px-5 py-2.5 font-medium">Status</th>
                    <th className="px-5 py-2.5 font-medium">Placed</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((order) => (
                    <tr
                      key={order.id}
                      onClick={() => selectOrder(order.id)}
                      className={`cursor-pointer border-t border-border-subtle ${
                        selectedId === order.id ? "bg-accent-soft" : "hover:bg-surface-alt"
                      }`}
                    >
                      <td className="max-w-0 px-5 py-3 text-[13px] font-medium text-text-primary">
                        <span className="block truncate">{itemsSummary(order.items)}</span>
                      </td>
                      <td className="px-5 py-3 text-[12.5px] text-text-secondary">{formatMoney(order.total, order.currency_code ?? currency)}</td>
                      <td className="px-5 py-3">
                        <OrderStatusBadge status={order.status} />
                      </td>
                      <td className="px-5 py-3 text-[12px] text-text-muted" suppressHydrationWarning>
                        {relativeTime(order.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="border-t border-border px-5 py-2 text-[12px] text-text-muted">
            {total} order{total === 1 ? "" : "s"}
          </div>
        </div>

        {selectedId ? (
          <OrderDetailPanel
            key={selectedId}
            orderId={selectedId}
            onClose={closeOrder}
            onChanged={() => router.refresh()}
          />
        ) : (
          <div className="flex h-full min-w-0 flex-1 items-center justify-center bg-surface">
            <p className="text-sm text-text-muted">No order is selected</p>
          </div>
        )}
      </div>
    </>
  );
}
