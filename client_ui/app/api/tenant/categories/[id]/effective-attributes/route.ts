import { NextResponse, type NextRequest } from "next/server";

import { apiFetch } from "@/lib/api";
import { apiErrorResponse } from "@/lib/route-helpers";
import type { CategoryAttribute } from "@/lib/types";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: NextRequest, { params }: Params) {
  const { id } = await params;
  try {
    const attrs = await apiFetch<CategoryAttribute[]>(`/tenant/categories/${id}/effective-attributes`);
    return NextResponse.json(attrs);
  } catch (e) {
    return apiErrorResponse(e);
  }
}
