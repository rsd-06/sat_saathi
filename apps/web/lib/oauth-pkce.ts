import { createHash, randomBytes, timingSafeEqual } from "node:crypto";

/**
 * The two secrets that make a sign-in redirect safe to come back from.
 *
 * `state` is proof the response belongs to a request this browser started.
 * Without it, an attacker can send someone a crafted callback URL and have
 * their browser complete a sign-in to the attacker's account.
 *
 * The PKCE verifier is proof that whoever redeems the authorization code is
 * whoever asked for it. Without it, a code intercepted in transit — in a
 * server log, a referrer header, a shared machine's history — can be spent
 * by somebody else.
 *
 * Kept apart from the configuration that reads the client secret, so these
 * stay ordinary functions a test can call directly.
 */

export function base64url(input: Buffer): string {
  return input.toString("base64url");
}

export function newState(): string {
  return base64url(randomBytes(32));
}

export function newVerifier(): string {
  // 32 random bytes, base64url encoded: within the 43-128 character range
  // RFC 7636 requires, with no padding to strip.
  return base64url(randomBytes(32));
}

export function challengeFor(verifier: string): string {
  return base64url(createHash("sha256").update(verifier).digest());
}

/**
 * Compare in constant time.
 *
 * A plain `===` on a secret leaks its prefix through timing. Empty or missing
 * values never match: a callback carrying no state must fail closed, and
 * calling undefined equal to undefined would defeat the whole check.
 */
export function statesMatch(a: string | undefined, b: string | undefined): boolean {
  if (!a || !b) return false;
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  if (left.length !== right.length) return false;
  return timingSafeEqual(left, right);
}

/**
 * A safe place to land afterwards.
 *
 * Only same-origin paths. An open redirect here would let a crafted sign-in
 * link bounce someone to another site carrying the trust of this one.
 */
export function safeReturnPath(value: string | null | undefined, fallback: string) {
  if (!value) return fallback;
  if (!value.startsWith("/") || value.startsWith("//")) return fallback;
  return value;
}
