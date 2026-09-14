import { NextResponse, type NextRequest } from "next/server";

import { apiFetch } from "@/lib/api";
import { apiErrorResponse } from "@/lib/route-helpers";
import type { OrderDetail } from "@/lib/types";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: NextRequest, { params }: Params) {
  const { id } = await params;
  try {
    const order = await apiFetch<OrderDetail>(`/tenant/orders/${id}`);
    return NextResponse.json(order);
  } catch (e) {
    return apiErrorResponse(e);
  }
}

export async function PATCH(req: NextRequest, { params }: Params) {
  const { id } = await params;
  const body = await req.json();
  try {
    const order = await apiFetch<OrderDetail>(`/tenant/orders/${id}`, { method: "PATCH", body });
    return NextResponse.json(order);
  } catch (e) {
    return apiErrorResponse(e);
  }
}
