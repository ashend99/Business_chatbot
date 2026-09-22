import { NextResponse, type NextRequest } from "next/server";

import { apiErrorResponse } from "@/lib/route-helpers";
import { getTenant, updateTenant } from "@/lib/tenants";
import type { TenantUpdatePayload } from "@/lib/types";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: NextRequest, { params }: Params) {
  const { id } = await params;
  try {
    const tenant = await getTenant(id);
    return NextResponse.json(tenant);
  } catch (e) {
    return apiErrorResponse(e);
  }
}

export async function PATCH(req: NextRequest, { params }: Params) {
  const { id } = await params;
  const body = (await req.json()) as TenantUpdatePayload;
  try {
    const tenant = await updateTenant(id, body);
    return NextResponse.json(tenant);
  } catch (e) {
    return apiErrorResponse(e);
  }
}
