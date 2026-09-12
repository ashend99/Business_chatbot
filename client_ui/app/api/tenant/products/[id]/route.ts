import { NextResponse, type NextRequest } from "next/server";

import { apiFetch } from "@/lib/api";
import { apiErrorResponse } from "@/lib/route-helpers";
import type { Product, ProductWithVariants } from "@/lib/types";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: NextRequest, { params }: Params) {
  const { id } = await params;
  try {
    const product = await apiFetch<ProductWithVariants>(`/tenant/products/${id}`);
    return NextResponse.json(product);
  } catch (e) {
    return apiErrorResponse(e);
  }
}

export async function PATCH(req: NextRequest, { params }: Params) {
  const { id } = await params;
  const body = await req.json();
  try {
    const product = await apiFetch<Product>(`/tenant/products/${id}`, { method: "PATCH", body });
    return NextResponse.json(product);
  } catch (e) {
    return apiErrorResponse(e);
  }
}

export async function DELETE(_req: NextRequest, { params }: Params) {
  const { id } = await params;
  try {
    await apiFetch<void>(`/tenant/products/${id}`, { method: "DELETE" });
    return new NextResponse(null, { status: 204 });
  } catch (e) {
    return apiErrorResponse(e);
  }
}
