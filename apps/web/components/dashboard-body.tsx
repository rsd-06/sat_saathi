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

  useEffect(() => {
    listJobs(50).then(setPage).catch(() => undefined);
    listReview().then(setReview).catch(() => undefined);
  }, []);

  const stats = [
    { label: t("dashboard.stats.analyses"), value: format.number(page?.total ?? 0) },
    { label: t("dashboard.stats.review"), value: format.number(review.length) },
  ];

  return (
    <>
      <dl className="border-rule divide-rule mt-8 grid divide-y border-y sm:grid-cols-2 sm:divide-x sm:divide-y-0">
        {stats.map((s) => (
          <div key={s.label} className="py-4 sm:px-5 sm:first:pl-0">
            <dt className="marginal">{s.label}</dt>
            <dd className="font-serif text-ink tabular mt-1 text-2xl">
              {s.value}
            </dd>
          </div>
        ))}
      </dl>

      {review.length > 0 && (
        <div className="border-relief bg-relief-wash/50 mt-8 flex flex-wrap items-center gap-x-4 gap-y-2 border-l-2 px-4 py-3">
          <span className="text-ink text-sm font-medium">
            {t("dashboard.review.title")}
          </span>
          <span className="text-ink-muted text-sm">
            {t("dashboard.review.body", { count: review.length })}
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
        <div className="flex items-baseline justify-between">
          <h2 className="font-serif text-ink text-xl tracking-tight">
            {t("dashboard.recent.title")}
          </h2>
          <Link
            href="/history"
            className="text-accent hover:text-accent-hover text-sm underline underline-offset-4"
          >
            {t("dashboard.recent.viewAll")}
          </Link>
        </div>
        <div className="mt-4">
          <HistoryList />
        </div>
      </section>
    </>
  );
}
