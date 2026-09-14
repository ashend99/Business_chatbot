import { NextResponse, type NextRequest } from "next/server";

import { apiFetch } from "@/lib/api";
import { apiErrorResponse } from "@/lib/route-helpers";
import type { DocumentDetail } from "@/lib/types";

type Params = { params: Promise<{ id: string }> };

export async function POST(_req: NextRequest, { params }: Params) {
  const { id } = await params;
  try {
    const document = await apiFetch<DocumentDetail>(`/tenant/documents/${id}/retry`, { method: "POST" });
    return NextResponse.json(document);
  } catch (e) {
    return apiErrorResponse(e);
  }
}
