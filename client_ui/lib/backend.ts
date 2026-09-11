import { API_BASE_URL } from "@/lib/constants";

/**
 * Server-side POST to the FastAPI backend. Returns the raw Response on any
 * HTTP status; returns `null` only when the backend is unreachable (so route
 * handlers can map that to a clean 502 instead of a thrown 500).
 */
export async function backendPost(path: string, body: unknown): Promise<Response | null> {
  try {
    return await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    return null;
  }
}
