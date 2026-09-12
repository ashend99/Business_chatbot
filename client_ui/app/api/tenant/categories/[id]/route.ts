import { NextResponse, type NextRequest } from "next/server";

import { apiFetch } from "@/lib/api";
import { apiErrorResponse } from "@/lib/route-helpers";
import type { Category } from "@/lib/types";

type Params = { params: Promise<{ id: string }> };

export async function PATCH(req: NextRequest, { params }: Params) {
  const { id } = await params;
  const body = await req.json();
  try {
    const category = await apiFetch<Category>(`/tenant/categories/${id}`, { method: "PATCH", body });
    return NextResponse.json(category);
  } catch (e) {
    return apiErrorResponse(e);
  }
}

export async function DELETE(_req: NextRequest, { params }: Params) {
  const { id } = await params;
  try {
    await apiFetch<void>(`/tenant/categories/${id}`, { method: "DELETE" });
    return new NextResponse(null, { status: 204 });
  } catch (e) {
    return apiErrorResponse(e);
  }
}
