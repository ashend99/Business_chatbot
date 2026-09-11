/** Shared constants safe to import from anywhere (middleware/edge included). */

export const AUTH_COOKIE = "helalien_token";

/**
 * Cookie lifetime in seconds. The backend JWT expires after 60 min
 * (`settings.access_token_expire_minutes`); keep the cookie a touch shorter
 * so we redirect to login before the API starts 401-ing.
 */
export const TOKEN_MAX_AGE = 55 * 60;

export const API_BASE_URL =
  process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

/** Rows per page in the leads list. */
export const LEAD_PAGE_SIZE = 25;
