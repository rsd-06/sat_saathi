import type { ReactNode } from "react";
import { getTranslations } from "next-intl/server";

import { Sheet } from "./sheet";
import { Scene } from "./scene";
import { SiteHeader } from "./site-header";

export async function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  const t = await getTranslations();

  return (
    <>
      <SiteHeader />
      <main className="relative">
        <div
          aria-hidden
          className="sheet-grid pointer-events-none absolute inset-0"
        />
        <div className="relative mx-auto grid max-w-[76rem] gap-10 px-4 py-12 sm:px-6 lg:grid-cols-2 lg:gap-16 lg:py-16">
          <div className="mx-auto w-full max-w-sm self-center">
            <h1 className="font-serif text-ink text-3xl tracking-tight">
              {title}
            </h1>
            <p className="text-ink-muted mt-2 text-sm leading-relaxed">
              {subtitle}
            </p>

            <p className="border-relief bg-relief-wash/60 text-ink-muted marginal mt-6 border-l-2 px-3 py-2">
              {t("auth.notice.preview")}
            </p>

            {children}

            <div className="text-ink-muted mt-6 text-sm">{footer}</div>
          </div>

          {/* The sheet keeps the subject present even on a sign-in screen. */}
          <Sheet
            className="hidden self-center lg:block"
            margin={[
              <span key="c" className="tabular">
                23.4102°N 88.5107°E
              </span>,
              <span key="s">Sentinel-1 GRD</span>,
              <span key="p">VV</span>,
            ]}
            footer={
              <span className="marginal">{t("landing.hero.figureCaption")}</span>
            }
          >
            <div className="aspect-[4/3]">
              <Scene variant="sar" />
            </div>
          </Sheet>
        </div>
      </main>
    </>
  );
}
