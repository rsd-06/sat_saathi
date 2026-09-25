import { NextResponse } from "next/server";

import { safeReturnPath } from "@/lib/oauth-pkce";
import { SESSION_COOKIE } from "@/lib/session";

/**
 * Clear a session the API no longer honours, then go to sign-in.
 *
 * Pages cannot delete a cookie while they render, so a page that finds its
 * session dead sends the browser here instead. Without this, a stale cookie —
 * left behind by a database reset, a revoked session, or a move to a new
 * database — makes the guard bounce every visit to /sign-in back to the
 * dashboard, and the person can never reach the form.
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const locale = url.searchParams.get("locale") || "en";
  const next = safeReturnPath(url.searchParams.get("next"), "");

  const target = new URL(`/${locale}/sign-in`, request.url);
  target.searchParams.set("error", "session_expired");
  if (next) target.searchParams.set("next", next);

  const response = NextResponse.redirect(target);
  response.cookies.set(SESSION_COOKIE, "", {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 0,
  });
  return response;
}
