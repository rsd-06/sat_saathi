import { getTranslations } from "next-intl/server";

import { Link } from "@/i18n/navigation";
import { LanguageSwitcher } from "./language-switcher";
import { ConnectivityBadge } from "./connectivity-badge";

type Props = {
  /** Signed-in chrome shows the working nav; the public pages do not. */
  signedIn?: boolean;
};

export async function SiteHeader({ signedIn = false }: Props) {
  const t = await getTranslations();

  return (
    <header className="border-rule bg-paper/85 sticky top-0 z-40 border-b backdrop-blur-sm">
      <div className="mx-auto flex h-14 max-w-[88rem] items-center gap-6 px-4 sm:px-6">
        <Link
          href={signedIn ? "/dashboard" : "/"}
          className="font-serif text-ink shrink-0 text-lg tracking-tight"
        >
          {t("app.name")}
        </Link>

        {signedIn && (
          <nav className="hidden items-center gap-5 text-sm md:flex">
            <Link
              href="/dashboard"
              className="text-ink-muted hover:text-ink transition-colors"
            >
              {t("nav.dashboard")}
            </Link>
            <Link
              href="/workspace"
              className="text-ink-muted hover:text-ink transition-colors"
            >
              {t("workspace.title")}
            </Link>
          </nav>
        )}

        <div className="ml-auto flex items-center gap-4 sm:gap-5">
          <ConnectivityBadge />
          <LanguageSwitcher />
          {!signedIn && (
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
