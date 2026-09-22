"use client";

import { useFormatter, useTranslations } from "next-intl";

import type { ComposedAnswer } from "@/lib/compose";

const THRESHOLD = 0.75;

export function LiveAnswer({
  answer,
  onAskAgain,
}: {
  answer: ComposedAnswer;
  onAskAgain: () => void;
}) {
  const t = useTranslations();
  const format = useFormatter();

  const held = answer.confidence < THRESHOLD;
  const band =
    answer.confidence >= 0.85
      ? "high"
      : answer.confidence >= THRESHOLD
        ? "medium"
        : "low";

  return (
    <section className="border-rule-strong bg-paper-raised border">
      <div className="border-rule flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
        <h2 className="font-serif text-ink text-lg tracking-tight">
          {t("answer.title")}
        </h2>
        <span className="marginal flex items-center gap-1.5">
          {t("answer.confidence.label")}
          <span
            className={`tabular font-medium ${
              held ? "text-relief" : "text-vegetation"
            }`}
          >
            {format.number(answer.confidence, { style: "percent" })}
          </span>
        </span>
      </div>

      {/* Below threshold the answer is withheld, exactly as the pipeline says. */}
      {held ? (
        <div className="border-relief bg-relief-wash/40 m-3 border-l-2 px-3 py-2.5">
          <p className="text-ink text-sm font-medium">
            {t("answer.review.title")}
          </p>
          <p className="text-ink-muted mt-1.5 text-sm leading-relaxed">
            {t("answer.review.body", { threshold: THRESHOLD * 100 })}
          </p>
        </div>
      ) : null}

      <div className="px-3 py-3">
        <p className="marginal">
          {t("answer.intent")} · {answer.intent.replace(/_/g, " ")}
        </p>
        <p className="text-ink mt-2 text-sm leading-relaxed">{answer.text}</p>

        <dl className="divide-rule border-rule mt-4 grid divide-y border-y sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          {answer.stats.map((s) => (
            <div key={s.label} className="py-3 sm:px-3 sm:first:pl-0">
              <dd className="font-serif text-ink tabular text-xl">{s.value}</dd>
              <dt className="marginal mt-0.5">{s.label}</dt>
              <dd className="marginal text-ink-faint">
                {t("answer.measuredFrom", { source: s.source })}
              </dd>
            </div>
          ))}
        </dl>

        <p className="marginal mt-3">{t(`answer.confidence.${band}`)}</p>

        {answer.limitation && (
          <div className="border-rule mt-4 border-t pt-3">
            <p className="text-ink text-xs font-medium">
              {t("run.limits.title")}
            </p>
            <p className="marginal mt-1">{answer.limitation}</p>
          </div>
        )}
      </div>

      <div className="border-rule divide-rule flex divide-x border-t">
        <button
          type="button"
          onClick={onAskAgain}
          className="text-accent hover:bg-paper-sunk marginal flex-1 px-2 py-2 transition-colors"
        >
          {t("run.again")}
        </button>
        <button
          type="button"
          className="text-ink-faint marginal flex-1 cursor-not-allowed px-2 py-2"
          aria-disabled="true"
          title={t("run.demo.notice")}
        >
          {t("answer.download.pdf")}
        </button>
      </div>
    </section>
  );
}
