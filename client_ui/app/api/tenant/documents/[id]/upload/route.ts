import { NextResponse, type NextRequest } from "next/server";

import { apiFetch } from "@/lib/api";
import { apiErrorResponse } from "@/lib/route-helpers";
import type { DocumentDetail } from "@/lib/types";

type Params = { params: Promise<{ id: string }> };

export async function POST(req: NextRequest, { params }: Params) {
  const { id } = await params;
  const formData = await req.formData();
  try {
    const document = await apiFetch<DocumentDetail>(`/tenant/documents/${id}/upload`, {
      method: "POST",
      body: formData,
    });
    return NextResponse.json(document);
  } catch (e) {
    return apiErrorResponse(e);
  }
}
