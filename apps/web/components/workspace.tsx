"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";

import { AnswerCard } from "./answer-card";
import { Scene } from "./scene";
import { Trace } from "./trace";
import { WorkspaceInputs } from "./workspace-inputs";
import { DEMO_STEPS, type JobMode } from "@/lib/mock";
import { localeNames, locales, type Locale } from "@/i18n/routing";

const LAYERS = [
  { key: "falseColour", on: true },
  { key: "ndwi", on: true },
  { key: "changeMask", on: false },
  { key: "aoi", on: false },
] as const;

const EXAMPLES: Record<JobMode, string[]> = {
  single: ["single1", "single2"],
  fusion: ["fusion1", "fusion2"],
  change: ["change1", "change2"],
};

export function Workspace() {
  const t = useTranslations();
  const uiLocale = useLocale() as Locale;
  const [mode, setMode] = useState<JobMode>("change");
  const [queryLang, setQueryLang] = useState<Locale>(uiLocale);
  const [question, setQuestion] = useState("");
  const [layers, setLayers] = useState<string[]>(
    LAYERS.filter((l) => l.on).map((l) => l.key),
  );

  function toggleLayer(key: string) {
    setLayers((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  }

  return (
    <div className="mx-auto grid max-w-[110rem] gap-6 px-4 py-6 sm:px-6 xl:grid-cols-[19rem_minmax(0,1fr)_25rem]">
      {/* Left: what you are looking at. */}
      <aside
        data-lenis-prevent
        className="xl:max-h-[calc(100dvh-6rem)] xl:overflow-y-auto xl:pr-1"
      >
        <WorkspaceInputs mode={mode} onModeChange={setMode} />
      </aside>

      {/* Centre: the sheet. The imagery is the largest thing on screen. */}
      <div className="min-w-0">
        <div className="border-rule-strong bg-paper-raised border">
          <div className="border-rule divide-rule flex flex-wrap items-center divide-x border-b">
            <span className="marginal tabular px-2.5 py-1.5">
              23.4102°N 88.5107°E
            </span>
            <span className="marginal px-2.5 py-1.5">EPSG:32645</span>
            <span className="marginal px-2.5 py-1.5">10 m</span>
            <span className="marginal tabular px-2.5 py-1.5">
              2026-09-04 → 2026-09-12
            </span>
            <span className="marginal ml-auto px-2.5 py-1.5">
              {t("workspace.map.compare")}
            </span>
          </div>

          <div className="relative aspect-[16/10] min-h-[20rem]">
            <Scene variant="flood" />
            {/* Before/after comparison handle. */}
            <div
              aria-hidden
              className="absolute inset-y-0 left-1/2 w-px bg-white/70"
            >
              <span className="border-rule-strong bg-paper-raised absolute top-1/2 left-1/2 flex size-7 -translate-x-1/2 -translate-y-1/2 items-center justify-center border text-xs">
                ‹›
              </span>
            </div>
            <div className="border-rule-strong bg-paper-raised/95 absolute bottom-3 left-3 border px-2.5 py-1.5">
              <div className="marginal flex items-center gap-2">
                NDWI
                <span
                  aria-hidden
                  className="h-1.5 w-20"
                  style={{
                    background:
                      "linear-gradient(to right, var(--color-relief), var(--color-water))",
                  }}
                />
                <span className="tabular">
                  {t("workspace.map.legend.low")} … {t("workspace.map.legend.high")}
                </span>
              </div>
            </div>
          </div>

          <div className="border-rule flex flex-wrap items-center gap-x-4 gap-y-2 border-t px-2.5 py-2">
            <span className="marginal text-ink">
              {t("workspace.map.layers")}
            </span>
            {LAYERS.map((l) => {
              const on = layers.includes(l.key);
              return (
                <label
                  key={l.key}
                  className="marginal flex cursor-pointer items-center gap-1.5"
                >
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() => toggleLayer(l.key)}
                    className="accent-accent size-3"
                  />
                  <span className={on ? "text-ink" : "text-ink-faint"}>
                    {t(`workspace.map.layer.${l.key}`)}
                  </span>
                </label>
              );
            })}
          </div>
        </div>
      </div>

      {/* Right: ask, then watch. */}
      <aside
        data-lenis-prevent
        className="space-y-6 xl:max-h-[calc(100dvh-6rem)] xl:overflow-y-auto xl:pl-1"
      >
        <section>
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="font-serif text-ink text-lg tracking-tight">
              {t("workspace.ask.title")}
            </h2>
            <label className="marginal flex items-center gap-1.5">
              {t("workspace.ask.language")}
              <select
                value={queryLang}
                onChange={(e) => setQueryLang(e.target.value as Locale)}
                className="border-rule-strong bg-paper-raised text-ink rounded-xs border px-1.5 py-0.5"
              >
                {locales.map((l) => (
                  <option key={l} value={l}>
                    {localeNames[l]}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="border-rule-strong bg-paper-raised mt-2 border">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={3}
              lang={queryLang}
              placeholder={t("workspace.ask.placeholder")}
              className="text-ink placeholder:text-ink-faint block w-full resize-none px-3 py-2.5 text-sm outline-none"
            />
            <div className="border-rule flex items-center gap-2 border-t px-2 py-1.5">
              <button
                type="button"
                title={t("workspace.ask.voiceUnavailable")}
                aria-disabled="true"
                className="marginal text-ink-faint cursor-not-allowed px-1.5 py-1"
              >
                {t("workspace.ask.voice")}
              </button>
              <button
                type="button"
                className="bg-accent hover:bg-accent-hover ml-auto rounded-xs px-4 py-1.5 text-xs font-medium whitespace-nowrap text-white transition-colors"
              >
                {t("workspace.ask.submit")}
              </button>
            </div>
          </div>

          <p className="marginal mt-2.5">{t("workspace.ask.examples")}</p>
          <div className="mt-1.5 space-y-1.5">
            {EXAMPLES[mode].map((ex) => {
              const text = t(`workspace.ask.example.${ex}`);
              return (
                <button
                  key={ex}
                  type="button"
                  onClick={() => setQuestion(text)}
                  className="border-rule text-ink-muted hover:border-accent hover:text-ink block w-full border px-2.5 py-1.5 text-left text-xs leading-snug transition-colors"
                >
                  {text}
                </button>
              );
            })}
          </div>
        </section>

        <Trace steps={DEMO_STEPS} />

        <AnswerCard />
      </aside>
    </div>
  );
}
