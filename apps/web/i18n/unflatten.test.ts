import { describe, expect, it } from "vitest";

import en from "@satsaathi/i18n/messages/en.json";
import ta from "@satsaathi/i18n/messages/ta.json";
import { unflatten, type Nested } from "./unflatten";

describe("unflatten", () => {
  it("expands dotted keys into nested objects", () => {
    expect(unflatten({ "a.b.c": "x", "a.d": "y" })).toEqual({
      a: { b: { c: "x" }, d: "y" },
    });
  });

  it("drops metadata keys", () => {
    expect(unflatten({ _comment: "ignore me", "a.b": "keep" })).toEqual({
      a: { b: "keep" },
    });
  });

  it("keeps ICU plural syntax intact", () => {
    const src = "{count, plural, =0 {none} one {# item} other {# items}}";
    const out = unflatten({ "x.y": src }) as { x: { y: string } };
    expect(out.x.y).toBe(src);
  });

  it("resolves a real catalog key the UI depends on", () => {
    const messages = unflatten(en as Record<string, string>) as Nested;
    const landing = messages.landing as Nested;
    const hero = landing.hero as Nested;
    expect(hero.headline).toBe("Ask the satellite, in your language.");
  });

  it("produces the same shape for every locale", () => {
    const shape = (n: Nested): string[] =>
      Object.entries(n)
        .flatMap(([k, v]) =>
          typeof v === "string" ? [k] : shape(v).map((s) => `${k}.${s}`),
        )
        .sort();

    expect(shape(unflatten(ta as Record<string, string>))).toEqual(
      shape(unflatten(en as Record<string, string>)),
    );
  });
});
