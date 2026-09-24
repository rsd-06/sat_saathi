import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";

import {
  challengeFor,
  newState,
  newVerifier,
  safeReturnPath,
  statesMatch,
} from "./oauth-pkce";

describe("PKCE", () => {
  it("makes a verifier within the length the spec allows", () => {
    // RFC 7636 requires 43-128 characters; a shorter one weakens the whole
    // exchange and a longer one is rejected outright.
    for (let i = 0; i < 20; i += 1) {
      const verifier = newVerifier();
      expect(verifier.length).toBeGreaterThanOrEqual(43);
      expect(verifier.length).toBeLessThanOrEqual(128);
      expect(verifier).toMatch(/^[A-Za-z0-9\-._~]+$/);
    }
  });

  it("never makes the same verifier twice", () => {
    const seen = new Set(Array.from({ length: 200 }, () => newVerifier()));
    expect(seen.size).toBe(200);
  });

  it("derives the challenge as the S256 hash of the verifier", () => {
    const verifier = newVerifier();

    const expected = createHash("sha256").update(verifier).digest("base64url");
    expect(challengeFor(verifier)).toBe(expected);
  });

  it("gives a different challenge for a different verifier", () => {
    expect(challengeFor("one")).not.toBe(challengeFor("two"));
  });
});

describe("state", () => {
  it("never repeats", () => {
    const seen = new Set(Array.from({ length: 200 }, () => newState()));
    expect(seen.size).toBe(200);
  });

  it("matches only an identical value", () => {
    const state = newState();

    expect(statesMatch(state, state)).toBe(true);
    expect(statesMatch(state, newState())).toBe(false);
  });

  it("refuses a missing value rather than treating it as a match", () => {
    // A callback that carries no state must fail closed. Comparing undefined
    // to undefined and calling it equal would defeat the whole check.
    expect(statesMatch(undefined, undefined)).toBe(false);
    expect(statesMatch("", "")).toBe(false);
    expect(statesMatch("abc", undefined)).toBe(false);
    expect(statesMatch(undefined, "abc")).toBe(false);
  });

  it("refuses a value that merely starts the same", () => {
    expect(statesMatch("abcdef", "abc")).toBe(false);
  });
});

describe("return path", () => {
  it("keeps a same-origin path", () => {
    expect(safeReturnPath("/en/workspace", "/en/dashboard")).toBe("/en/workspace");
  });

  it.each([
    "https://evil.example/steal",
    "//evil.example/steal",
    "http://evil.example",
    "javascript:alert(1)",
    "evil.example",
  ])("refuses %s and falls back", (value) => {
    // An open redirect here would let a crafted sign-in link send someone
    // elsewhere carrying the trust of arriving from this site.
    expect(safeReturnPath(value, "/en/dashboard")).toBe("/en/dashboard");
  });

  it("falls back when there is nothing to return to", () => {
    expect(safeReturnPath(null, "/en/dashboard")).toBe("/en/dashboard");
    expect(safeReturnPath(undefined, "/en/dashboard")).toBe("/en/dashboard");
    expect(safeReturnPath("", "/en/dashboard")).toBe("/en/dashboard");
  });
});
