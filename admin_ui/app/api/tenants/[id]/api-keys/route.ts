import { NextResponse, type NextRequest } from "next/server";

import { apiErrorResponse } from "@/lib/route-helpers";
import { createApiKey, listApiKeys } from "@/lib/tenant-settings";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: NextRequest, { params }: Params) {
  const { id } = await params;
  try {
    const keys = await listApiKeys(id);
    return NextResponse.json(keys);
  } catch (e) {
    return apiErrorResponse(e);
  }
}

export async function POST(_req: NextRequest, { params }: Params) {
  const { id } = await params;
  try {
    const key = await createApiKey(id);
    return NextResponse.json(key, { status: 201 });
  } catch (e) {
    return apiErrorResponse(e);
  }
}
