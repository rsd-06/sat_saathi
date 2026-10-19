"use client";

import { useLocale, useTranslations } from "next-intl";
import { useParams } from "next/navigation";
import { useTransition } from "react";

import { usePathname, useRouter } from "@/i18n/navigation";
import { localeNames, locales, type Locale } from "@/i18n/routing";

export function LanguageSwitcher() {
  const t = useTranslations();
  const active = useLocale() as Locale;
  const router = useRouter();
  const pathname = usePathname();
  const params = useParams();
  const [isPending, startTransition] = useTransition();

  function select(next: Locale) {
    if (next === active) return;
    startTransition(() => {
      router.replace(
        // @ts-expect-error -- params carry through unchanged for dynamic routes
        { pathname, params },
        { locale: next },
      );
    });
  }

  // Four names in four scripts do not fit a phone header beside the mark and
  // sign-in (Tamil overflowed by ~180px at 375px), so phones get a select.
  return (
    <>
      <select
        aria-label={t("nav.languageChange")}
        value={active}
        onChange={(e) => select(e.target.value as Locale)}
        data-pending={isPending ? "" : undefined}
        className="text-ink bg-paper rounded-xs border-rule border px-1.5 py-1 text-sm sm:hidden"
      >
        {locales.map((locale) => (
          <option key={locale} value={locale} lang={locale}>
            {localeNames[locale]}
          </option>
        ))}
      </select>
      <div
        role="group"
        aria-label={t("nav.languageChange")}
        className="hidden items-center sm:flex"
        data-pending={isPending ? "" : undefined}
      >
        {locales.map((locale, i) => (
          <span key={locale} className="flex items-center">
            {i > 0 && (
              <span aria-hidden className="text-rule-strong px-1 select-none">
                /
              </span>
            )}
            <button
              type="button"
              lang={locale}
              onClick={() => select(locale)}
              aria-current={locale === active ? "true" : undefined}
              className={`rounded-xs px-1 py-0.5 text-sm transition-colors ${
                locale === active
                  ? "text-ink font-medium"
                  : "text-ink-faint hover:text-ink"
              }`}
            >
              {localeNames[locale]}
            </button>
          </span>
        ))}
      </div>
    </>
  );
}
