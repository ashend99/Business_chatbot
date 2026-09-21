import { NextResponse, type NextRequest } from "next/server";

import { apiFetch } from "@/lib/api";
import { apiErrorResponse } from "@/lib/route-helpers";
import type { TenantSettingsResponse } from "@/lib/types";

export async function GET() {
  try {
    return NextResponse.json(await apiFetch<TenantSettingsResponse>("/tenant/settings"));
  } catch (e) {
    return apiErrorResponse(e);
  }
}

export async function PATCH(req: NextRequest) {
  const body = await req.json();
  try {
    const res = await apiFetch<TenantSettingsResponse>("/tenant/settings", { method: "PATCH", body });
    return NextResponse.json(res);
  } catch (e) {
    return apiErrorResponse(e);
  }
}
