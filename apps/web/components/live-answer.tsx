"use client";

import { useFormatter, useTranslations } from "next-intl";

import { geojsonUrl, traceUrl, type JobOut } from "@/lib/api";

const THRESHOLD = 0.75;

/** Figures the pipeline actually measured, pulled from the compute step. */
function measurements(job: JobOut) {
  const compute = job.steps.find((s) => s.step_key === "compute");
  const summary = (compute?.output_summary ?? {}) as Record<string, unknown>;
  const stats: { value: string; label: string; source: string }[] = [];

  const pct = summary.above_threshold_pct;
  if (typeof pct === "number") {
    stats.push({
      value: `${pct.toFixed(1)}%`,
      label: "aboveThreshold",
      source: `${String(summary.index ?? "index").toUpperCase()} > ${summary.threshold ?? 0}`,
    });
  }
  const area = summary.area_ha;
  if (typeof area === "number") {
    stats.push({
      value: `${area} ha`,
      label: "area",
      source: String(summary.index ?? "index").toUpperCase(),
    });
  }
  const mean = summary.mean;
  if (typeof mean === "number") {
    stats.push({
      value: mean.toFixed(4),
      label: "mean",
      source: `${summary.valid_pixels ?? 0} px`,
    });
  }
  return { stats, summary };
}

export function LiveAnswer({
  job,
  onAskAgain,
}: {
  job: JobOut;
  onAskAgain: () => void;
}) {
  const t = useTranslations();
  const format = useFormatter();

  const held = job.status === "needs_review";
  const confidence = job.confidence ?? 0;
  // A model answer carries its own band (thresholds 0.6 / 0.35 in settings);
  // the fixed cut-offs remain for fixture runs, which have none.
  const vlmBand = job.steps.find((s) => s.step_key === "vision_language")
    ?.output_summary?.confidence_band;
  const band =
    vlmBand === "high" || vlmBand === "medium" || vlmBand === "low"
      ? vlmBand
      : confidence >= 0.85
        ? "high"
        : confidence >= THRESHOLD
          ? "medium"
          : "low";
  const { stats, summary } = measurements(job);
  const text = (job.answer as { text?: string } | null)?.text;
  const vlm = job.steps.find((s) => s.step_key === "vision_language");
  const fixture = Boolean(
    vlm && (vlm.is_stub || vlm.output_summary?.source === "fixture"),
  );

  return (
    <section className="border-rule-strong bg-paper-raised border">
      <div className="border-rule flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
        <h2 className="font-serif text-ink text-lg tracking-tight">
          {t("answer.title")}
        </h2>
        <span className="marginal flex items-center gap-1.5">
          {t("answer.confidence.label")}
          <span
            className={`tabular font-medium ${held ? "text-relief" : "text-vegetation"}`}
          >
            {format.number(confidence, { style: "percent" })}
          </span>
        </span>
      </div>

      {/* A fixture answer is not about this image; never let it pass as one. */}
      {fixture && (
        <div className="border-relief bg-relief-wash/60 m-3 border-2 px-3 py-2.5">
          <p className="text-ink text-sm font-medium">
            {t("answer.fixture.title")}
          </p>
          <p className="text-ink-muted mt-1.5 text-sm leading-relaxed">
            {t("answer.fixture.body")}
          </p>
        </div>
      )}

      {held && (
        <div className="border-relief bg-relief-wash/40 m-3 border-l-2 px-3 py-2.5">
          <p className="text-ink text-sm font-medium">
            {t("answer.review.title")}
          </p>
          <p className="text-ink-muted mt-1.5 text-sm leading-relaxed">
            {t("answer.review.body", { threshold: THRESHOLD * 100 })}
          </p>
        </div>
      )}

      <div className="px-3 py-3">
        {job.intent && (
          <p className="marginal">
            {t("answer.intent")} · {job.intent.replace(/_/g, " ")}
          </p>
        )}
        {text && (
          <p className="text-ink mt-2 text-sm leading-relaxed">{text}</p>
        )}

        {stats.length > 0 && (
          <dl className="divide-rule border-rule mt-4 grid divide-y border-y sm:grid-cols-3 sm:divide-x sm:divide-y-0">
            {stats.map((s) => (
              <div key={s.label} className="py-3 sm:px-3 sm:first:pl-0">
                <dd className="font-serif text-ink tabular text-xl">
                  {s.value}
                </dd>
                <dt className="marginal mt-0.5">
                  {t(`answer.stat.${s.label}`)}
                </dt>
                <dd className="marginal text-ink-faint">
                  {t("answer.measuredFrom", { source: s.source })}
                </dd>
              </div>
            ))}
          </dl>
        )}

        {summary.area_ha === null && (
          <p className="marginal mt-3 text-relief">
            {t("answer.noAreaWithoutCrs")}
          </p>
        )}

        <p className="marginal mt-3">{t(`answer.confidence.${band}`)}</p>
      </div>

      <div className="border-rule divide-rule flex divide-x border-t">
        <a
          href={traceUrl(job.id)}
          download
          className="text-accent hover:bg-paper-sunk marginal flex-1 px-2 py-2 text-center transition-colors"
        >
          {t("answer.download.trace")}
        </a>
        <a
          href={geojsonUrl(job.id)}
          download
          className="text-accent hover:bg-paper-sunk marginal flex-1 px-2 py-2 text-center transition-colors"
        >
          {t("answer.download.geojson")}
        </a>
        <button
          type="button"
          onClick={onAskAgain}
          className="text-accent hover:bg-paper-sunk marginal flex-1 px-2 py-2 transition-colors"
        >
          {t("run.again")}
        </button>
      </div>
    </section>
  );
}
