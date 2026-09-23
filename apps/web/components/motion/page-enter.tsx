"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

/**
 * A route change lays the new sheet down over the old one.
 *
 * Keyed on the path so React remounts the subtree and the animation runs
 * again — which is the whole mechanism, and why this is a client component
 * with no effects in it. The View Transitions API would be tidier, but it is
 * still experimental in this stack and a demo is the wrong place to find out
 * which browsers disagree.
 */
export function PageEnter({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div key={pathname} className="page-enter">
      {children}
    </div>
  );
}
