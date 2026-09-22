import { NextResponse, type NextRequest } from "next/server";

import { apiErrorResponse } from "@/lib/route-helpers";
import { suspendTenant } from "@/lib/tenants";

type Params = { params: Promise<{ id: string }> };

export async function POST(_req: NextRequest, { params }: Params) {
  const { id } = await params;
  try {
    const tenant = await suspendTenant(id);
    return NextResponse.json(tenant);
  } catch (e) {
    return apiErrorResponse(e);
  }
}
