import { getLocale, getTranslations } from "next-intl/server";

import { Link } from "@/i18n/navigation";
import { currentUser } from "@/lib/session";
import { AccountMenu } from "./account-menu";
import { ConnectivityBadge } from "./connectivity-badge";
import { LanguageSwitcher } from "./language-switcher";

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
        <Link
          href={user ? "/dashboard" : "/"}
          className="font-serif text-ink shrink-0 text-lg tracking-tight"
        >
          {t("app.name")}
        </Link>

        {user && (
          <nav className="hidden items-center gap-5 text-sm md:flex">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="text-ink-muted hover:text-ink transition-colors"
              >
                {t(item.key)}
              </Link>
            ))}
          </nav>
        )}

        <div className="ml-auto flex items-center gap-4 sm:gap-5">
          <ConnectivityBadge />
          <LanguageSwitcher />
          {user ? (
            <AccountMenu name={user.full_name} email={user.email} locale={locale} />
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
    </header>
  );
}
