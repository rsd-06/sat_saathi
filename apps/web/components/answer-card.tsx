"use client";

import { useFormatter, useTranslations } from "next-intl";

import { Scene } from "./scene";

const CONFIDENCE = 0.86;
const THRESHOLD = 0.75;

export function AnswerCard() {
  const t = useTranslations();
  const format = useFormatter();
  const held = CONFIDENCE < THRESHOLD;

  const band =
    CONFIDENCE >= 0.85 ? "high" : CONFIDENCE >= THRESHOLD ? "medium" : "low";

  if (held) {
    return (
      <section className="border-relief bg-relief-wash/50 border-l-2 px-4 py-4">
        <h2 className="text-ink font-medium">{t("answer.review.title")}</h2>
        <p className="text-ink-muted mt-2 text-sm leading-relaxed">
          {t("answer.review.body", { threshold: THRESHOLD * 100 })}
        </p>
      </section>
    );
  }

  return (
    <section className="border-rule-strong bg-paper-raised border">
      <div className="border-rule flex items-center justify-between border-b px-3 py-2">
        <h2 className="font-serif text-ink text-lg tracking-tight">
          {t("answer.title")}
        </h2>
        <span className="marginal flex items-center gap-1.5">
          {t("answer.confidence.label")}
          <span className="text-vegetation tabular font-medium">
            {format.number(CONFIDENCE, { style: "percent" })}
          </span>
        </span>
      </div>

      <div className="px-3 py-3">
        <p className="text-ink text-sm leading-relaxed">
          About 142 hectares of the scene are under water — roughly 32% of the
          paddy parcels in the eastern block. The flooded ground follows the
          river channel and is widest where it meets the embankment.
        </p>

        {/* Numbers sit on a ruled line with their provenance beneath. */}
        <dl className="divide-rule border-rule mt-4 grid divide-y border-y sm:grid-cols-3 sm:divide-x sm:divide-y-0">
          {[
            { v: "142.4 ha", l: t("dashboard.stats.area"), src: "NDWI > 0.3" },
            { v: "31.7%", l: "Paddy affected", src: "NDVI Δ" },
            { v: "10 m", l: t("workspace.checks.resolution"), src: "Sentinel-2" },
          ].map((s) => (
            <div key={s.l} className="py-3 sm:px-3 sm:first:pl-0">
              <dd className="font-serif text-ink tabular text-xl">{s.v}</dd>
              <dt className="marginal mt-0.5">{s.l}</dt>
              <dd className="marginal text-ink-faint">
                {t("answer.measuredFrom", { source: s.src })}
              </dd>
            </div>
          ))}
        </dl>

        <p className="marginal mt-3">{t(`answer.confidence.${band}`)}</p>

        <div className="mt-3 grid grid-cols-2 gap-2">
          {(["ndwi", "change"] as const).map((v) => (
            <figure key={v} className="border-rule border">
              <div className="aspect-[16/10]">
                <Scene variant={v} />
              </div>
              <figcaption className="marginal border-rule border-t px-2 py-1">
                {v === "ndwi"
                  ? t("workspace.map.layer.ndwi")
                  : t("workspace.map.layer.changeMask")}
              </figcaption>
            </figure>
          ))}
        </div>
      </div>

      <div className="border-rule divide-rule flex divide-x border-t">
        {[
          t("answer.download.pdf"),
          t("answer.download.geojson"),
          t("answer.download.trace"),
        ].map((label) => (
          <button
            key={label}
            type="button"
            className="text-accent hover:bg-paper-sunk marginal flex-1 px-2 py-2 transition-colors"
          >
            {label}
          </button>
        ))}
      </div>
    </section>
  );
}
