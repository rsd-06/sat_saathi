import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ImageAnalysis } from "./analyze";

const analysis: ImageAnalysis = {
  width: 800,
  height: 600,
  sampledWidth: 800,
  sampledHeight: 600,
  pixelsSampled: 480000,
  downsampled: false,
  exg: { mean: 0.05, min: -0.2, max: 0.4, aboveThresholdPct: 44, threshold: 0.06 },
  waterProxyPct: 9,
  meanChannels: { r: 100, g: 120, b: 90 },
  brightness: 0.44,
  durationMs: 12,
};

// Canvas is unavailable under jsdom, so the measurement step is stubbed here.
// What this test covers is the orchestration: order, statuses, and the trace.
vi.mock("./analyze", () => ({
  analyzeImage: vi.fn(async () => analysis),
}));

const { runPipeline } = await import("./orchestrator");
const { STEP_ORDER } = await import("./mock");

function input(question: string) {
  return {
    question,
    queryLang: "en",
    uiLang: "en",
    image: {
      element: { naturalWidth: 800, naturalHeight: 600 } as HTMLImageElement,
      name: "scene.png",
      sizeBytes: 1024,
      type: "image/png",
    },
    formatNumber: (n: number) => String(n),
  };
}

async function runToEnd(question: string) {
  const states = [];
  for await (const s of runPipeline(input(question))) states.push(s);
  return states;
}

describe("runPipeline", () => {
  beforeEach(() => {
    vi.useRealTimers();
  });

  it("visits all eight steps in the fixed order", async () => {
    const states = await runToEnd("How much water is there?");
    const final = states.at(-1)!;
    expect(final.steps.map((s) => s.key)).toEqual(STEP_ORDER);
  });

  it("leaves no step pending and records a duration for each", async () => {
    const final = (await runToEnd("Describe this image")).at(-1)!;
    for (const step of final.steps) {
      expect(step.status).not.toBe("pending");
      expect(step.durationMs).toBeTypeOf("number");
    }
  });

  it("emits a running state before each step settles", async () => {
    const states = await runToEnd("Describe this image");
    for (const key of STEP_ORDER) {
      const sawRunning = states.some(
        (s) => s.steps.find((x) => x.key === key)?.status === "running",
      );
      expect(sawRunning, `${key} never reported running`).toBe(true);
    }
  });

  it("skips preprocessing for a single image rather than pretending to run it", async () => {
    const final = (await runToEnd("Describe this image")).at(-1)!;
    const pre = final.steps.find((s) => s.key === "preprocess")!;
    expect(pre.status).toBe("skipped");
  });

  it("routes the question to an intent and answers from measured values", async () => {
    const final = (await runToEnd("How much paddy is there?")).at(-1)!;
    expect(final.intent).toBe("vegetation");
    expect(final.answer?.text).toContain("44.0%");
    expect(final.analysis).toEqual(analysis);
  });

  it("holds a low-confidence answer for review in the trace", async () => {
    const final = (await runToEnd("What changed between the dates?")).at(-1)!;
    const verify = final.steps.find((s) => s.key === "verify")!;
    expect(verify.status).toBe("needs_review");
    expect(verify.output?.verdict).toBe("held_for_review");
  });

  it("marks which steps were real and which returned fixture output", async () => {
    const final = (await runToEnd("Describe this image")).at(-1)!;
    const byKey = Object.fromEntries(final.steps.map((s) => [s.key, s.isStub]));
    expect(byKey.compute).toBe(false);
    expect(byKey.imagery).toBe(false);
    expect(byKey.vision_language).toBe(true);
    expect(byKey.answer).toBe(true);
  });

  it("records that NDVI and NDWI were declined, not computed", async () => {
    const final = (await runToEnd("How much water?")).at(-1)!;
    const compute = final.steps.find((s) => s.key === "compute")!;
    expect(compute.params?.index).toBe("ExG");
    expect(compute.note).toBe("ndvi-ndwi-unavailable");
  });
});
