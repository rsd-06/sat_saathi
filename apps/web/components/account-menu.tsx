"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";

/**
 * Who is signed in, and the way out.
 *
 * Sign-out clears the cookie through this app's own route, then refreshes so
 * every server component re-renders signed-out. Navigating without the
 * refresh would leave a cached tree that still believes it has a user.
 */
export function AccountMenu({
  name,
  email,
  locale,
}: {
  name: string;
  email: string;
  locale: string;
}) {
  const t = useTranslations();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function signOut() {
    setSigningOut(true);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch {
      /* The cookie is cleared server-side either way. */
    }
    router.replace(`/${locale}`);
    router.refresh();
  }

  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

  return (
    <div ref={container} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="border-rule-strong text-ink hover:border-accent flex items-center gap-2 rounded-xs border px-2 py-1 text-sm transition-colors"
      >
        <span
          aria-hidden
          className="bg-accent-wash text-accent grid size-5 place-items-center text-[0.625rem] font-medium"
        >
          {initials || "—"}
        </span>
        <span className="hidden max-w-[10rem] truncate sm:inline">{name}</span>
      </button>

      {open && (
        <div
          role="menu"
          className="border-rule-strong bg-paper-raised absolute right-0 z-50 mt-1 w-60 border shadow-sm"
        >
          <div className="border-rule border-b px-3 py-2.5">
            <div className="text-ink truncate text-sm font-medium">{name}</div>
            <div className="marginal mt-0.5 truncate">{email}</div>
          </div>
          <button
            type="button"
            role="menuitem"
            onClick={signOut}
            disabled={signingOut}
            className="text-ink hover:bg-paper-sunk w-full px-3 py-2.5 text-left text-sm transition-colors disabled:opacity-60"
          >
            {t("nav.signOut")}
          </button>
        </div>
      )}
    </div>
  );
}
