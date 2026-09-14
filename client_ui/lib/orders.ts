import "server-only";

import { apiFetch } from "@/lib/api";
import type { OrderListResponse, OrderStatus } from "@/lib/types";

export type OrderListParams = {
  status?: OrderStatus;
  search?: string;
  page?: number;
  pageSize?: number;
};

export function listOrders(params: OrderListParams = {}): Promise<OrderListResponse> {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  if (params.search) q.set("search", params.search);
  q.set("page", String(params.page ?? 1));
  q.set("page_size", String(params.pageSize ?? 50));
  return apiFetch<OrderListResponse>(`/tenant/orders?${q.toString()}`);
}
