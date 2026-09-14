/**
 * Thin fetch wrapper around the FastAPI backend.
 *
 * On the server (server components, route handlers) it reads the tenant JWT
 * from the httpOnly `helalien_token` cookie automatically. Client components
 * must not call this directly — they go through the dashboard's own
 * `/api/*` route handlers, which forward the cookie.
 */

import { cookies } from "next/headers";

import { API_BASE_URL, AUTH_COOKIE } from "@/lib/constants";

const BASE_URL = API_BASE_URL;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(
      typeof detail === "object" && detail !== null && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : `Request failed with ${status}`,
    );
    this.name = "ApiError";
  }
}

type FetchOptions = Omit<RequestInit, "body"> & {
  /** JSON-serialisable request body, or a FormData for a file upload (sent as-is, no Content-Type override so fetch sets its own multipart boundary). */
  body?: unknown;
  /** Explicit bearer token — overrides the cookie (used by route handlers). */
  token?: string;
};

export async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const { body, token: explicitToken, headers, ...rest } = options;
  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;

  let token = explicitToken;
  if (!token) {
    try {
      token = (await cookies()).get(AUTH_COOKIE)?.value;
    } catch {
      // Not in a request scope (e.g. build-time) — proceed unauthenticated.
    }
  }

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...rest,
      headers: {
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      body: body === undefined ? undefined : isFormData ? (body as FormData) : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, { detail: "Could not reach the API server." });
  }

  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text();
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
