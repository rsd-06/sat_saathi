#!/usr/bin/env node
/**
 * Fails if any locale is missing a key, carries an extra one, leaves an ICU
 * placeholder behind, or introduces a key that is also the prefix of another
 * (which would break the flat->nested expansion the web app does at load).
 */
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const messagesDir = join(here, "messages");
const BASE = "en";

const locales = readdirSync(messagesDir)
  .filter((f) => f.endsWith(".json") && !f.endsWith(".review.json"))
  .map((f) => f.replace(/\.json$/, ""));

const load = (loc) =>
  JSON.parse(readFileSync(join(messagesDir, `${loc}.json`), "utf8"));

const base = load(BASE);
const baseKeys = Object.keys(base).filter((k) => !k.startsWith("_"));
const problems = [];

// A key must never also be the prefix of another key.
const keySet = new Set(baseKeys);
for (const key of baseKeys) {
  const parts = key.split(".");
  for (let i = 1; i < parts.length; i++) {
    const prefix = parts.slice(0, i).join(".");
    if (keySet.has(prefix)) {
      problems.push(
        `${BASE}: "${prefix}" is both a value and a parent of "${key}" — rename one`,
      );
    }
  }
}

/**
 * Real ICU placeholders look like {count} or {count, plural, ...} — the name is
 * immediately followed by "," or "}". A plural branch body such as
 * "{Nothing is waiting}" is prose, not a placeholder, so it must not match.
 */
const placeholders = (s) => [
  ...new Set(
    [...String(s).matchAll(/\{\s*(\w+)\s*[,}]/g)].map((m) => m[1]).sort(),
  ),
];

for (const locale of locales) {
  if (locale === BASE) continue;
  const msgs = load(locale);
  const keys = Object.keys(msgs).filter((k) => !k.startsWith("_"));

  for (const key of baseKeys) {
    if (!(key in msgs)) problems.push(`${locale}: missing "${key}"`);
  }
  for (const key of keys) {
    if (!keySet.has(key)) problems.push(`${locale}: unknown key "${key}"`);
  }
  for (const key of baseKeys) {
    if (!(key in msgs)) continue;
    const a = placeholders(base[key]).join(",");
    const b = placeholders(msgs[key]).join(",");
    if (a !== b) {
      problems.push(
        `${locale}: "${key}" placeholders differ (${BASE}: {${a}} vs ${locale}: {${b}})`,
      );
    }
  }
}

if (problems.length) {
  console.error(`i18n check failed with ${problems.length} problem(s):`);
  for (const p of problems) console.error(`  ${p}`);
  process.exit(1);
}

console.log(
  `i18n check passed: ${baseKeys.length} keys x ${locales.length} locales (${locales.join(", ")})`,
);
