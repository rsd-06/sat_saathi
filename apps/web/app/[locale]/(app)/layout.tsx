import type { ReactNode } from "react";
import { redirect } from "next/navigation";

import { getSession } from "@/lib/session";

/**
 * The guard for every page that shows somebody's own work.
 *
 * The proxy only checks that a session cookie exists, which is all it can do
 * without a network call on every navigation. This checks that the API still
 * honours it. A dead session goes through /api/auth/expired, which clears the
 * cookie — the proxy would otherwise go on believing it — and lands on
 * sign-in with a note saying why.
 *
 * An unreachable API is left alone on purpose. The page renders, its own
 * requests show that the service is down, and the person stays signed in for
 * when it comes back.
 */
export default async function SignedInLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const session = await getSession();

  if (session.state === "invalid" || session.state === "signed-out") {
    redirect(`/api/auth/expired?locale=${encodeURIComponent(locale)}`);
  }

  return children;
}
