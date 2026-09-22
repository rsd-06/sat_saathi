import { describe, expect, it } from "vitest";

import { composeAnswer } from "./compose";
import type { ImageAnalysis } from "./analyze";

const analysis: ImageAnalysis = {
  width: 1600,
  height: 900,
  sampledWidth: 1024,
  sampledHeight: 576,
  pixelsSampled: 589824,
  downsampled: true,
  exg: {
    mean: 0.0421,
    min: -0.31,
    max: 0.48,
    aboveThresholdPct: 37.25,
    threshold: 0.06,
  },
  waterProxyPct: 12.5,
  meanChannels: { r: 96, g: 118, b: 88 },
  brightness: 0.42,
  durationMs: 31,
};

describe("composeAnswer", () => {
  it("never attributes a figure to NDVI on RGB input", () => {
    const out = composeAnswer("vegetation", analysis, "scene.png");
    // Mentioning NDVI to rule it out is correct; sourcing a number from it
    // would not be. The invariant is about provenance, not vocabulary.
    expect(out.stats.every((s) => !/NDVI|NDWI|LSWI/.test(s.source))).toBe(true);
    expect(out.text).toMatch(/not NDVI/);
    expect(out.limitation).toMatch(/near-infrared/i);
    expect(out.stats.some((s) => s.source.includes("ExG"))).toBe(true);
  });

  it("states the water figure is a proxy, not NDWI", () => {
    const out = composeAnswer("water_extent", analysis, "scene.png");
    expect(out.text).toMatch(/proxy/i);
    expect(out.limitation).toMatch(/NDWI/);
    // A proxy must not be presented with high confidence.
    expect(out.confidence).toBeLessThan(0.75);
  });

  it("refuses change detection when only one image was given", () => {
    const out = composeAnswer("change", analysis, "scene.png");
    expect(out.limitation).toMatch(/before-and-after|second image/i);
    expect(out.confidence).toBeLessThan(0.5);
  });

  it("reports only figures that were actually measured", () => {
    const out = composeAnswer("land_cover", analysis, "scene.png");
    // Every stat traces back to a computed value, never a hectare figure,
    // because an RGB file carries no coordinate system.
    expect(out.stats.every((s) => s.source.length > 0)).toBe(true);
    expect(JSON.stringify(out)).not.toMatch(/\bha\b/);
  });

  it("carries the measured percentage into the text verbatim", () => {
    const out = composeAnswer("vegetation", analysis, "scene.png");
    expect(out.text).toContain("37.3%");
  });

  it("formats counts through the injected locale formatter", () => {
    const en = composeAnswer("vegetation", analysis, "s.png", (n) =>
      new Intl.NumberFormat("en-US").format(n),
    );
    const hi = composeAnswer("vegetation", analysis, "s.png", (n) =>
      new Intl.NumberFormat("hi-IN").format(n),
    );
    expect(en.text).toContain("589,824");
    // Indian grouping differs; the figure must follow the chosen locale, not
    // whatever locale the machine running the browser happens to have.
    expect(hi.text).toContain("5,89,824");
    expect(en.text).not.toBe(hi.text);
  });
});
