"use client";

import { useEffect, useState } from "react";
import { useFormatter, useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import { HistoryList } from "./history-list";
import { listJobs, listReview, type JobPage, type ReviewOut } from "@/lib/api";

export function DashboardBody() {
  const t = useTranslations();
  const format = useFormatter();
  const [page, setPage] = useState<JobPage | null>(null);
  const [review, setReview] = useState<ReviewOut[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([listJobs(50), listReview()]).then(([jobs, queue]) => {
      if (jobs.status === "fulfilled") setPage(jobs.value);
      if (queue.status === "fulfilled") setReview(queue.value);
      setLoading(false);
    });
  }, []);

  const total = page?.total ?? 0;
  const held = review.length;
  // Counted rather than assumed: a job that was held is not a measurement,
  // and the dashboard should not flatter the numbers.
  const measured = Math.max(total - held, 0);

  const stats = [
    { label: t("dashboard.stats.analyses"), value: total },
    { label: t("dashboard.stats.measured"), value: measured },
    { label: t("dashboard.stats.held"), value: held },
  ];

  return (
    <>
      <dl className="border-rule divide-rule grid divide-y border-y sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        {stats.map((s) => (
          <div key={s.label} className="py-4 sm:px-5 sm:first:pl-0">
            <dt className="marginal">{s.label}</dt>
            <dd className="font-serif text-ink tabular mt-1 text-3xl leading-none">
              {loading ? (
                <span className="bg-paper-sunk inline-block h-7 w-10 animate-pulse align-middle" />
              ) : (
                format.number(s.value)
              )}
            </dd>
          </div>
        ))}
      </dl>

      {held > 0 && (
        <div className="border-relief bg-relief-wash/50 mt-8 flex flex-wrap items-center gap-x-4 gap-y-2 border-l-2 px-4 py-3">
          <span className="text-ink text-sm font-medium">
            {t("dashboard.review.title")}
          </span>
          <span className="text-ink-muted text-sm">
            {t("dashboard.review.body", { count: held })}
          </span>
          <Link
            href="/review"
            className="text-accent hover:text-accent-hover ml-auto text-sm underline underline-offset-4"
          >
            {t("dashboard.review.cta")}
          </Link>
        </div>
      )}

      <section className="mt-10">
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="font-serif text-ink text-xl tracking-tight">
            {t("dashboard.recent.title")}
          </h2>
          {total > 0 && (
            <Link
              href="/history"
              className="text-accent hover:text-accent-hover text-sm underline underline-offset-4"
            >
              {t("dashboard.recent.viewAll")}
            </Link>
          )}
        </div>

        {!loading && total === 0 ? (
          // An empty screen is an invitation, not a dead end.
          <div className="border-rule-strong bg-paper-raised mt-4 border px-6 py-10 text-center">
            <p className="font-serif text-ink text-lg">
              {t("dashboard.empty.title")}
            </p>
            <p className="text-ink-muted mx-auto mt-2 max-w-sm text-sm leading-relaxed">
              {t("dashboard.empty.body")}
            </p>
            <Link
              href="/workspace"
              className="bg-accent hover:bg-accent-hover mt-5 inline-block rounded-xs px-5 py-2.5 text-sm font-medium text-white transition-colors"
            >
              {t("dashboard.newAnalysis")}
            </Link>
          </div>
        ) : (
          <div className="mt-4">
            <HistoryList />
          </div>
        )}
      </section>
    </>
  );
}
