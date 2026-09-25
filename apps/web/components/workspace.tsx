"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";

import { ImageUpload, type LoadedImage } from "./image-upload";
import { LiveAnswer } from "./live-answer";
import { Scene } from "./scene";
import { Trace } from "./trace";
import { PipelineStages, parseBoxes } from "./pipeline-stages";
import { BandMapping } from "./band-mapping";
import {
  ALL_FEATURES,
  AnalysisView,
  ModeBar,
  StackInputs,
  loadFrame,
  resolveMode,
  type ChangeChoice,
  type Frame,
  type Mode,
  type Report,
} from "./analysis";
import {
  ApiError,
  createInputSet,
  createJob,
  subscribeToJob,
  saveAnalysis,
  uploadAsset,
  type AssetOut,
  type ErrorBody,
  type JobOut,
} from "@/lib/api";
import { localeNames, locales, type Locale } from "@/i18n/routing";

const EXAMPLES = ["single1", "single2", "change1"] as const;

type Phase = "empty" | "uploading" | "ready" | "running" | "done" | "failed";

export function Workspace({
  maxUploadMb,
  reviewThresholdPct,
}: {
  maxUploadMb: number;
  reviewThresholdPct: number;
}) {
  const t = useTranslations();
  const uiLocale = useLocale() as Locale;

  const [image, setImage] = useState<LoadedImage | null>(null);
  const [asset, setAsset] = useState<AssetOut | null>(null);
  const [job, setJob] = useState<JobOut | null>(null);
  const [phase, setPhase] = useState<Phase>("empty");
  const [error, setError] = useState<ErrorBody | null>(null);
  const [question, setQuestion] = useState("");
  const [queryLang, setQueryLang] = useState<Locale>(uiLocale);
  //: Percent while bytes are in flight; null once the server is reading.
  const [progress, setProgress] = useState<number | null>(null);
  const unsubscribe = useRef<(() => void) | null>(null);
  const [frames, setFrames] = useState<Frame[]>([]);
  const [mode, setMode] = useState<Mode>("auto");
  const [changeChoice, setChangeChoice] = useState<ChangeChoice>("auto");
  const [features, setFeatures] = useState(ALL_FEATURES);
  const [pair, setPair] = useState<[string, string] | null>(null);
  const resolved = resolveMode(mode, frames, changeChoice);
  // Each distinct result is saved to history once, after it has been on screen
  // for a moment, so flicking between toggles does not fill history with noise.
  const saved = useRef(new Set<string>());
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [saveState, setSaveState] = useState<"idle" | "saved" | "failed">("idle");
  const onResult = useCallback((report: Report) => {
    const key = JSON.stringify([report.kind, report.variant, report.frames]);
    if (pending.current) clearTimeout(pending.current);
    if (saved.current.has(key)) {
      setSaveState("saved");
      return;
    }
    setSaveState("idle");
    pending.current = setTimeout(() => {
      saveAnalysis(report)
        .then(() => {
          saved.current.add(key);
          setSaveState("saved");
        })
        .catch(() => setSaveState("failed"));
    }, 1500);
  }, []);

  async function addFrames(files: File[], primary = false) {
    const loaded = (
      await Promise.all(files.map((f) => loadFrame(f).catch(() => null)))
    ).filter((f): f is Frame => f !== null);
    if (primary) loaded.forEach((f) => (f.primary = true));
    setFrames((fs) => (primary ? [...loaded, ...fs.filter((f) => !f.primary)] : [...fs, ...loaded]));
  }

  useEffect(() => {
    return () => {
      unsubscribe.current?.();
      if (image?.url) URL.revokeObjectURL(image.url);
    };
  }, [image]);

  const handleUpload = useCallback(async (loaded: LoadedImage) => {
    setImage(loaded);
    // The Q&A image also joins the stack, so it can be compared too.
    if (loaded.url) void addFrames([loaded.file], true);
    setJob(null);
    setError(null);
    setPhase("uploading");
    setProgress(0);
    try {
      const uploaded = await uploadAsset(loaded.file, (percent) => {
        // Once every byte is sent the server still has to read headers, so
        // the bar hands over to the indeterminate state rather than sitting
        // at 100% looking stuck.
        setProgress(percent >= 100 ? null : percent);
      });
      setProgress(null);
      setAsset(uploaded);
      setPhase("ready");
    } catch (cause) {
      setProgress(null);
      setAsset(null);
      setImage(null);
      setPhase("empty");
      setError(
        cause instanceof ApiError
          ? cause.body
          : { key: "error.apiUnreachable.title", params: {} as never },
      );
    }
  }, []);

  function clearImage() {
    setFrames((fs) => fs.filter((f) => !f.primary));
    unsubscribe.current?.();
    if (image?.url) URL.revokeObjectURL(image.url);
    setImage(null);
    setAsset(null);
    setJob(null);
    setError(null);
    setProgress(null);
    setPhase("empty");
  }

  async function run() {
    if (!asset || !question.trim() || phase === "running") return;
    setError(null);
    setPhase("running");
    try {
      const inputSet = await createInputSet("single", { single: asset.id });
      if (inputSet.blocked) {
        setPhase("ready");
        setError({
          key: "job.error.inputSetBlocked",
          params: {} as never,
        });
        return;
      }

      const created = await createJob({
        input_set_id: inputSet.id,
        query_text: question,
        query_lang: queryLang,
        ui_lang: uiLocale,
      });
      setJob(created);

      unsubscribe.current?.();
      unsubscribe.current = subscribeToJob(created.id, {
        onSnapshot: (snapshot) => {
          setJob(snapshot);
          if (snapshot.status === "failed") setPhase("failed");
        },
        onDone: () => setPhase("done"),
        onError: (body) => {
          setError(body);
          setPhase("done");
        },
      });
    } catch (cause) {
      setPhase("ready");
      setError(
        cause instanceof ApiError
          ? cause.body
          : { key: "error.apiUnreachable.title", params: {} as never },
      );
    }
  }

  const canRun = Boolean(asset) && question.trim().length > 0 && phase !== "running";
  const answered = job?.status === "succeeded" || job?.status === "needs_review";
  const boxes = parseBoxes(
    job?.steps.find((s) => s.step_key === "vision_language")?.output_summary?.boxes_2d,
  );

  return (
    <div className="workspace-large mx-auto grid max-w-[110rem] gap-6 px-4 py-6 sm:px-6 xl:grid-cols-[19rem_minmax(0,1fr)_25rem]">
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
              asset={asset}
              busy={phase === "uploading"}
              progress={progress}
              maxMb={maxUploadMb}
              onLoad={handleUpload}
              onClear={clearImage}
            />
          </div>
        </section>

        <StackInputs
          frames={frames}
          onAdd={(files) => void addFrames(files)}
          onUpdate={(id, patch) =>
            setFrames((fs) => fs.map((f) => (f.id === id ? { ...f, ...patch } : f)))
          }
          onRemove={(id) => setFrames((fs) => fs.filter((f) => f.id !== id))}
        />

        {asset && (
          <BandMapping
            asset={asset}
            onChange={(updated) => {
              setAsset(updated);
              setJob(null);
            }}
          />
        )}
      </aside>

      <div className="min-w-0">
        <ModeBar
          mode={mode}
          onMode={setMode}
          changeChoice={changeChoice}
          onChangeChoice={setChangeChoice}
          features={features}
          onFeatures={setFeatures}
          frames={frames}
        />
        {resolved.mode !== "single" && saveState !== "idle" && (
          <p className="marginal mb-2 text-right" role="status">
            {saveState === "saved" ? "✓ Saved to your history" : "Could not save to history. The API is unreachable."}
          </p>
        )}
        {resolved.mode !== "single" ? (
          <AnalysisView
            frames={frames}
            mode={resolved.mode}
            changeKind={resolved.changeKind}
            features={features}
            pair={pair}
            onPair={setPair}
            onResult={onResult}
          />
        ) : (
        <div className="border-rule-strong bg-paper-raised border">
          <div className="border-rule divide-rule flex flex-wrap items-center divide-x border-b">
            <span className="marginal px-2.5 py-1.5">
              {asset ? asset.filename : t("workspace.map.empty.title")}
            </span>
            {asset && (
              <>
                <span className="marginal tabular px-2.5 py-1.5">
                  {asset.width} × {asset.height} px
                </span>
                <span className="marginal px-2.5 py-1.5">
                  {asset.band_count} {t("workspace.bands.title")}
                </span>
                <span className="marginal px-2.5 py-1.5">
                  {asset.crs ?? t("upload.meta.noCrs")}
                </span>
                {asset.pixel_size ? (
                  <span className="marginal tabular px-2.5 py-1.5">
                    {asset.pixel_size} m
                  </span>
                ) : null}
              </>
            )}
          </div>

          <div className="bg-paper-sunk relative flex min-h-[20rem] items-center justify-center p-2">
            {image?.url ? (
              /* A local object URL; next/image cannot optimise a blob source. */
              /* Filled to the column, capped by screen height; the wrapper keeps
                 the image's own shape so boxes drawn over it stay aligned. */
              <div
                className="relative"
                style={{
                  width: `min(100%, calc(75dvh * ${image.width || 16} / ${image.height || 10}))`,
                }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={image.url}
                  alt={image.file.name}
                  className="block h-auto w-full"
                />
                {boxes.length > 0 && (
                  <svg
                    viewBox="0 0 1000 1000"
                    preserveAspectRatio="none"
                    className="pointer-events-none absolute inset-0 h-full w-full"
                  >
                    {boxes.map((b, i) => (
                      <g key={i}>
                        <rect
                          x={b.box[0]}
                          y={b.box[1]}
                          width={b.box[2] - b.box[0]}
                          height={b.box[3] - b.box[1]}
                          fill="none"
                          stroke={b.status === "corroborated" || b.status === "measured" ? "#16a34a" : "#f59e0b"}
                          strokeWidth={4}
                          vectorEffect="non-scaling-stroke"
                        />
                        <text x={b.box[0] + 6} y={Math.max(b.box[1] - 8, 28)} fontSize={28} fill="#fff" stroke="#000" strokeWidth={0.6}>
                          {b.label}
                        </text>
                      </g>
                    ))}
                  </svg>
                )}
              </div>
            ) : image ? (
              /* GeoTIFF: no browser preview, so show what was read instead of
                 an empty frame. Real tiles arrive once the tiler is wired. */
              <div className="px-6 text-center">
                <div className="border-rule mx-auto aspect-[16/10] w-64 overflow-hidden border opacity-80">
                  <Scene variant="flood" showLabel={false} sizes="16rem" />
                </div>
                <p className="text-ink-muted mt-4 text-sm">
                  {t("upload.error.geotiffPreview")}
                </p>
              </div>
            ) : (
              <div className="px-6 text-center">
                <div className="border-rule mx-auto aspect-[16/10] w-64 overflow-hidden border opacity-80">
                  <Scene variant="flood" showLabel={false} sizes="16rem" />
                </div>
                <p className="text-ink-muted mt-4 text-sm">
                  {t("workspace.map.empty.body")}
                </p>
              </div>
            )}
          </div>

          <p className="marginal border-rule border-t px-2.5 py-2">
            {t("run.server.notice")}
          </p>
        </div>
        )}
      </div>

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
                onClick={() => void run()}
                disabled={!canRun}
                className="bg-accent hover:bg-accent-hover ml-auto rounded-xs px-4 py-1.5 text-xs font-medium whitespace-nowrap text-white transition-colors disabled:cursor-not-allowed disabled:opacity-40"
              >
                {phase === "running" ? t("run.running") : t("run.start")}
              </button>
            </div>
          </div>

          {error && (
            <p className="border-alert bg-alert-wash/60 text-ink marginal mt-2 border-l-2 px-2.5 py-2">
              {t.has(error.key) ? t(error.key) : error.key}
            </p>
          )}
          {!asset && phase !== "uploading" && (
            <p className="marginal mt-2">{t("run.needsImage")}</p>
          )}
          {asset && !question.trim() && (
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

        {job && <PipelineStages steps={job.steps} />}

        {job && <Trace steps={job.steps} jobId={job.id} />}

        {job && answered && <LiveAnswer
            job={job}
            thresholdPct={reviewThresholdPct}
            onAskAgain={() => setQuestion("")}
          />}
      </aside>
    </div>
  );
}
