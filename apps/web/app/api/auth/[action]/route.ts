import { NextResponse } from "next/server";

import { SESSION_COOKIE, apiUrl } from "@/lib/session";

/**
 * Sign-in, sign-up and sign-out, proxied so the token lands in an httpOnly
 * cookie on this origin rather than in the page.
 *
 * Errors come back from the API as {"error": {key, params}} and are passed
 * through untouched: this route localises nothing, because the browser is the
 * only part of the system that knows which language to speak.
 */

const ACTIONS = { login: "login", register: "register", logout: "logout" } as const;

type Action = keyof typeof ACTIONS;

function isAction(value: string): value is Action {
  return value in ACTIONS;
}

/** Fourteen days, matching the session lifetime the API issues. */
const MAX_AGE = 60 * 60 * 24 * 14;

export async function POST(
  request: Request,
  { params }: { params: Promise<{ action: string }> },
) {
  const { action } = await params;
  if (!isAction(action)) {
    return NextResponse.json(
      { error: { key: "auth.error.unknownAction", params: {} } },
      { status: 404 },
    );
  }

  const token = request.headers
    .get("cookie")
    ?.split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(`${SESSION_COOKIE}=`))
    ?.slice(SESSION_COOKIE.length + 1);

  if (action === "logout") {
    // Tell the API to revoke it, then drop the cookie either way: a user who
    // pressed sign out must end up signed out even if the API is down.
    if (token) {
      try {
        await fetch(apiUrl("/api/v1/auth/logout"), {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
      } catch {
        /* Revoking is best effort; clearing the cookie is not. */
      }
    }
    const response = new NextResponse(null, { status: 204 });
    response.cookies.set(SESSION_COOKIE, "", { ...cookieOptions(), maxAge: 0 });
    return response;
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: { key: "auth.error.badRequest", params: {} } },
      { status: 400 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(apiUrl(`/api/v1/auth/${action}`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    return NextResponse.json(
      { error: { key: "error.apiUnreachable.title", params: {} } },
      { status: 503 },
    );
  }

  const payload = await upstream.json().catch(() => null);

  if (!upstream.ok) {
    return NextResponse.json(
      payload ?? { error: { key: "http.error", params: { status: upstream.status } } },
      { status: upstream.status },
    );
  }

  const session = payload as { token: string; user: unknown };
  const response = NextResponse.json({ user: session.user });
  response.cookies.set(SESSION_COOKIE, session.token, cookieOptions());
  return response;
}

function cookieOptions() {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    // Set on HTTPS only in production; a dev server on http would otherwise
    // set a cookie the browser refuses to send back.
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: MAX_AGE,
  };
}
