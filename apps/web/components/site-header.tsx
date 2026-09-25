import { getLocale, getTranslations } from "next-intl/server";

import { Link } from "@/i18n/navigation";
import { currentUser } from "@/lib/session";
import { AccountMenu } from "./account-menu";
import { ConnectivityBadge } from "./connectivity-badge";
import { LanguageSwitcher } from "./language-switcher";
import { NavLink } from "./nav-link";

const NAV = [
  { href: "/dashboard", key: "nav.dashboard" },
  { href: "/workspace", key: "workspace.title" },
  { href: "/history", key: "nav.history" },
  { href: "/review", key: "nav.review" },
  { href: "/settings", key: "nav.settings" },
] as const;

/**
 * The header asks the API who is signed in rather than being told.
 *
 * A `signedIn` prop would have to be threaded through every page and would go
 * stale the moment a session was revoked elsewhere. One read here is cheap and
 * is always right.
 */
export async function SiteHeader() {
  const t = await getTranslations();
  const locale = await getLocale();
  const user = await currentUser();

  return (
    <header className="border-rule bg-paper/85 sticky top-0 z-40 border-b backdrop-blur-sm">
      <div className="mx-auto flex h-14 max-w-[88rem] items-center gap-6 px-4 sm:px-6">
        {/* The mark goes home, signed in or not. Somewhere to start over from
            is worth more than one saved click to the dashboard, which is the
            next item along anyway. */}
        <Link
          href="/"
          aria-label={t("nav.home")}
          className="font-serif text-ink hover:text-accent shrink-0 text-lg tracking-tight transition-colors"
        >
          {t("app.name")}
        </Link>

        {user && (
          <nav aria-label={t("nav.dashboard")} className="hidden items-center gap-5 text-sm md:flex">
            {NAV.map((item) => (
              <NavLink key={item.href} href={item.href}>
                {t(item.key)}
              </NavLink>
            ))}
          </nav>
        )}

        <div className="ml-auto flex items-center gap-4 sm:gap-5">
          <ConnectivityBadge />
          <LanguageSwitcher />
          {user ? (
            <AccountMenu user={user} locale={locale} />
          ) : (
            <Link
              href="/sign-in"
              className="text-accent hover:text-accent-hover text-sm font-medium transition-colors"
            >
              {t("nav.signIn")}
            </Link>
          )}
        </div>
      </div>

      {/* The nav wraps to its own row on narrow screens rather than vanishing,
          because a phone user still has to reach the review queue. */}
      {user && (
        <nav
          aria-label={t("nav.dashboard")}
          className="border-rule scrollbar-none flex gap-4 overflow-x-auto border-t px-4 py-2 text-sm md:hidden"
        >
          {NAV.map((item) => (
            <NavLink key={item.href} href={item.href} className="whitespace-nowrap">
              {t(item.key)}
            </NavLink>
          ))}
        </nav>
      )}
    </header>
  );
}
