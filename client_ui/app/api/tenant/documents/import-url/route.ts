import { NextResponse, type NextRequest } from "next/server";

import { apiFetch } from "@/lib/api";
import { apiErrorResponse } from "@/lib/route-helpers";
import type { DocumentDetail } from "@/lib/types";

export async function POST(req: NextRequest) {
  const body = await req.json();
  try {
    const document = await apiFetch<DocumentDetail>("/tenant/documents/import-url", {
      method: "POST",
      body,
    });
    return NextResponse.json(document, { status: 201 });
  } catch (e) {
    return apiErrorResponse(e);
  }
}
