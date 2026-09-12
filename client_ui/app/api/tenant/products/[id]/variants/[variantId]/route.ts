import { NextResponse, type NextRequest } from "next/server";

import { apiFetch } from "@/lib/api";
import { apiErrorResponse } from "@/lib/route-helpers";
import type { Variant } from "@/lib/types";

type Params = { params: Promise<{ id: string; variantId: string }> };

export async function PATCH(req: NextRequest, { params }: Params) {
  const { id, variantId } = await params;
  const body = await req.json();
  try {
    const variant = await apiFetch<Variant>(`/tenant/products/${id}/variants/${variantId}`, {
      method: "PATCH",
      body,
    });
    return NextResponse.json(variant);
  } catch (e) {
    return apiErrorResponse(e);
  }
}

export async function DELETE(_req: NextRequest, { params }: Params) {
  const { id, variantId } = await params;
  try {
    await apiFetch<void>(`/tenant/products/${id}/variants/${variantId}`, { method: "DELETE" });
    return new NextResponse(null, { status: 204 });
  } catch (e) {
    return apiErrorResponse(e);
  }
}
