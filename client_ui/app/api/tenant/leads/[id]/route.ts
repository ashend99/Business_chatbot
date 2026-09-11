import { NextResponse, type NextRequest } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import type { Lead, LeadDetail, LeadUpdate } from "@/lib/types";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: NextRequest, { params }: Params) {
  const { id } = await params;
  try {
    const lead = await apiFetch<LeadDetail>(`/tenant/leads/${id}`);
    return NextResponse.json(lead);
  } catch (e) {
    return errorResponse(e);
  }
}

export async function PATCH(req: NextRequest, { params }: Params) {
  const { id } = await params;
  const body = (await req.json()) as LeadUpdate;
  try {
    const lead = await apiFetch<Lead>(`/tenant/leads/${id}`, {
      method: "PATCH",
      body,
    });
    return NextResponse.json(lead);
  } catch (e) {
    return errorResponse(e);
  }
}

function errorResponse(e: unknown) {
  if (e instanceof ApiError) {
    return NextResponse.json({ error: e.message }, { status: e.status });
  }
  return NextResponse.json({ error: "Could not reach the server." }, { status: 502 });
}
