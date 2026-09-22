/**
 * Turns measured numbers into an answer. This is the templated stand-in for
 * the LLM phrasing step: every sentence is assembled from values that were
 * actually computed, so the demo never states something the numbers do not
 * support. The real LLM provider replaces `composeAnswer` behind this shape.
 */

import type { ImageAnalysis } from "./analyze";
import type { Intent } from "./intent";

export type Stat = {
  value: string;
  label: string;
  /** What the number was derived from. Shown under every figure. */
  source: string;
};

export type ComposedAnswer = {
  intent: Intent;
  text: string;
  stats: Stat[];
  confidence: number;
  /** Set when the question asks for something this input cannot answer. */
  limitation?: string;
};

const pct = (n: number) => `${n.toFixed(1)}%`;

/**
 * Number formatting is injected rather than done here: a bare toLocaleString()
 * would follow the machine's locale, not the one the officer selected, so the
 * same scene would render "589,824" or "5,89,824" depending on the laptop.
 */
export type NumberFormatter = (n: number) => string;

export function composeAnswer(
  intent: Intent,
  a: ImageAnalysis,
  fileName: string,
  formatNumber: NumberFormatter = (n) => String(n),
): ComposedAnswer {
  const resolution = `${a.width} × ${a.height} px`;
  const sourceExg = `ExG > ${a.exg.threshold}`;

  const base: Stat[] = [
    {
      value: pct(a.exg.aboveThresholdPct),
      label: "Vegetated pixels",
      source: sourceExg,
    },
    {
      value: a.exg.mean.toFixed(3),
      label: "Mean ExG",
      source: `${formatNumber(a.pixelsSampled)} px sampled`,
    },
    { value: resolution, label: "Image size", source: fileName },
  ];

  switch (intent) {
    case "water_extent":
      return {
        intent,
        text: `About ${pct(a.waterProxyPct)} of the pixels are dark and blue-dominant, which is consistent with open water in a three-channel image. This is a brightness-and-colour proxy, not a water index: NDWI needs a green and a near-infrared band, and this file has neither. Treat the figure as an indication of where to look, not as a measured water extent.`,
        stats: [
          {
            value: pct(a.waterProxyPct),
            label: "Water-like pixels",
            source: "RGB luminance + blue dominance",
          },
          {
            value: pct(a.exg.aboveThresholdPct),
            label: "Vegetated pixels",
            source: sourceExg,
          },
          { value: resolution, label: "Image size", source: fileName },
        ],
        confidence: 0.42,
        limitation:
          "NDWI is unavailable on RGB input, and without a coordinate system the area cannot be converted to hectares.",
      };

    case "vegetation":
      return {
        intent,
        text: `${pct(a.exg.aboveThresholdPct)} of the sampled pixels exceed an Excess Green value of ${a.exg.threshold}, with a mean ExG of ${a.exg.mean.toFixed(3)} across ${formatNumber(a.pixelsSampled)} pixels. ExG is a red-green-blue vegetation proxy; it separates green canopy from soil and water, but it is not NDVI and will not distinguish crop stress the way a near-infrared band would.`,
        stats: base,
        confidence: 0.63,
        limitation:
          "NDVI needs a red and a near-infrared band. This file has no near-infrared band, so crop-health questions cannot be answered from it.",
      };

    case "change":
      return {
        intent,
        text: `Change detection needs two co-registered images of the same ground on different dates. One image was uploaded, so there is nothing to difference. What can be said about this single scene: ${pct(a.exg.aboveThresholdPct)} of pixels read as vegetated and ${pct(a.waterProxyPct)} as water-like.`,
        stats: base,
        confidence: 0.2,
        limitation:
          "A before-and-after pair is required. Upload a second image of the same area to measure change.",
      };

    case "built_up":
      return {
        intent,
        text: `Built-up extraction is not measurable from this input. Separating buildings and roads from bare soil reliably needs either SAR backscatter or a short-wave infrared band; on three visible channels, concrete, dry soil and rooftops overlap heavily. For reference, the scene averages R ${a.meanChannels.r.toFixed(0)}, G ${a.meanChannels.g.toFixed(0)}, B ${a.meanChannels.b.toFixed(0)} with ${pct(a.exg.aboveThresholdPct)} vegetated pixels.`,
        stats: base,
        confidence: 0.24,
        limitation:
          "Built-up detection needs SAR or SWIR. Upload an optical and SAR pair to answer this properly.",
      };

    default:
      return {
        intent,
        text: `The scene is ${a.brightness > 0.6 ? "bright" : a.brightness > 0.35 ? "moderately lit" : "dark"} overall, averaging R ${a.meanChannels.r.toFixed(0)}, G ${a.meanChannels.g.toFixed(0)}, B ${a.meanChannels.b.toFixed(0)}. ${pct(a.exg.aboveThresholdPct)} of pixels read as vegetated by Excess Green and ${pct(a.waterProxyPct)} as water-like. A fuller land-cover breakdown needs a multispectral image with a near-infrared band.`,
        stats: base,
        confidence: 0.55,
        limitation:
          "Land-cover classes beyond vegetation and water need more than three visible bands.",
      };
  }
}
