import { NextResponse, type NextRequest } from "next/server";

import { AUTH_COOKIE, TOKEN_MAX_AGE } from "@/lib/constants";
import { backendPost } from "@/lib/backend";

/**
 * Step 2 of activation: create the dashboard login with the same invite
 * token plus a username/password, then immediately log the user in.
 */
export async function POST(req: NextRequest) {
  const { token, username, password } = await req.json();

  const res = await backendPost("/auth/activate/set-credentials", {
    token,
    username,
    password,
  });
  if (!res) {
    return NextResponse.json(
      { error: "Could not reach the server. Try again." },
      { status: 502 },
    );
  }

  if (res.status !== 204) {
    return NextResponse.json(
      {
        error:
          res.status === 409
            ? "That username is already taken."
            : res.status === 400
              ? "This activation link is invalid or has expired."
              : "Could not reach the server. Try again.",
      },
      { status: res.status === 409 || res.status === 400 ? res.status : 502 },
    );
  }

  // Auto-login with the freshly created credentials.
  const loginRes = await backendPost("/auth/tenant/login", { username, password });
  if (!loginRes || !loginRes.ok) {
    // Credentials were created fine — just send them to the login page.
    return NextResponse.json({ ok: true, login: false });
  }

  const { access_token } = (await loginRes.json()) as { access_token: string };
  const response = NextResponse.json({ ok: true, login: true });
  response.cookies.set(AUTH_COOKIE, access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: TOKEN_MAX_AGE,
  });
  return response;
}
