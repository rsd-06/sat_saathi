import "server-only";

export {
  challengeFor,
  newState,
  newVerifier,
  safeReturnPath,
  statesMatch,
} from "./oauth-pkce";

export const STATE_COOKIE = "satsaathi_oauth_state";
export const VERIFIER_COOKIE = "satsaathi_oauth_verifier";
export const RETURN_COOKIE = "satsaathi_oauth_return";

/** Long enough to sign in unhurriedly, short enough to be useless later. */
export const HANDSHAKE_MAX_AGE = 10 * 60;

export const AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";

export function handshakeCookie() {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: HANDSHAKE_MAX_AGE,
  };
}

/**
 * The client credentials, if this deployment has any.
 *
 * `server-only` at the top of this file is what keeps the secret out of a
 * client bundle: importing it from a component that runs in the browser is a
 * build error rather than a silent leak.
 */
export function googleConfig() {
  const clientId = process.env.GOOGLE_CLIENT_ID ?? "";
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET ?? "";
  return { clientId, clientSecret, configured: Boolean(clientId && clientSecret) };
}

/**
 * Where Google should send the browser back to.
 *
 * Derived from the request rather than configured, so the same code works on
 * localhost and behind a domain — but it must match a URI registered in the
 * Google console exactly, or Google refuses the request outright.
 */
export function redirectUri(request: Request): string {
  const configured = process.env.GOOGLE_REDIRECT_URI;
  if (configured) return configured;
  const url = new URL(request.url);
  return `${url.origin}/api/auth/google/callback`;
}
