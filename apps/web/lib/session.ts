import "server-only";

import { cache } from "react";
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

const API_BASE =
  process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type User = {
  id: string;
  email: string;
  full_name: string;
  department: string | null;
  district: string | null;
  preferred_locale: string;
  created_at: string;
};

/**
 * Four answers, not two.
 *
 * "No cookie" and "a cookie the API no longer honours" need different
 * handling: the second has to be cleared, or the guard keeps treating a dead
 * session as a live one and the person can never reach the sign-in form.
 * "The API did not answer" is different again — signing someone out because
 * the API blinked would be its own bug.
 */
export type Session =
  | { state: "signed-in"; user: User; token: string }
  | { state: "signed-out" }
  | { state: "invalid" }
  | { state: "unreachable" };

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export async function readToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(SESSION_COOKIE)?.value ?? null;
}

/**
 * Who is signed in, asked once per request.
 *
 * `cache` makes every caller in one render share one answer. The header, the
 * page and the guard all want to know, and against a hosted database each
 * separate ask is a round trip somebody waits for.
 */
export const getSession = cache(async (): Promise<Session> => {
  const token = await readToken();
  if (!token) return { state: "signed-out" };

  try {
    const response = await fetch(apiUrl("/api/v1/auth/me"), {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    if (response.status === 401) return { state: "invalid" };
    if (!response.ok) return { state: "unreachable" };
    return { state: "signed-in", user: (await response.json()) as User, token };
  } catch {
    return { state: "unreachable" };
  }
});

/** The signed-in user, or null for every other state. */
export async function currentUser(): Promise<User | null> {
  const session = await getSession();
  return session.state === "signed-in" ? session.user : null;
}
