import { NextResponse, type NextRequest } from "next/server";

import { apiErrorResponse } from "@/lib/route-helpers";
import { resendInvite } from "@/lib/tenants";

type Params = { params: Promise<{ id: string }> };

export async function POST(_req: NextRequest, { params }: Params) {
  const { id } = await params;
  try {
    await resendInvite(id);
    return new NextResponse(null, { status: 204 });
  } catch (e) {
    return apiErrorResponse(e);
  }
}
