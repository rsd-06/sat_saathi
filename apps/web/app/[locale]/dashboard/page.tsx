import { getFormatter, getTranslations, setRequestLocale } from "next-intl/server";

import { Link } from "@/i18n/navigation";
import { SiteHeader } from "@/components/site-header";
import { StatusDot } from "@/components/status-dot";
import { RECENT_JOBS } from "@/lib/mock";

export default async function DashboardPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations();
  const format = await getFormatter();

  const heldForReview = RECENT_JOBS.filter(
    (j) => j.status === "needs_review",
  ).length;
  const totalArea = RECENT_JOBS.reduce((sum, j) => sum + (j.areaHa ?? 0), 0);

  const stats = [
    { label: t("dashboard.stats.analyses"), value: format.number(RECENT_JOBS.length) },
    {
      label: t("dashboard.stats.area"),
      value: `${format.number(totalArea, { maximumFractionDigits: 1 })} ha`,
    },
    { label: t("dashboard.stats.review"), value: format.number(heldForReview) },
  ];

  return (
    <>
      <SiteHeader signedIn />

      <main className="mx-auto max-w-[88rem] px-4 py-10 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-serif text-ink text-3xl tracking-tight">
              {t("dashboard.greeting")}
            </h1>
            <p className="text-ink-muted mt-2 text-sm">
              {t("dashboard.subtitle")}
            </p>
          </div>
          <Link
            href="/workspace"
            className="bg-accent hover:bg-accent-hover rounded-xs px-5 py-2.5 text-sm font-medium text-white transition-colors"
          >
            {t("dashboard.newAnalysis")}
          </Link>
        </div>

        {/* Measurements read against each other, so they sit on one ruled line. */}
        <dl className="border-rule divide-rule mt-8 grid divide-y border-y sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          {stats.map((s) => (
            <div key={s.label} className="py-4 sm:px-5 sm:first:pl-0">
              <dt className="marginal">{s.label}</dt>
              <dd className="font-serif text-ink tabular mt-1 text-2xl">
                {s.value}
              </dd>
            </div>
          ))}
        </dl>

        {heldForReview > 0 && (
          <div className="border-relief bg-relief-wash/50 mt-8 flex flex-wrap items-center gap-x-4 gap-y-2 border-l-2 px-4 py-3">
            <span className="text-ink text-sm font-medium">
              {t("dashboard.review.title")}
            </span>
            <span className="text-ink-muted text-sm">
              {t("dashboard.review.body", { count: heldForReview })}
            </span>
            <span className="text-ink-faint ml-auto text-sm">
              {t("dashboard.review.cta")}
            </span>
          </div>
        )}

        <section className="mt-10">
          <div className="flex items-baseline justify-between">
            <h2 className="font-serif text-ink text-xl tracking-tight">
              {t("dashboard.recent.title")}
            </h2>
            <span className="text-ink-faint text-sm">
              {t("dashboard.recent.viewAll")}
            </span>
          </div>

          <ul className="border-rule divide-rule mt-4 divide-y border-t">
            {RECENT_JOBS.map((job) => (
              <li key={job.id}>
                <Link
                  href="/workspace"
                  className="hover:bg-paper-sunk/60 group flex flex-wrap items-baseline gap-x-4 gap-y-1 px-1 py-4 transition-colors"
                >
                  <StatusDot
                    status={job.status}
                    className="translate-y-[-2px]"
                  />
                  <span className="text-ink group-hover:text-accent min-w-0 flex-1 text-sm transition-colors">
                    {job.question}
                  </span>
                  <span className="marginal shrink-0">
                    {t(`job.mode.${job.mode}`)}
                  </span>
                  <span className="marginal w-16 shrink-0 text-right">
                    {job.areaHa
                      ? `${format.number(job.areaHa, { maximumFractionDigits: 1 })} ha`
                      : "—"}
                  </span>
                  <span className="marginal w-12 shrink-0 text-right">
                    {job.confidence
                      ? format.number(job.confidence, { style: "percent" })
                      : "—"}
                  </span>
                  {/* Status is free text and expands hard in ta/bn — it sizes
                      to content. Only the numeric columns are width-locked. */}
                  <span className="marginal shrink-0">
                    {t(`job.status.${job.status}`)}
                  </span>
                  <span className="marginal tabular w-24 shrink-0 text-right">
                    {job.date}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </>
  );
}
