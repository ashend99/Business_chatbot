import { NextResponse, type NextRequest } from "next/server";

import { apiErrorResponse } from "@/lib/route-helpers";
import { createTenant, listTenants } from "@/lib/tenants";
import type { TenantCreatePayload } from "@/lib/types";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  try {
    const result = await listTenants({
      isActive: sp.has("is_active") ? sp.get("is_active") === "true" : undefined,
      search: sp.get("search") ?? undefined,
      page: sp.has("page") ? Number(sp.get("page")) : undefined,
      pageSize: sp.has("page_size") ? Number(sp.get("page_size")) : undefined,
    });
    return NextResponse.json(result);
  } catch (e) {
    return apiErrorResponse(e);
  }
}

export async function POST(req: NextRequest) {
  const body = (await req.json()) as TenantCreatePayload;
  try {
    const tenant = await createTenant(body);
    return NextResponse.json(tenant, { status: 201 });
  } catch (e) {
    return apiErrorResponse(e);
  }
}
