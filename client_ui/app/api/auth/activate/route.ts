import { NextResponse, type NextRequest } from "next/server";

import { backendPost } from "@/lib/backend";

/** Step 1 of activation: confirm the invite token belongs to this email. */
export async function POST(req: NextRequest) {
  const { token, email } = await req.json();

  const res = await backendPost("/auth/activate", { token, email });
  if (!res) {
    return NextResponse.json(
      { error: "Could not reach the server. Try again." },
      { status: 502 },
    );
  }

  if (res.status === 204) return NextResponse.json({ ok: true });

  return NextResponse.json(
    {
      error:
        res.status === 400
          ? "That link or email doesn't match. Check the email and try again."
          : "Could not reach the server. Try again.",
    },
    { status: res.status === 400 ? 400 : 502 },
  );
}
