export type Nested = { [key: string]: string | Nested };

/**
 * The catalogs are stored flat ("workspace.trace.title") so the Python side can
 * read the same files for PDF report templates. next-intl resolves dots as
 * nesting, so they are expanded here at load time.
 *
 * Keys beginning with "_" are metadata and are dropped. A key that is also the
 * prefix of another key cannot be represented; the i18n check script fails the
 * build on that case rather than letting one silently overwrite the other.
 */
export function unflatten(flat: Record<string, string>): Nested {
  const out: Nested = {};
  for (const [key, value] of Object.entries(flat)) {
    if (key.startsWith("_")) continue;
    const parts = key.split(".");
    let node = out;
    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i]!;
      node[part] ??= {};
      node = node[part] as Nested;
    }
    node[parts[parts.length - 1]!] = value;
  }
  return out;
}
