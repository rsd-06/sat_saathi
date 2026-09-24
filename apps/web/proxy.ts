import createMiddleware from "next-intl/middleware";
import { NextResponse, type NextRequest } from "next/server";

import { routing, locales } from "./i18n/routing";

const intl = createMiddleware(routing);

const SESSION_COOKIE = "satsaathi_session";

/** Everything that shows somebody's own work. */
const PROTECTED = ["/dashboard", "/workspace", "/history", "/review", "/settings", "/jobs"];

function firstSegment(pathname: string): string {
  return pathname.split("/")[1] ?? "";
}

function isLocale(segment: string): boolean {
  return (locales as readonly string[]).includes(segment);
}

function pathWithoutLocale(pathname: string): string {
  const [, first, ...rest] = pathname.split("/");
  return isLocale(first ?? "")
    ? `/${rest.join("/")}`.replace(/\/$/, "") || "/"
    : pathname;
}

function localeOf(pathname: string): string {
  const first = firstSegment(pathname);
  return isLocale(first) ? first : routing.defaultLocale;
}

/**
 * Locale routing first, then the guard.
 *
 * The cookie is only checked for presence here. Whether it is still valid is
 * the API's answer to give, and asking it on every navigation would put a
 * network round trip in front of every page. The signed-in layout asks
 * instead, and clears a cookie the API no longer honours.
 *
 * This deliberately does not send a cookie-holder away from /sign-in. It used
 * to, and a stale cookie — left by a database reset or a move to a new
 * database — then bounced every visit to /sign-in onto a dashboard that could
 * not load, so the form was unreachable. The sign-in page decides that itself,
 * against the API.
 */
export default function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const route = pathWithoutLocale(pathname);
  const locale = localeOf(pathname);
  const signedIn = Boolean(request.cookies.get(SESSION_COOKIE)?.value);

  if (!signedIn && PROTECTED.some((p) => route === p || route.startsWith(`${p}/`))) {
    const url = new URL(`/${locale}/sign-in`, request.url);
    // Come back to where they were trying to go, not to a generic landing.
    url.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(url);
  }

  return intl(request);
}

export const config = {
  matcher: "/((?!api|_next|_vercel|.*\\..*).*)",
};
