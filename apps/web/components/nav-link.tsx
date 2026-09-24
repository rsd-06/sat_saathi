"use client";

import type { ReactNode } from "react";
import { usePathname } from "next/navigation";

import { Link } from "@/i18n/navigation";

/**
 * A nav item that knows whether you are already on it.
 *
 * Marked with a rule under the label rather than a colour change alone, so
 * "where am I" survives a monochrome screen and a colour-blind reader.
 * `aria-current` carries the same fact to a screen reader.
 */
export function NavLink({
  href,
  children,
  className = "",
}: {
  href: string;
  children: ReactNode;
  className?: string;
}) {
  const pathname = usePathname();
  // The pathname carries a locale prefix the href does not, so compare on the
  // segment rather than the whole string.
  const current = pathname.replace(/^\/[a-z]{2}(?=\/|$)/, "") || "/";
  const active = current === href || current.startsWith(`${href}/`);

  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`border-b-2 pb-0.5 transition-colors ${
        active
          ? "border-accent text-ink"
          : "text-ink-muted hover:text-ink border-transparent"
      } ${className}`}
    >
      {children}
    </Link>
  );
}
