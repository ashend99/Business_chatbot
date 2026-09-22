import { NextResponse, type NextRequest } from "next/server";

import { apiErrorResponse } from "@/lib/route-helpers";
import { getAdminSettings, updateAdminSettings } from "@/lib/tenant-settings";
import type { AdminSettingsUpdatePayload } from "@/lib/types";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: NextRequest, { params }: Params) {
  const { id } = await params;
  try {
    const settings = await getAdminSettings(id);
    return NextResponse.json(settings);
  } catch (e) {
    return apiErrorResponse(e);
  }
}

export async function PATCH(req: NextRequest, { params }: Params) {
  const { id } = await params;
  const body = (await req.json()) as AdminSettingsUpdatePayload;
  try {
    const settings = await updateAdminSettings(id, body);
    return NextResponse.json(settings);
  } catch (e) {
    return apiErrorResponse(e);
  }
}
