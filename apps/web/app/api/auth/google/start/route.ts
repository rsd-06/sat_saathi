import { NextResponse } from "next/server";

import {
  AUTH_URL,
  RETURN_COOKIE,
  STATE_COOKIE,
  VERIFIER_COOKIE,
  challengeFor,
  googleConfig,
  handshakeCookie,
  newState,
  newVerifier,
  redirectUri,
  safeReturnPath,
} from "@/lib/google-oauth";

/**
 * Begin a Google sign-in.
 *
 * Mints the state and the PKCE verifier, keeps them in httpOnly cookies the
 * page cannot read, and sends the browser to Google. Nothing is decided here;
 * the callback does the deciding, and it will not believe a response that
 * does not carry these back.
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const locale = url.searchParams.get("locale") || "en";
  const { clientId, configured } = googleConfig();

  if (!configured) {
    // Not an error page: sign-in by password still works, so send them there
    // with a note rather than a dead end.
    return NextResponse.redirect(
      new URL(`/${locale}/sign-in?error=google_unavailable`, request.url),
    );
  }

  const state = newState();
  const verifier = newVerifier();

  const authorize = new URL(AUTH_URL);
  authorize.searchParams.set("client_id", clientId);
  authorize.searchParams.set("redirect_uri", redirectUri(request));
  authorize.searchParams.set("response_type", "code");
  authorize.searchParams.set("scope", "openid email profile");
  authorize.searchParams.set("state", state);
  authorize.searchParams.set("code_challenge", challengeFor(verifier));
  authorize.searchParams.set("code_challenge_method", "S256");
  // Ask for an account choice every time. Silently reusing whichever Google
  // account the browser happens to be signed into is a common way for people
  // to end up in the wrong account without noticing.
  authorize.searchParams.set("prompt", "select_account");

  const response = NextResponse.redirect(authorize);
  const options = handshakeCookie();
  response.cookies.set(STATE_COOKIE, state, options);
  response.cookies.set(VERIFIER_COOKIE, verifier, options);
  response.cookies.set(
    RETURN_COOKIE,
    safeReturnPath(url.searchParams.get("next"), `/${locale}/dashboard`),
    options,
  );
  return response;
}
