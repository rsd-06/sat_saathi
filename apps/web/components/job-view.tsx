"use client";

import { useEffect, useState } from "react";
import { useFormatter, useTranslations } from "next-intl";

import { LiveAnswer } from "./live-answer";
import { Trace } from "./trace";
import { getJob, subscribeToJob, type JobOut } from "@/lib/api";

/** A shareable read-only view. Reconnects to the live stream if still running. */
export function JobView({ jobId }: { jobId: string }) {
  const t = useTranslations();
  const format = useFormatter();
  const [job, setJob] = useState<JobOut | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let stop: (() => void) | undefined;

    getJob(jobId)
      .then((initial) => {
        setJob(initial);
        const running =
          initial.status === "queued" || initial.status === "running";
        if (running) {
          stop = subscribeToJob(jobId, { onSnapshot: setJob });
        }
      })
      .catch(() => setFailed(true));

    return () => stop?.();
  }, [jobId]);

  if (failed) {
    return (
      <p className="border-alert bg-alert-wash/60 text-ink marginal border-l-2 px-3 py-2">
        {t("error.apiUnreachable.body")}
      </p>
    );
  }
  if (!job) return <p className="marginal">{t("workspace.inputs.reading")}…</p>;

  const answered = job.status === "succeeded" || job.status === "needs_review";

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-serif text-ink text-2xl leading-snug tracking-tight">
          {job.query_text}
        </h1>
        <p className="marginal mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="uppercase">{job.query_lang}</span>
          <span>{t(`job.status.${job.status}`)}</span>
          {job.confidence !== null && (
            <span className="tabular">
              {format.number(job.confidence, { style: "percent" })}
            </span>
          )}
          <span className="tabular">
            {format.dateTime(new Date(job.created_at), {
              dateStyle: "medium",
              timeStyle: "short",
            })}
          </span>
        </p>
      </header>

      {answered && <LiveAnswer job={job} onAskAgain={() => undefined} />}

      <Trace steps={job.steps} jobId={job.id} />
    </div>
  );
}
