import { NextResponse, type NextRequest } from "next/server";

import { apiFetch } from "@/lib/api";
import { apiErrorResponse } from "@/lib/route-helpers";
import type { Variant } from "@/lib/types";

type Params = { params: Promise<{ id: string }> };

export async function POST(req: NextRequest, { params }: Params) {
  const { id } = await params;
  const body = await req.json();
  try {
    const variant = await apiFetch<Variant>(`/tenant/products/${id}/variants`, {
      method: "POST",
      body,
    });
    return NextResponse.json(variant, { status: 201 });
  } catch (e) {
    return apiErrorResponse(e);
  }
}
