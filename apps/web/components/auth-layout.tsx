import type { ReactNode } from "react";
import { getTranslations } from "next-intl/server";

import { Scene } from "./scene";
import { SiteHeader } from "./site-header";

/**
 * Sign-in as a sheet's title block.
 *
 * A real toposheet carries its identity in the margin — sheet number, datum,
 * projection, the survey that produced it — and the map is only the middle of
 * it. The form sits in that margin, so signing in happens on the instrument
 * rather than in front of a picture of one.
 */
export async function AuthLayout({
  title,
  subtitle,
  children,
  footer,
  sheet = "sar",
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
  sheet?: "sar" | "flood";
}) {
  const t = await getTranslations();

  const specimen =
    sheet === "sar"
      ? { platform: "Sentinel-1 GRD", bands: "VV", pass: "Descending" }
      : { platform: "Sentinel-2 L2A", bands: "B03 · B08", pass: "Descending" };

  return (
    <>
      <SiteHeader />
      <main className="relative">
        <div aria-hidden className="sheet-grid pointer-events-none absolute inset-0" />

        <div className="relative mx-auto max-w-[62rem] px-4 py-10 sm:px-6 lg:py-14">
          <div className="sheet-marks border-rule-strong bg-paper-raised relative border">
            {/* Title block, along the top edge, as a sheet carries it. */}
            <div className="border-rule divide-rule open-frame grid grid-cols-2 divide-x border-b sm:grid-cols-4">
              {[
                ["Sheet", "78 B/11"],
                ["Platform", specimen.platform],
                ["Bands", specimen.bands],
                ["Datum", "WGS 84"],
              ].map(([label, value]) => (
                <div key={label} className="px-3 py-2">
                  <div className="text-ink-faint marginal">{label}</div>
                  <div className="text-ink tabular mt-0.5 text-sm">{value}</div>
                </div>
              ))}
            </div>

            <div className="grid lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
              {/* The survey, at its own proportions, with the margin below it.
                  Stretching it to the height of the form would crop it to
                  abstract colour blocks. Hidden on small screens, where the
                  form is the entire job. */}
              <div className="border-rule open-wash hidden flex-col border-r lg:flex">
                <div className="border-rule relative aspect-[4/3] border-b">
                  <Scene variant={sheet} />
                </div>

                <dl className="divide-rule flex-1 divide-y">
                  {[
                    ["Centre", "23.4102°N 88.5107°E"],
                    ["Projection", "UTM 45N"],
                    ["Pass", specimen.pass],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      className="flex items-baseline justify-between gap-3 px-3 py-2"
                    >
                      <dt className="marginal">{label}</dt>
                      <dd className="text-ink tabular text-xs">{value}</dd>
                    </div>
                  ))}
                </dl>

                <div className="border-rule border-t px-3 py-2.5">
                  <div className="marginal">{t("landing.hero.figureCaption")}</div>
                  <div className="mt-2 flex items-center gap-2">
                    <span
                      aria-hidden
                      className="h-1.5 flex-1"
                      style={{
                        background:
                          "linear-gradient(to right, var(--color-relief), var(--color-water))",
                      }}
                    />
                    <span className="marginal tabular shrink-0">−1 … +1</span>
                  </div>
                </div>
              </div>

              <div className="open-line p-6 sm:p-8">
                <h1 className="font-serif text-ink text-3xl leading-tight tracking-tight">
                  {title}
                </h1>
                <p className="text-ink-muted mt-2 text-sm leading-relaxed">{subtitle}</p>

                {children}

                <div className="border-rule text-ink-muted mt-8 border-t pt-4 text-sm">
                  {footer}
                </div>
              </div>
            </div>

            {/* Bottom margin: who made the sheet, where a sheet says so. */}
            <div className="border-rule marginal border-t px-3 py-2">
              {t("app.name")} · Team MidDevz · SIH 2026
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
