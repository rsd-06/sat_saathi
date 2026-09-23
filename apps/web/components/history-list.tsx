"use client";

import { useEffect, useState } from "react";
import { useFormatter, useTranslations } from "next-intl";

import { Link } from "@/i18n/navigation";
import { StatusDot } from "./status-dot";
import { listJobs, type JobPage } from "@/lib/api";

export function HistoryList() {
  const t = useTranslations();
  const format = useFormatter();
  const [page, setPage] = useState<JobPage | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    listJobs(50).then(setPage).catch(() => setFailed(true));
  }, []);

  if (failed) {
    return (
      <p className="border-alert bg-alert-wash/60 text-ink marginal border-l-2 px-3 py-2">
        {t("error.apiUnreachable.body")}
      </p>
    );
  }

  if (!page) {
    return <p className="marginal">{t("workspace.inputs.reading")}…</p>;
  }

  if (page.items.length === 0) {
    return <p className="text-ink-muted text-sm">{t("history.empty")}</p>;
  }

  return (
    <ul className="border-rule divide-rule divide-y border-t">
      {page.items.map((job) => (
        <li key={job.id}>
          <Link
            href={`/jobs/${job.id}`}
            className="hover:bg-paper-sunk/60 group flex flex-wrap items-baseline gap-x-4 gap-y-1 px-1 py-4 transition-colors"
          >
            <StatusDot status={job.status} className="translate-y-[-2px]" />
            <span className="text-ink group-hover:text-accent min-w-0 flex-1 text-sm transition-colors">
              {job.query_text}
            </span>
            <span className="marginal shrink-0 uppercase">{job.query_lang}</span>
            <span className="marginal shrink-0">{t(`job.mode.${job.mode}`)}</span>
            <span className="marginal w-12 shrink-0 text-right">
              {job.confidence === null
                ? "—"
                : format.number(job.confidence, { style: "percent" })}
            </span>
            <span className="marginal shrink-0">
              {t(`job.status.${job.status}`)}
            </span>
            <span className="marginal tabular shrink-0">
              {format.dateTime(new Date(job.created_at), {
                year: "numeric",
                month: "short",
                day: "numeric",
              })}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
