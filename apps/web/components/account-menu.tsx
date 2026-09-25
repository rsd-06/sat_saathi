"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";

import { Link } from "@/i18n/navigation";
import type { User } from "@/lib/session";

/**
 * Who is signed in, and the way out.
 *
 * Sign-out clears the cookie through this app's own route, then refreshes so
 * every server component re-renders signed-out. Navigating without the
 * refresh would leave a cached tree that still believes it has a user.
 */
export function AccountMenu({ user, locale }: { user: User; locale: string }) {
  const { full_name: name, email } = user;
  const area = [user.district, user.state].filter(Boolean).join(", ");
  const details: [string, string | null][] = [
    ["Post", user.designation],
    ["Department", user.department],
    ["Area", area || null],
  ];
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
        <span className="hidden min-w-0 text-left leading-tight sm:block">
          <span className="block max-w-[11rem] truncate">{name}</span>
          {(user.department || area) && (
            <span className="text-ink-faint block max-w-[11rem] truncate text-[0.6875rem]">
              {user.department ?? area}
            </span>
          )}
        </span>
      </button>

      {open && (
        <div
          role="menu"
          className="border-rule-strong bg-paper-raised absolute right-0 z-50 mt-1 w-72 border shadow-lg"
        >
          <div className="border-rule border-b px-3 py-2.5">
            <div className="text-ink truncate text-sm font-medium">{name}</div>
            <div className="marginal mt-0.5 truncate">{email}</div>
          </div>
          <dl className="border-rule space-y-1.5 border-b px-3 py-2.5">
            {details.map(([label, value]) => (
              <div key={label} className="grid grid-cols-[5.5rem_1fr] gap-2 text-xs">
                <dt className="text-ink-faint">{label}</dt>
                <dd className={value ? "text-ink" : "text-ink-faint italic"}>
                  {value ?? "Not set"}
                </dd>
              </div>
            ))}
          </dl>
          <Link
            href="/settings#profile"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="text-ink hover:bg-paper-sunk border-rule block border-b px-3 py-2.5 text-sm transition-colors"
          >
            Edit profile
          </Link>
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
