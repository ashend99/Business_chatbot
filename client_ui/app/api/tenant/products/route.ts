import { NextResponse, type NextRequest } from "next/server";

import { apiFetch } from "@/lib/api";
import { apiErrorResponse } from "@/lib/route-helpers";
import type { ProductWithVariants } from "@/lib/types";

export async function POST(req: NextRequest) {
  const body = await req.json();
  try {
    const product = await apiFetch<ProductWithVariants>("/tenant/products", { method: "POST", body });
    return NextResponse.json(product, { status: 201 });
  } catch (e) {
    return apiErrorResponse(e);
  }
}
