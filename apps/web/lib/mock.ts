/**
 * Fixture data for the UI preview. The shapes here deliberately mirror the API
 * contract in the spec (jobs, steps, artifacts) so swapping in the generated
 * client later is a data-source change, not a rewrite.
 */

export type StepKey =
  | "ask"
  | "imagery"
  | "understand"
  | "preprocess"
  | "compute"
  | "vision_language"
  | "verify"
  | "answer";

export type StepStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "skipped"
  | "failed"
  | "needs_review";

export type JobMode = "single" | "fusion" | "change";

export type Step = {
  key: StepKey;
  status: StepStatus;
  tool: string;
  version: string;
  isStub: boolean;
  durationMs: number | null;
  params?: Record<string, string | number>;
  output?: Record<string, string | number>;
  artifacts?: { name: string; kind: string }[];
};

export const STEP_ORDER: StepKey[] = [
  "ask",
  "imagery",
  "understand",
  "preprocess",
  "compute",
  "vision_language",
  "verify",
  "answer",
];

export const DEMO_STEPS: Step[] = [
  {
    key: "ask",
    status: "succeeded",
    tool: "intake.text",
    version: "0.1.0",
    isStub: false,
    durationMs: 4,
    params: { query_lang: "en", ui_lang: "en" },
    output: { chars: 58 },
  },
  {
    key: "imagery",
    status: "succeeded",
    tool: "rasterio.inspect",
    version: "0.1.0",
    isStub: false,
    durationMs: 38,
    params: { headers_only: "true" },
    output: {
      crs: "EPSG:32645",
      pixel_size_m: 10,
      bands: 4,
      width: 2048,
      height: 2048,
    },
    artifacts: [{ name: "footprint.geojson", kind: "geojson" }],
  },
  {
    key: "understand",
    status: "succeeded",
    tool: "intent.keyword",
    version: "0.1.0",
    isStub: true,
    durationMs: 12,
    params: { translate: "passthrough" },
    output: { intent: "vqa_area", aoi: "full_scene" },
  },
  {
    key: "preprocess",
    status: "skipped",
    tool: "preprocess.noop",
    version: "0.1.0",
    isStub: true,
    durationMs: 2,
    output: { reason: "already co-registered" },
  },
  {
    key: "compute",
    status: "succeeded",
    tool: "indices.ndwi",
    version: "0.1.0",
    isStub: false,
    durationMs: 412,
    params: { green: "B03", nir: "B08", threshold: 0.3 },
    output: {
      mean: 0.11,
      min: -0.82,
      max: 0.94,
      above_threshold_pct: 31.7,
      area_ha: 142.4,
    },
    artifacts: [{ name: "ndwi.tif", kind: "cog" }],
  },
  {
    key: "vision_language",
    status: "succeeded",
    tool: "vlm.fixture",
    version: "0.1.0",
    isStub: true,
    durationMs: 260,
    params: { task: "vqa" },
    output: { boxes: 3, caption_chars: 112 },
  },
  {
    key: "verify",
    status: "succeeded",
    tool: "verify.crosscheck",
    version: "0.1.0",
    isStub: true,
    durationMs: 26,
    params: { threshold: 0.75 },
    output: { confidence: 0.86, agreement: "consistent" },
  },
  {
    key: "answer",
    status: "running",
    tool: "answer.compose",
    version: "0.1.0",
    isStub: true,
    durationMs: null,
    params: { target_lang: "en" },
  },
];

export type RecentJob = {
  id: string;
  question: string;
  mode: JobMode;
  status: "succeeded" | "running" | "needs_review" | "failed";
  lang: string;
  date: string;
  areaHa?: number;
  confidence?: number;
};

export const RECENT_JOBS: RecentJob[] = [
  {
    id: "j-4821",
    question: "How much paddy was lost to flooding?",
    mode: "change",
    status: "succeeded",
    lang: "bn",
    date: "2026-09-21",
    areaHa: 142.4,
    confidence: 0.86,
  },
  {
    id: "j-4817",
    question:
      "Use the optical and SAR images together to identify built-up and water-covered regions.",
    mode: "fusion",
    status: "needs_review",
    lang: "en",
    date: "2026-09-20",
    areaHa: 68.2,
    confidence: 0.61,
  },
  {
    id: "j-4802",
    question: "Describe the land cover in this image.",
    mode: "single",
    status: "succeeded",
    lang: "ta",
    date: "2026-09-18",
    areaHa: 311.9,
    confidence: 0.91,
  },
  {
    id: "j-4790",
    question: "What changed between these two dates?",
    mode: "change",
    status: "failed",
    lang: "hi",
    date: "2026-09-17",
  },
];
