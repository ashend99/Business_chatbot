// Pin the locale so server-rendered and client-rendered text always match
// (a viewer's OS locale differing from the server's would otherwise trip
// React's hydration check).
const LOCALE = "en-US";

export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  const min = Math.round(diff / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  if (day < 30) return `${day}d ago`;
  return new Date(iso).toLocaleDateString(LOCALE, { month: "short", day: "numeric" });
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(LOCALE, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** ISO timestamp -> the value an `<input type="datetime-local">` expects
 * (local time, no timezone suffix, minute precision). */
export function toDateTimeInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** The reverse: a datetime-local value (parsed by the browser as local
 * time) -> a UTC ISO timestamp for the API. */
export function fromDateTimeInput(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

/** `currency` is the tenant's admin-set ISO code (see CurrencyProvider) or an
 * order's own snapshotted `currency_code`. */
export function formatMoney(value: string | null, currency = "USD"): string {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return value;
  try {
    return n.toLocaleString(LOCALE, { style: "currency", currency });
  } catch {
    return `${currency} ${n.toFixed(2)}`; // unknown/invalid ISO code
  }
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Best-effort display name from a lead's free-form fields. */
export function leadDisplayName(fields: Record<string, string>): string {
  return (
    fields.name ||
    fields.full_name ||
    fields.contact_name ||
    fields.email ||
    fields.phone ||
    "Unnamed lead"
  );
}
