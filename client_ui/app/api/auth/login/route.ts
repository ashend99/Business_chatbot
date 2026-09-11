import { NextResponse, type NextRequest } from "next/server";

import { AUTH_COOKIE, TOKEN_MAX_AGE } from "@/lib/constants";
import { backendPost } from "@/lib/backend";

export async function POST(req: NextRequest) {
  const { username, password } = await req.json();

  const res = await backendPost("/auth/tenant/login", { username, password });
  if (!res) {
    return NextResponse.json(
      { error: "Could not reach the server. Try again." },
      { status: 502 },
    );
  }

  if (!res.ok) {
    const message =
      res.status === 403
        ? "This account is suspended."
        : res.status === 401
          ? "Incorrect username or password."
          : "Could not reach the server. Try again.";
    return NextResponse.json(
      { error: message },
      { status: res.status === 401 || res.status === 403 ? res.status : 502 },
    );
  }

  const { access_token } = (await res.json()) as { access_token: string };

  const response = NextResponse.json({ ok: true });
  response.cookies.set(AUTH_COOKIE, access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: TOKEN_MAX_AGE,
  });
  return response;
}
