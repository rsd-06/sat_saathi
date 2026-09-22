/**
 * Runs the eight fixed pipeline steps in order and records a trace as it goes.
 *
 * This is the rule-based planner the spec calls for, not an agent: the plan is
 * decided by (intent, input mode) and nothing here reasons about anything. The
 * real orchestrator replaces `runPipeline` behind the same generator contract,
 * and the trace it emits keeps the same shape.
 *
 * Steps marked `isStub` return fixture output. Steps that are not marked stub
 * measured something real, and the trace says which is which — the distinction
 * is the point of showing the trace at all.
 */

import { analyzeImage, type ImageAnalysis } from "./analyze";
import { classifyIntentDetailed, type Intent } from "./intent";
import { composeAnswer, type ComposedAnswer } from "./compose";
import type { StepKey, StepStatus } from "./mock";

export type RunStep = {
  key: StepKey;
  status: StepStatus;
  tool: string;
  version: string;
  isStub: boolean;
  durationMs: number | null;
  params?: Record<string, string | number>;
  output?: Record<string, string | number>;
  artifacts?: { name: string; kind: string }[];
  /** Set when a step declines to produce a number it cannot support. */
  note?: string;
};

export type RunState = {
  steps: RunStep[];
  answer: ComposedAnswer | null;
  analysis: ImageAnalysis | null;
  intent: Intent | null;
  done: boolean;
};

const ORDER: StepKey[] = [
  "ask",
  "imagery",
  "understand",
  "preprocess",
  "compute",
  "vision_language",
  "verify",
  "answer",
];

const TOOLS: Record<StepKey, { tool: string; version: string; isStub: boolean }> =
  {
    ask: { tool: "intake.text", version: "0.1.0", isStub: false },
    imagery: { tool: "browser.imageHeader", version: "0.1.0", isStub: false },
    understand: { tool: "intent.keyword", version: "0.1.0", isStub: true },
    preprocess: { tool: "preprocess.noop", version: "0.1.0", isStub: true },
    compute: { tool: "indices.exg", version: "0.1.0", isStub: false },
    vision_language: { tool: "vlm.fixture", version: "0.1.0", isStub: true },
    verify: { tool: "verify.crosscheck", version: "0.1.0", isStub: false },
    answer: { tool: "answer.template", version: "0.1.0", isStub: true },
  };

/** Visible pacing so the trace can be watched. Not a simulation of real cost. */
const PACING: Partial<Record<StepKey, number>> = {
  ask: 120,
  imagery: 220,
  understand: 260,
  preprocess: 180,
  vision_language: 420,
  verify: 240,
  answer: 300,
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function seed(): RunStep[] {
  return ORDER.map((key) => ({
    key,
    ...TOOLS[key],
    status: "pending" as StepStatus,
    durationMs: null,
  }));
}

export type RunInput = {
  question: string;
  queryLang: string;
  uiLang: string;
  image: { element: HTMLImageElement; name: string; sizeBytes: number; type: string };
  /** Locale-aware, supplied by the caller so figures match the chosen language. */
  formatNumber: (n: number) => string;
};

/**
 * Yields the whole state after every transition so the caller can render it.
 * Async generator rather than callbacks so cancellation is just breaking out.
 */
export async function* runPipeline(
  input: RunInput,
): AsyncGenerator<RunState, RunState, void> {
  const steps = seed();
  let analysis: ImageAnalysis | null = null;
  let intent: Intent | null = null;
  let answer: ComposedAnswer | null = null;

  const snapshot = (done = false): RunState => ({
    steps: steps.map((s) => ({ ...s })),
    answer,
    analysis,
    intent,
    done,
  });

  for (const key of ORDER) {
    const step = steps.find((s) => s.key === key)!;
    step.status = "running";
    yield snapshot();

    const started = performance.now();
    await sleep(PACING[key] ?? 150);

    switch (key) {
      case "ask": {
        step.params = { query_lang: input.queryLang, ui_lang: input.uiLang };
        step.output = { chars: input.question.length };
        break;
      }

      case "imagery": {
        const { element, name, sizeBytes, type } = input.image;
        step.params = { headers_only: "true" };
        step.output = {
          file: name,
          type,
          width: element.naturalWidth,
          height: element.naturalHeight,
          bytes: sizeBytes,
          bands: 3,
          crs: "none",
        };
        step.note = "rgb-no-crs";
        break;
      }

      case "understand": {
        const match = classifyIntentDetailed(input.question);
        intent = match.intent;
        step.params = { translate: "passthrough", classifier: "keyword" };
        // The evidence goes in the trace: if a keyword misfires, it is visible
        // here rather than only showing up as a surprising intent downstream.
        step.output = {
          intent,
          query_lang: input.queryLang,
          matched: match.matched.length ? match.matched.join(" ") : "(none)",
          score: match.score,
        };
        if (match.score === 0) step.note = "intent-defaulted";
        break;
      }

      case "preprocess": {
        step.status = "skipped";
        step.output = { reason: "single RGB image; nothing to co-register" };
        break;
      }

      case "compute": {
        analysis = await analyzeImage(input.image.element);
        step.params = {
          index: "ExG",
          threshold: analysis.exg.threshold,
          max_edge_px: 1024,
        };
        step.output = {
          mean: Number(analysis.exg.mean.toFixed(4)),
          min: Number(analysis.exg.min.toFixed(4)),
          max: Number(analysis.exg.max.toFixed(4)),
          above_threshold_pct: Number(analysis.exg.aboveThresholdPct.toFixed(2)),
          water_proxy_pct: Number(analysis.waterProxyPct.toFixed(2)),
          pixels_sampled: analysis.pixelsSampled,
          downsampled: String(analysis.downsampled),
        };
        // The refusal is part of the record, not a UI afterthought.
        step.note = "ndvi-ndwi-unavailable";
        break;
      }

      case "vision_language": {
        step.params = { task: "vqa" };
        step.output = { caption: "fixture", boxes: 0 };
        break;
      }

      case "verify": {
        const conf = analysis
          ? composeAnswer(
              intent ?? "land_cover",
              analysis,
              input.image.name,
              input.formatNumber,
            ).confidence
          : 0;
        step.params = { threshold: 0.75 };
        step.output = {
          confidence: Number(conf.toFixed(2)),
          verdict: conf >= 0.75 ? "released" : "held_for_review",
        };
        if (conf < 0.75) step.status = "needs_review";
        break;
      }

      case "answer": {
        if (analysis) {
          answer = composeAnswer(
            intent ?? "land_cover",
            analysis,
            input.image.name,
            input.formatNumber,
          );
        }
        step.params = { target_lang: input.uiLang };
        step.output = { chars: answer?.text.length ?? 0 };
        break;
      }
    }

    if (step.status === "running") step.status = "succeeded";
    step.durationMs =
      key === "compute" && analysis
        ? analysis.durationMs
        : Math.round(performance.now() - started);

    yield snapshot();
  }

  return snapshot(true);
}
