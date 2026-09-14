import { NextResponse, type NextRequest } from "next/server";

import { API_BASE_URL } from "@/lib/constants";

/**
 * Test-widget proxy for POST /bot/message. Unlike lib/api.ts's apiFetch, this
 * authenticates with the tenant's api_secret key (X-Api-Key) rather than the
 * dashboard's tenant JWT cookie -- this is the same auth shape a real channel
 * adapter (n8n, the embedded site widget) would use, so the browser never
 * sees the secret, only this same-origin route does.
 */
export async function POST(req: NextRequest) {
  const apiKey = process.env.BOT_API_SECRET;
  if (!apiKey) {
    return NextResponse.json({ error: "BOT_API_SECRET is not configured." }, { status: 500 });
  }

  const body = await req.json();
  try {
    const res = await fetch(`${API_BASE_URL}/bot/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Api-Key": apiKey },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      return NextResponse.json({ error: data.detail ?? "Bot request failed." }, { status: res.status });
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "Could not reach the bot API." }, { status: 502 });
  }
}
