/**
 * What counts as a TIFF, decided from the file itself.
 *
 * The first four bytes of every TIFF are the byte order ("II" little-endian or
 * "MM" big-endian) followed by the magic number 42, or 43 for BigTIFF. A
 * GeoTIFF is a TIFF with extra tags, so it starts the same way. These are the
 * same four headers the API checks; the browser checks first so a wrong file
 * is refused before a byte is sent, and the server checks again because it is
 * the one that cannot be bypassed.
 */
export const TIFF_EXTENSIONS = [".tif", ".tiff"] as const;

const TIFF_MAGIC = ["49492a00", "4d4d002a", "49492b00", "4d4d002b"];

export function hasTiffExtension(name: string): boolean {
  const lower = name.toLowerCase();
  return TIFF_EXTENSIONS.some((extension) => lower.endsWith(extension));
}

/** The filename is only a claim; these bytes are the evidence. */
export async function looksLikeTiff(file: Blob): Promise<boolean> {
  const head = new Uint8Array(await file.slice(0, 4).arrayBuffer());
  const hex = Array.from(head, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return TIFF_MAGIC.includes(hex);
}
