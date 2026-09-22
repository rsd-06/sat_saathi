/**
 * Real, in-browser measurement of an uploaded RGB image.
 *
 * What is honest here matters more than what is impressive. A PNG or JPEG
 * carries no near-infrared band and no coordinate system, so NDVI, NDWI and
 * LSWI are genuinely not computable and area on the ground is unknowable.
 * Rather than substitute bands, this module computes indices that ARE valid
 * for three-channel imagery and reports the rest as unavailable, with reasons.
 *
 * ExG (Excess Green, 2G - R - B on normalised channels) is a standard RGB
 * vegetation proxy. It is not NDVI and is never labelled as such.
 */

/** Matches MAX_INDEX_PIXELS in the backend settings: cap work, report the cap. */
const MAX_EDGE = 1024;

export type IndexStats = {
  mean: number;
  min: number;
  max: number;
  aboveThresholdPct: number;
  threshold: number;
};

export type ImageAnalysis = {
  width: number;
  height: number;
  sampledWidth: number;
  sampledHeight: number;
  pixelsSampled: number;
  downsampled: boolean;
  exg: IndexStats;
  /** Fraction of pixels that are dark and blue-dominant — an open-water proxy. */
  waterProxyPct: number;
  /** Mean channel values, 0-255, useful as a plain description of the scene. */
  meanChannels: { r: number; g: number; b: number };
  brightness: number;
  durationMs: number;
};

function clamp01(n: number) {
  return n < 0 ? 0 : n > 1 ? 1 : n;
}

export async function analyzeImage(
  source: HTMLImageElement,
  { exgThreshold = 0.06 }: { exgThreshold?: number } = {},
): Promise<ImageAnalysis> {
  const started = performance.now();

  const width = source.naturalWidth;
  const height = source.naturalHeight;
  const scale = Math.min(1, MAX_EDGE / Math.max(width, height));
  const sw = Math.max(1, Math.round(width * scale));
  const sh = Math.max(1, Math.round(height * scale));

  const canvas = document.createElement("canvas");
  canvas.width = sw;
  canvas.height = sh;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("canvas-unavailable");
  ctx.drawImage(source, 0, 0, sw, sh);

  const { data } = ctx.getImageData(0, 0, sw, sh);

  let sumExg = 0;
  let minExg = Number.POSITIVE_INFINITY;
  let maxExg = Number.NEGATIVE_INFINITY;
  let above = 0;
  let water = 0;
  let sumR = 0;
  let sumG = 0;
  let sumB = 0;
  let counted = 0;

  for (let i = 0; i < data.length; i += 4) {
    const a = data[i + 3]!;
    if (a < 8) continue; // fully transparent padding is not scene content
    const r = data[i]!;
    const g = data[i + 1]!;
    const b = data[i + 2]!;

    sumR += r;
    sumG += g;
    sumB += b;
    counted++;

    const total = r + g + b;
    if (total === 0) {
      // Pure black: ExG is undefined rather than zero, so skip the index only.
      water++;
      minExg = Math.min(minExg, 0);
      maxExg = Math.max(maxExg, 0);
      continue;
    }
    const rn = r / total;
    const gn = g / total;
    const bn = b / total;
    const exg = 2 * gn - rn - bn;

    sumExg += exg;
    if (exg < minExg) minExg = exg;
    if (exg > maxExg) maxExg = exg;
    if (exg > exgThreshold) above++;

    const luma = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
    if (luma < 0.35 && bn > rn && bn > 0.34) water++;
  }

  const safeCount = counted || 1;

  return {
    width,
    height,
    sampledWidth: sw,
    sampledHeight: sh,
    pixelsSampled: counted,
    downsampled: scale < 1,
    exg: {
      mean: sumExg / safeCount,
      min: Number.isFinite(minExg) ? minExg : 0,
      max: Number.isFinite(maxExg) ? maxExg : 0,
      aboveThresholdPct: (above / safeCount) * 100,
      threshold: exgThreshold,
    },
    waterProxyPct: (water / safeCount) * 100,
    meanChannels: {
      r: sumR / safeCount,
      g: sumG / safeCount,
      b: sumB / safeCount,
    },
    brightness: clamp01(
      (0.2126 * (sumR / safeCount) +
        0.7152 * (sumG / safeCount) +
        0.0722 * (sumB / safeCount)) /
        255,
    ),
    durationMs: Math.round(performance.now() - started),
  };
}
