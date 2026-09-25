import { getTranslations, setRequestLocale } from "next-intl/server";

import { HeroSheet } from "@/components/hero-sheet";
import { Register } from "@/components/motion/register";
import { Scene } from "@/components/scene";
import { Sheet } from "@/components/sheet";
import { SiteHeader } from "@/components/site-header";
import { Link } from "@/i18n/navigation";
import { currentUser } from "@/lib/session";

export default async function LandingPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();
  // Someone already signed in is not a prospect. Send them to the work
  // rather than inviting them to start an account they have.
  const user = await currentUser();

  const steps = ["ask", "compute", "explain", "act"] as const;
  const inputs = ["single", "fusion", "change"] as const;

  return (
    <>
      <SiteHeader />

      <main>
        {/* Hero: the sheet is the hero. The copy sits beside it, not over it. */}
        <section className="relative bg-gradient-to-b from-blue-50/40 via-transparent to-transparent">
          <div aria-hidden className="sheet-grid pointer-events-none absolute inset-0" />
          <div className="relative mx-auto grid max-w-[88rem] gap-10 px-4 py-14 sm:px-6 lg:grid-cols-[minmax(0,25rem)_minmax(0,1fr)] lg:gap-14 lg:py-20">
            <div className="open-line max-w-prose self-center">
              <h1 className="font-serif text-ink text-5xl leading-[1.15] tracking-tight text-balance sm:text-6xl drop-shadow-sm">
                {t("landing.hero.headline")}
              </h1>
              <p className="text-ink-muted mt-6 text-lg leading-relaxed">
                {t("landing.hero.body")}
              </p>
              <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-3">
                <Link
                  href={user ? "/workspace" : "/sign-up"}
                  className="bg-accent hover:bg-accent-hover rounded-full shadow-md hover:shadow-lg hover:-translate-y-0.5 px-6 py-3 text-base font-medium text-white transition-all"
                >
                  {user ? t("landing.hero.ctaSignedIn") : t("landing.hero.cta")}
                </Link>
                {user ? (
                  <Link
                    href="/history"
                    className="text-ink-muted hover:text-ink text-sm underline decoration-current/30 underline-offset-4 transition-colors"
                  >
                    {t("landing.hero.secondarySignedIn")}
                  </Link>
                ) : (
                  <a
                    href="#how"
                    className="text-ink-muted hover:text-ink text-sm underline decoration-current/30 underline-offset-4 transition-colors"
                  >
                    {t("landing.hero.secondary")}
                  </a>
                )}
              </div>
            </div>

            <div className="self-center transform transition duration-500 hover:scale-[1.01] hover:shadow-2xl rounded-2xl overflow-hidden ring-1 ring-black/5">
              <HeroSheet />
            </div>
          </div>
        </section>

        {/* The problem, stated plainly. */}
        <section className="border-rule border-t">
          <div className="mx-auto max-w-[88rem] px-4 py-14 sm:px-6">
            <Register rule={false} className="max-w-2xl">
              <h2 className="font-serif text-ink text-3xl leading-snug tracking-tight text-balance sm:text-4xl">
                {t("landing.problem.title")}
              </h2>
              <p className="text-ink-muted mt-5 text-lg leading-relaxed">
                {t("landing.problem.body")}
              </p>
            </Register>
          </div>
        </section>

        {/* Ask → Compute → Explain → Act. Genuinely a sequence, so it is numbered. */}
        <section id="how" className="border-rule bg-paper-sunk/60 border-t">
          <div className="mx-auto max-w-[88rem] px-4 py-14 sm:px-6">
            <h2 className="font-serif text-ink text-3xl tracking-tight">
              {t("landing.steps.title")}
            </h2>
            <ol className="divide-rule border-rule mt-8 grid divide-y border-t sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-4">
              {steps.map((step, i) => (
                <li
                  key={step}
                  className="border-rule sm:border-r sm:first:pl-0 lg:last:border-r-0"
                >
                  {/* Each step draws in turn, so the sequence reads as one. */}
                  <Register rule={false} delay={i * 110} className="flex gap-4 py-6 sm:px-5">
                    <span className="text-ink-faint tabular marginal shrink-0 pt-0.5 text-lg" aria-hidden>
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <div>
                      <h3 className="text-ink font-semibold text-lg">
                        {t(`landing.steps.${step}.title`)}
                      </h3>
                      <p className="text-ink-muted mt-2 text-base leading-relaxed">
                        {t(`landing.steps.${step}.body`)}
                      </p>
                    </div>
                  </Register>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* Supported inputs, each shown as the sheet it produces. */}
        <section className="border-rule border-t">
          <div className="mx-auto max-w-[88rem] px-4 py-14 sm:px-6">
            <h2 className="font-serif text-ink text-2xl tracking-tight">
              {t("landing.inputs.title")}
            </h2>
            <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {inputs.map((input, i) => (
                <Register key={input} rule={false} delay={i * 110}>
                  <Sheet margin={[<span key="k">{t(`landing.inputs.${input}.title`)}</span>]}>
                    <div className="aspect-[16/9]">
                      <Scene
                        variant={
                          input === "fusion" ? "sar" : input === "change" ? "change" : "flood"
                        }
                        showFlood={input !== "single"}
                      />
                    </div>
                    <p className="text-ink-muted border-rule border-t px-3 py-3 text-sm leading-relaxed">
                      {t(`landing.inputs.${input}.body`)}
                    </p>
                  </Sheet>
                </Register>
              ))}
            </div>
          </div>
        </section>

        {/* Trust: the trace is the product's argument, so it closes the page. */}
        <section className="border-rule bg-paper-sunk/60 border-t">
          <div className="mx-auto grid max-w-[88rem] gap-10 px-4 py-14 sm:px-6 lg:grid-cols-2 lg:items-center">
            <Register rule={false} className="max-w-prose">
              <h2 className="font-serif text-ink text-2xl leading-snug tracking-tight text-balance sm:text-3xl">
                {t("landing.trust.title")}
              </h2>
              <p className="text-ink-muted mt-4 leading-relaxed">
                {t("landing.trust.body")}
              </p>
              <Link
                href={user ? "/workspace" : "/sign-up"}
                className="text-accent hover:text-accent-hover mt-6 inline-block text-sm font-medium underline decoration-current/30 underline-offset-4 transition-colors"
              >
                {t("landing.trust.cta")}
              </Link>
            </Register>

            <div>
            <p className="marginal mb-1.5">Example trace · illustrative timings</p>
            <ol className="border-rule-strong bg-paper-raised divide-rule divide-y border">
              {(
                [
                  ["imagery", "succeeded", "rasterio.inspect", "38"],
                  ["compute", "succeeded", "indices.ndwi", "412"],
                  ["verify", "succeeded", "verify.crosscheck", "26"],
                  ["answer", "running", "answer.compose", null],
                ] as const
              ).map(([step, status, tool, ms], i) => (
                <li key={step}>
                  <Register rule={false} delay={i * 130} className="flex items-baseline gap-3 px-3 py-2.5">
                    <span
                      aria-hidden
                      className={`size-1.5 shrink-0 translate-y-[-2px] rounded-full ${
                        status === "succeeded" ? "bg-vegetation" : "bg-accent"
                      }`}
                    />
                    <span className="text-ink text-sm">{t(`steps.${step}.title`)}</span>
                    <span className="marginal ml-auto shrink-0">{tool}</span>
                    <span className="marginal tabular w-14 shrink-0 text-right">
                      {ms ? `${ms} ms` : "—"}
                    </span>
                  </Register>
                </li>
              ))}
            </ol>
            </div>
          </div>
        </section>
      </main>

      {/* The sheet's colophon: who surveyed it, and under what. */}
      <footer className="border-rule border-t">
        <div className="mx-auto max-w-[88rem] px-4 py-8 sm:px-6">
          <dl className="divide-rule border-rule grid gap-px border-t sm:grid-cols-3">
            {[
              ["Surveyed by", "Team MidDevz"],
              ["Problem statement", "SIH26167"],
              ["Edition", "SIH 2026"],
            ].map(([label, value]) => (
              <div key={label} className="py-3">
                <dt className="marginal">{label}</dt>
                <dd className="text-ink mt-0.5 text-sm">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </footer>
    </>
  );
}
