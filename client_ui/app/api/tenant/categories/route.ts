import { NextResponse, type NextRequest } from "next/server";

import { apiFetch } from "@/lib/api";
import { apiErrorResponse } from "@/lib/route-helpers";
import type { Category } from "@/lib/types";

export async function POST(req: NextRequest) {
  const body = await req.json();
  try {
    const category = await apiFetch<Category>("/tenant/categories", { method: "POST", body });
    return NextResponse.json(category, { status: 201 });
  } catch (e) {
    return apiErrorResponse(e);
  }
}
