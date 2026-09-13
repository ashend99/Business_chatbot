import { NextResponse, type NextRequest } from "next/server";

import { apiFetch } from "@/lib/api";
import { apiErrorResponse } from "@/lib/route-helpers";
import type { ConversationDetail } from "@/lib/types";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: NextRequest, { params }: Params) {
  const { id } = await params;
  try {
    const conversation = await apiFetch<ConversationDetail>(`/tenant/conversations/${id}`);
    return NextResponse.json(conversation);
  } catch (e) {
    return apiErrorResponse(e);
  }
}
