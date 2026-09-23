"use client";

import { useTranslations } from "next-intl";

import { Scene } from "./scene";
import { Parallax } from "./motion/parallax";

/**
 * The opening sheet, drawn rather than shown.
 *
 * Order matters and is the whole idea: the frame is ruled first, the survey
 * washes in second, and the measurement is annotated on top last — which is
 * the order a sheet is actually made. It runs once, on load, and nothing else
 * on the page animates without being asked to.
 *
 * The layers drift at different rates on scroll because a map is layers;
 * depth here is the subject rather than an effect applied to it.
 */
export function HeroSheet() {
  const t = useTranslations();

  return (
    <div className="sheet-marks border-rule-strong bg-paper-raised relative border">
      {/* Top margin: what the sheet is of. */}
      <div className="border-rule divide-rule open-frame grid grid-cols-2 divide-x border-b sm:grid-cols-4">
        {[
          ["Centre", "23.4102°N 88.5107°E"],
          ["Platform", "Sentinel-2 L2A"],
          ["Bands", "B03 · B08"],
          ["Acquired", "2026-09-12"],
        ].map(([label, value]) => (
          <div key={label} className="px-3 py-2">
            <div className="text-ink-faint marginal">{label}</div>
            <div className="text-ink tabular mt-0.5 text-xs sm:text-sm">{value}</div>
          </div>
        ))}
      </div>

      <div className="relative overflow-hidden">
        <div className="open-wash aspect-[16/10]">
          <Parallax speed={0.05} className="h-full">
            <Scene variant="flood" />
          </Parallax>
        </div>

        {/* The measurement is annotated where it was taken, with a leader line
            down to the point, the way a surveyor marks a sheet. The point sits
            on the water, because water is what NDWI measured. */}
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute left-[24%] top-[26%]">
            <span
              aria-hidden
              className="open-leader bg-ink/60 absolute left-1/2 top-0 block h-24 w-px"
            />
            <span
              aria-hidden
              className="open-annotate border-ink/70 absolute left-1/2 top-0 block size-2 -translate-x-1/2 -translate-y-1/2 rotate-45 border"
            />
          </div>

          <div className="open-annotate border-rule-strong bg-paper-raised/95 absolute left-[15%] top-[calc(26%+6rem)] border px-3 py-2">
            <div className="text-ink tabular font-serif text-2xl leading-none">
              142.4 ha
            </div>
            <div className="marginal mt-1">
              {t("answer.measuredFrom", { source: "NDWI > 0.3" })}
            </div>
          </div>
        </div>
      </div>

      {/* Bottom margin: scale and legend, where a sheet keeps them. */}
      <div className="border-rule marginal flex flex-wrap items-center justify-between gap-3 border-t px-3 py-2">
        <span>{t("landing.hero.figureCaption")}</span>
        <span className="flex items-center gap-2">
          NDWI
          <span
            aria-hidden
            className="h-1.5 w-24"
            style={{
              background:
                "linear-gradient(to right, var(--color-relief), var(--color-water))",
            }}
          />
          <span className="tabular">−1 … +1</span>
        </span>
      </div>
    </div>
  );
}
