import { NextResponse, type NextRequest } from "next/server";

import { apiErrorResponse } from "@/lib/route-helpers";
import { revokeApiKey } from "@/lib/tenant-settings";

type Params = { params: Promise<{ id: string; keyId: string }> };

export async function DELETE(_req: NextRequest, { params }: Params) {
  const { id, keyId } = await params;
  try {
    const key = await revokeApiKey(id, keyId);
    return NextResponse.json(key);
  } catch (e) {
    return apiErrorResponse(e);
  }
}
