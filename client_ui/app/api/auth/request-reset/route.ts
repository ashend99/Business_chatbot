import { NextResponse, type NextRequest } from "next/server";

import { backendPost } from "@/lib/backend";

/**
 * Ask the backend to email a password-reset link. The backend returns 204
 * whether or not the username exists (so usernames can't be enumerated) —
 * we mirror that and only surface "server unreachable" as an error.
 */
export async function POST(req: NextRequest) {
  const { username } = await req.json();

  const res = await backendPost("/auth/request-password-reset", { username });
  if (!res || (res.status !== 204 && res.status !== 422)) {
    return NextResponse.json(
      { error: "Could not reach the server. Try again." },
      { status: 502 },
    );
  }
  return NextResponse.json({ ok: true });
}
