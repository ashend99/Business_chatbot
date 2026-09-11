import { NextResponse, type NextRequest } from "next/server";

import { ApiError, apiFetch } from "@/lib/api";
import type { LeadFieldDef } from "@/lib/types";

export async function GET() {
  try {
    const defs = await apiFetch<LeadFieldDef[]>("/tenant/lead-field-defs");
    return NextResponse.json(defs);
  } catch (e) {
    return errorResponse(e);
  }
}

export async function PUT(req: NextRequest) {
  const body = await req.json();
  try {
    const defs = await apiFetch<LeadFieldDef[]>("/tenant/lead-field-defs", {
      method: "PUT",
      body,
    });
    return NextResponse.json(defs);
  } catch (e) {
    return errorResponse(e);
  }
}

function errorResponse(e: unknown) {
  if (e instanceof ApiError) {
    return NextResponse.json({ error: e.message }, { status: e.status || 502 });
  }
  return NextResponse.json({ error: "Could not reach the server." }, { status: 502 });
}
