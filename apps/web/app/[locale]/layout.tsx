import type { Metadata } from "next";
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import Script from "next/script";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { PageEnter } from "@/components/motion/page-enter";
import { SmoothScroll } from "@/components/motion/smooth-scroll";
import { routing } from "@/i18n/routing";

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale });
  return {
    title: t("app.name"),
    description: t("app.tagline"),
  };
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);

  return (
    <html lang={locale} suppressHydrationWarning>
      <head>
        {/* Arms the scroll reveals before first paint. The stylesheet only
            hides a section once this flag is set, so a page whose JavaScript
            never arrives shows all of its content instead of none of it.
            Reduced motion never arms, so that reader gets the page whole.
            next/script, because a raw <script> re-rendered on a client
            navigation (a language switch) is never run and React warns. */}
        <Script id="arm-motion" strategy="beforeInteractive">
          {"try{if(!matchMedia('(prefers-reduced-motion: reduce)').matches)" +
            "document.documentElement.dataset.motion='on'}catch(e){}"}
        </Script>
      </head>
      <body className="min-h-dvh antialiased">
        <NextIntlClientProvider>
          <SmoothScroll />
          <PageEnter>{children}</PageEnter>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
