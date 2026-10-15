// Base URL of the API as seen by the browser (NEXT_PUBLIC_API_URL, baked in at build time).
// Every route in lib/api.ts already starts with "/api/", so the base must NOT end with "/api":
// a trailing "/api" (or "/") is stripped here, otherwise requests would hit "/api/api/...".
export const DEFAULT_API_URL = "http://localhost:8000";

export function apiBase(raw: string | undefined): string {
  let base = (raw ?? "").trim();
  if (!base) return DEFAULT_API_URL; // empty in .env = default
  base = base.replace(/\/+$/, "");
  while (/\/api$/i.test(base)) base = base.slice(0, -4).replace(/\/+$/, "");
  return base || DEFAULT_API_URL;
}
