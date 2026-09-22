"use client";

import { useEffect, useRef, useState } from "react";
import { useFormatter, useLocale, useTranslations } from "next-intl";

import { ImageUpload, type LoadedImage } from "./image-upload";
import { LiveAnswer } from "./live-answer";
import { Scene } from "./scene";
import { Trace } from "./trace";
import { runPipeline, type RunState } from "@/lib/orchestrator";
import { localeNames, locales, type Locale } from "@/i18n/routing";

const EXAMPLES = ["single1", "single2", "change1"] as const;

export function Workspace() {
  const t = useTranslations();
  const format = useFormatter();
  const uiLocale = useLocale() as Locale;

  const [image, setImage] = useState<LoadedImage | null>(null);
  const [question, setQuestion] = useState("");
  const [queryLang, setQueryLang] = useState<Locale>(uiLocale);
  const [run, setRun] = useState<RunState | null>(null);
  const [busy, setBusy] = useState(false);
  const cancelled = useRef(false);

  // Object URLs are a real leak if the component unmounts mid-demo.
  useEffect(() => {
    return () => {
      cancelled.current = true;
      if (image) URL.revokeObjectURL(image.url);
    };
  }, [image]);

  async function start() {
    if (!image || !question.trim() || busy) return;
    setBusy(true);
    cancelled.current = false;

    for await (const state of runPipeline({
      question,
      queryLang,
      uiLang: uiLocale,
      image: {
        element: image.element,
        name: image.file.name,
        sizeBytes: image.file.size,
        type: image.file.type,
      },
      formatNumber: (n) => format.number(n),
    })) {
      if (cancelled.current) return;
      setRun(state);
    }
    setBusy(false);
  }

  function clearImage() {
    if (image) URL.revokeObjectURL(image.url);
    setImage(null);
    setRun(null);
  }

  const canRun = Boolean(image) && question.trim().length > 0 && !busy;

  return (
    <div className="mx-auto grid max-w-[110rem] gap-6 px-4 py-6 sm:px-6 xl:grid-cols-[19rem_minmax(0,1fr)_25rem]">
      {/* Left: the input and what is known about it. */}
      <aside
        data-lenis-prevent
        className="space-y-6 xl:max-h-[calc(100dvh-6rem)] xl:overflow-y-auto xl:pr-1"
      >
        <section>
          <h2 className="font-serif text-ink text-lg tracking-tight">
            {t("workspace.inputs.title")}
          </h2>
          <div className="mt-3">
            <ImageUpload
              loaded={image}
              onLoad={(img) => {
                setImage(img);
                setRun(null);
              }}
              onClear={clearImage}
            />
          </div>
        </section>

        <section>
          <h3 className="text-ink text-sm font-medium">
            {t("workspace.analyses.title")}
          </h3>
          {/* An RGB file genuinely cannot support NDVI/NDWI/LSWI. Saying so is
              the product's whole discipline, so it is stated before the run. */}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {[
              { name: "ExG", available: true },
              { name: "NDVI", available: false },
              { name: "NDWI", available: false },
              { name: "LSWI", available: false },
            ].map((a) => (
              <span
                key={a.name}
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
            {t("workspace.analyses.ndviUnavailable")}
          </p>
        </section>
      </aside>

      {/* Centre: the uploaded image, framed as a sheet. */}
      <div className="min-w-0">
        <div className="border-rule-strong bg-paper-raised border">
          <div className="border-rule divide-rule flex flex-wrap items-center divide-x border-b">
            <span className="marginal px-2.5 py-1.5">
              {image ? image.file.name : t("workspace.map.empty.title")}
            </span>
            {image && (
              <>
                <span className="marginal tabular px-2.5 py-1.5">
                  {image.width} × {image.height} px
                </span>
                <span className="marginal px-2.5 py-1.5">RGB</span>
                <span className="marginal px-2.5 py-1.5">
                  {t("upload.meta.noCrs")}
                </span>
              </>
            )}
          </div>

          <div className="bg-paper-sunk relative flex aspect-[16/10] min-h-[20rem] items-center justify-center">
            {image ? (
              /* A local object URL from the file picker — next/image cannot
                 optimise a blob: source, so a plain <img> is correct here. */
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={image.url}
                alt={image.file.name}
                className="max-h-full max-w-full object-contain"
              />
            ) : (
              <div className="px-6 text-center">
                <div className="mx-auto w-48 opacity-25">
                  <Scene variant="flood" />
                </div>
                <p className="text-ink-muted mt-4 text-sm">
                  {t("workspace.map.empty.body")}
                </p>
              </div>
            )}
          </div>

          <p className="marginal border-rule border-t px-2.5 py-2">
            {t("run.demo.notice")}
          </p>
        </div>
      </div>

      {/* Right: ask, watch, read. */}
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
                onClick={() => void start()}
                disabled={!canRun}
                className="bg-accent hover:bg-accent-hover ml-auto rounded-xs px-4 py-1.5 text-xs font-medium whitespace-nowrap text-white transition-colors disabled:cursor-not-allowed disabled:opacity-40"
              >
                {busy ? t("run.running") : t("run.start")}
              </button>
            </div>
          </div>

          {!image && <p className="marginal mt-2">{t("run.needsImage")}</p>}
          {image && !question.trim() && (
            <p className="marginal mt-2">{t("run.needsQuestion")}</p>
          )}

          <p className="marginal mt-2.5">{t("workspace.ask.examples")}</p>
          <div className="mt-1.5 space-y-1.5">
            {EXAMPLES.map((ex) => {
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

        {run && <Trace steps={run.steps} />}

        {run?.answer && (
          <LiveAnswer
            answer={run.answer}
            onAskAgain={() => {
              setRun(null);
              setQuestion("");
            }}
          />
        )}
      </aside>
    </div>
  );
}
