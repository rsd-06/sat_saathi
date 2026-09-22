"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";

import type { JobMode } from "@/lib/mock";

const MODES: JobMode[] = ["single", "fusion", "change"];

const SLOTS: Record<JobMode, string[]> = {
  single: ["single"],
  fusion: ["optical", "sar"],
  change: ["before", "after"],
};

const CHECKS = [
  { key: "crs", status: "pass" as const, value: "EPSG:32645" },
  { key: "overlap", status: "pass" as const, value: "97%" },
  { key: "resolution", status: "warn" as const, value: "10 m / 20 m" },
  { key: "dates", status: "pass" as const, value: "09-04 → 09-12" },
];

const TONE = {
  pass: "text-vegetation",
  warn: "text-relief",
  fail: "text-alert",
};

const MARK = { pass: "✓", warn: "!", fail: "✕" };

export function WorkspaceInputs({
  mode,
  onModeChange,
}: {
  mode: JobMode;
  onModeChange: (m: JobMode) => void;
}) {
  const t = useTranslations();
  const [loaded] = useState(true);

  return (
    <div className="space-y-7">
      <section>
        <h2 className="font-serif text-ink text-lg tracking-tight">
          {t("workspace.inputs.title")}
        </h2>

        <fieldset className="mt-3">
          <legend className="marginal mb-1.5">
            {t("workspace.inputs.mode")}
          </legend>
          <div className="border-rule-strong flex border">
            {MODES.map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => onModeChange(m)}
                aria-pressed={m === mode}
                className={`border-rule flex-1 border-r px-2 py-2 text-xs transition-colors last:border-r-0 ${
                  m === mode
                    ? "bg-accent text-white"
                    : "text-ink-muted hover:bg-paper-sunk"
                }`}
              >
                {t(`job.mode.${m}`)}
              </button>
            ))}
          </div>
        </fieldset>

        <div className="mt-4 space-y-3">
          {SLOTS[mode].map((slot) => (
            <div key={slot} className="border-rule-strong border">
              <div className="border-rule marginal flex items-center justify-between border-b px-2.5 py-1.5">
                <span className="text-ink">
                  {t(`workspace.inputs.slot.${slot}`)}
                </span>
                {loaded && (
                  <span className="text-ink-faint">
                    {slot === "sar" ? "S1A_GRD_20260912.tif" : "S2A_20260912.tif"}
                  </span>
                )}
              </div>
              {loaded ? (
                <dl className="divide-rule divide-y">
                  {[
                    ["CRS", "EPSG:32645"],
                    [t("workspace.checks.resolution"), "10 m"],
                    [t("workspace.checks.sensor"), slot === "sar" ? "Sentinel-1 GRD" : "Sentinel-2 L2A"],
                  ].map(([k, v]) => (
                    <div
                      key={k}
                      className="marginal flex items-center justify-between px-2.5 py-1.5"
                    >
                      <dt>{k}</dt>
                      <dd className="text-ink tabular">{v}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <div className="px-2.5 py-6 text-center">
                  <p className="marginal">
                    {t("workspace.inputs.drop")}{" "}
                    <span className="text-accent underline underline-offset-2">
                      {t("workspace.inputs.browse")}
                    </span>
                  </p>
                  <p className="marginal mt-1">
                    {t("workspace.inputs.accepts")}
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      <section>
        <h3 className="text-ink text-sm font-medium">
          {t("workspace.checks.title")}
        </h3>
        <dl className="border-rule divide-rule mt-2 divide-y border-t">
          {CHECKS.map((c) => (
            <div
              key={c.key}
              className="flex items-center justify-between gap-2 py-2"
            >
              <dt className="marginal flex items-center gap-1.5">
                <span className={TONE[c.status]} aria-hidden>
                  {MARK[c.status]}
                </span>
                {/* The mark is decorative; the outcome still has to be spoken. */}
                <span className="sr-only">
                  {t(`workspace.checks.${c.status}`)}:{" "}
                </span>
                {t(`workspace.checks.${c.key}`)}
              </dt>
              <dd className="marginal text-ink tabular">{c.value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section>
        <h3 className="text-ink text-sm font-medium">
          {t("workspace.analyses.title")}
        </h3>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {[
            { name: "NDVI", available: true },
            { name: "NDWI", available: true },
            { name: "LSWI", available: false },
          ].map((a) => (
            <span
              key={a.name}
              title={
                a.available ? undefined : t("workspace.analyses.lswiUnavailable")
              }
              className={`border px-2 py-1 text-xs ${
                a.available
                  ? "border-vegetation text-vegetation bg-vegetation-wash/50"
                  : "border-rule text-ink-faint line-through"
              }`}
            >
              {a.name}
            </span>
          ))}
        </div>
        <p className="marginal mt-2">
          {t("workspace.analyses.lswiUnavailable")}
        </p>
      </section>
    </div>
  );
}
