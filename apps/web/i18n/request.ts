import { getRequestConfig } from "next-intl/server";
import { hasLocale } from "next-intl";

import { routing } from "./routing";
import { unflatten } from "./unflatten";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested)
    ? requested
    : routing.defaultLocale;

  const flat = (await import(`@satsaathi/i18n/messages/${locale}.json`))
    .default as Record<string, string>;

  return { locale, messages: unflatten(flat) };
});
