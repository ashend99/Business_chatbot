import { NextResponse } from "next/server";

import { ApiError } from "@/lib/api";

/** Standard error → NextResponse mapping for the `/api/tenant/*` proxy routes. */
export function apiErrorResponse(e: unknown) {
  if (e instanceof ApiError) {
    return NextResponse.json({ error: e.message }, { status: e.status || 502 });
  }
  return NextResponse.json({ error: "Could not reach the server." }, { status: 502 });
}
