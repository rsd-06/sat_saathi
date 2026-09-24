import { NextResponse } from "next/server";

import {
  RETURN_COOKIE,
  STATE_COOKIE,
  VERIFIER_COOKIE,
  googleConfig,
  redirectUri,
  safeReturnPath,
  statesMatch,
} from "@/lib/google-oauth";
import { SESSION_COOKIE, apiUrl } from "@/lib/session";

const TOKEN_URL = "https://oauth2.googleapis.com/token";
const MAX_AGE = 60 * 60 * 24 * 14;

/**
 * Come back from Google, and decide whether to believe it.
 *
 * In order: the state must match the one this browser left with, the code is
 * redeemed with the PKCE verifier, and the resulting ID token goes to the API
 * — which verifies its signature, issuer, audience and expiry itself. This
 * route never inspects the token's contents; reading claims out of an
 * unverified JWT is how people end up trusting one.
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const locale = url.pathname.split("/")[1] ?? "en";

  const cookieOf = (name: string) =>
    request.headers
      .get("cookie")
      ?.split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith(`${name}=`))
      ?.slice(name.length + 1);

  const returnTo = safeReturnPath(cookieOf(RETURN_COOKIE), "/en/dashboard");
  const signInPath = returnTo.split("/")[1] || locale;

  const fail = (reason: string) => {
    const response = NextResponse.redirect(
      new URL(`/${signInPath}/sign-in?error=${reason}`, request.url),
    );
    // The handshake is spent either way; leaving it behind would let a failed
    // attempt be retried with a state somebody else has now seen.
    clearHandshake(response);
    return response;
  };

  // Google reports a refusal by redirecting here with an error, not by
  // failing. Someone who pressed cancel is not an error to report loudly.
  const denied = url.searchParams.get("error");
  if (denied) return fail(denied === "access_denied" ? "cancelled" : "google_failed");

  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const verifier = cookieOf(VERIFIER_COOKIE);

  if (!code || !statesMatch(state ?? undefined, cookieOf(STATE_COOKIE))) {
    // Either the response was not started here, or the handshake expired.
    return fail("state_mismatch");
  }
  if (!verifier) return fail("state_mismatch");

  const { clientId, clientSecret, configured } = googleConfig();
  if (!configured) return fail("google_unavailable");

  let idToken: string;
  try {
    const exchange = await fetch(TOKEN_URL, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        code,
        client_id: clientId,
        client_secret: clientSecret,
        redirect_uri: redirectUri(request),
        grant_type: "authorization_code",
        code_verifier: verifier,
      }),
    });
    if (!exchange.ok) return fail("google_failed");
    const payload = (await exchange.json()) as { id_token?: string };
    if (!payload.id_token) return fail("google_failed");
    idToken = payload.id_token;
  } catch {
    return fail("google_failed");
  }

  let session: { token: string };
  try {
    const upstream = await fetch(apiUrl("/api/v1/auth/google"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken, preferred_locale: signInPath }),
    });
    if (!upstream.ok) {
      const body = await upstream.json().catch(() => null);
      const key: string = body?.error?.key ?? "";
      // The one refusal worth naming: an address Google would not vouch for,
      // on an account that already exists. The person needs to know to use
      // their password instead, not to try Google again.
      return fail(
        key === "auth.error.googleUnverifiedEmail" ? "unverified_email" : "google_failed",
      );
    }
    session = (await upstream.json()) as { token: string };
  } catch {
    return fail("api_unreachable");
  }

  const response = NextResponse.redirect(new URL(returnTo, request.url));
  clearHandshake(response);
  response.cookies.set(SESSION_COOKIE, session.token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: MAX_AGE,
  });
  return response;
}

function clearHandshake(response: NextResponse) {
  for (const name of [STATE_COOKIE, VERIFIER_COOKIE, RETURN_COOKIE]) {
    response.cookies.set(name, "", {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 0,
    });
  }
}
