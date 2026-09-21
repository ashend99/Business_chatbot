import { NextResponse, type NextRequest } from "next/server";

import { backendPost } from "@/lib/backend";

/** Set a new password using the token from the reset email. */
export async function POST(req: NextRequest) {
  const { token, password } = await req.json();

  const res = await backendPost("/auth/reset-password", { token, password });
  if (!res) {
    return NextResponse.json(
      { error: "Could not reach the server. Try again." },
      { status: 502 },
    );
  }

  if (res.status === 204) return NextResponse.json({ ok: true });

  // 400 = bad/expired/used token; 422 = password failed backend validation.
  if (res.status === 400 || res.status === 422) {
    return NextResponse.json(
      {
        error:
          res.status === 422
            ? "Password must be at least 8 characters."
            : "This reset link is invalid or has expired. Request a new one.",
      },
      { status: res.status },
    );
  }
  return NextResponse.json(
    { error: "Could not reach the server. Try again." },
    { status: 502 },
  );
}
