import "server-only";

import { cookies } from "next/headers";

/**
 * The browser never sees the API token.
 *
 * The API issues an opaque session token and returns it in the response body;
 * this app puts it in an httpOnly cookie on its own origin and attaches it as
 * a bearer credential on the way out. Two consequences worth keeping: no
 * script in the page can read the token, and sign-in does not depend on the
 * API sharing an origin with the app.
 */
export const SESSION_COOKIE = "satsaathi_session";

const API_BASE = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type User = {
  id: string;
  email: string;
  full_name: string;
  department: string | null;
  district: string | null;
  preferred_locale: string;
  created_at: string;
};

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export async function readToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(SESSION_COOKIE)?.value ?? null;
}

/**
 * Who is signed in, or null.
 *
 * Never throws: a page that cannot reach the API should render signed-out
 * rather than error, because the alternative is a blank screen whenever the
 * API restarts.
 */
export async function currentUser(): Promise<User | null> {
  const token = await readToken();
  if (!token) return null;

  try {
    const response = await fetch(apiUrl("/api/v1/auth/me"), {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!response.ok) return null;
    return (await response.json()) as User;
  } catch {
    return null;
  }
}
