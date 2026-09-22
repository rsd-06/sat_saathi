import { defineRouting } from "next-intl/routing";

export const locales = ["en", "hi", "ta", "bn"] as const;

export type Locale = (typeof locales)[number];

/** Each language names itself in its own script — never in English. */
export const localeNames: Record<Locale, string> = {
  en: "English",
  hi: "हिन्दी",
  ta: "தமிழ்",
  bn: "বাংলা",
};

export const routing = defineRouting({
  locales,
  defaultLocale: "en",
  localePrefix: "always",
});
