// @vitest-environment node
// Node's own File and Blob, which implement arrayBuffer(); jsdom's do not.
import { describe, expect, it } from "vitest";

import { hasTiffExtension, looksLikeTiff } from "./tiff";

const blob = (hex: string, extra = 16) =>
  new Blob([Buffer.concat([Buffer.from(hex, "hex"), Buffer.alloc(extra)])]);

describe("looksLikeTiff", () => {
  it.each([
    ["little-endian", "49492a00"],
    ["big-endian", "4d4d002a"],
    ["BigTIFF little-endian", "49492b00"],
    ["BigTIFF big-endian", "4d4d002b"],
  ])("accepts %s", async (_label, hex) => {
    expect(await looksLikeTiff(blob(hex))).toBe(true);
  });

  it.each([
    ["JPEG", "ffd8ffe0"],
    ["PNG", "89504e470d0a1a0a"],
    ["WebP", "52494646"],
    ["a truncated header", "49492a"],
  ])("refuses %s", async (_label, hex) => {
    expect(await looksLikeTiff(blob(hex, 0))).toBe(false);
  });

  it("refuses an empty file", async () => {
    expect(await looksLikeTiff(new Blob([]))).toBe(false);
  });
});

describe("hasTiffExtension", () => {
  it.each(["scene.tif", "scene.tiff", "SCENE.TIF", "a.b.Tiff"])("accepts %s", (name) => {
    expect(hasTiffExtension(name)).toBe(true);
  });

  it.each(["scene.png", "scene.jpg", "scene.tif.png", "tif", ""])("refuses %s", (name) => {
    expect(hasTiffExtension(name)).toBe(false);
  });
});
