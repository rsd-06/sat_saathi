import { describe, expect, it } from "vitest";

import { classifyIntent, classifyIntentDetailed } from "./intent";

describe("classifyIntent", () => {
  it("recognises water questions in English", () => {
    expect(classifyIntent("How much of this area is under water?")).toBe(
      "water_extent",
    );
    expect(classifyIntent("Show me the flooded ground")).toBe("water_extent");
  });

  it("recognises questions in Hindi, Tamil and Bangla", () => {
    expect(classifyIntent("इस क्षेत्र का कितना हिस्सा पानी में है?")).toBe(
      "water_extent",
    );
    expect(classifyIntent("இந்தப் படத்தில் பயிர் எப்படி உள்ளது?")).toBe(
      "vegetation",
    );
    expect(classifyIntent("এই দুই তারিখের মধ্যে কী পরিবর্তন হয়েছে?")).toBe(
      "change",
    );
  });

  it("recognises vegetation and built-up questions", () => {
    expect(classifyIntent("How much paddy was lost?")).toBe("vegetation");
    expect(classifyIntent("Identify built-up regions")).toBe("built_up");
  });

  it("falls back to land cover when nothing matches", () => {
    expect(classifyIntent("Describe this image")).toBe("land_cover");
    expect(classifyIntent("")).toBe("land_cover");
  });

  it("is case insensitive", () => {
    expect(classifyIntent("WHERE IS THE FLOODING")).toBe("water_extent");
  });

  describe("does not match keywords buried inside unrelated words", () => {
    it("ignores 'பின்' inside 'பின்வருமாறு' (as follows)", () => {
      // Reported from a demo: this Tamil sentence is not a change question,
      // but "பின்" (after) is a substring of "பின்வருமாறு" (as follows), which
      // routed it to change detection and held the answer for review.
      expect(classifyIntent("என்பதை தமிழில் பின்வருமாறு கூறலாம்")).toBe(
        "land_cover",
      );
    });

    it("ignores 'after' inside 'afternoon'", () => {
      expect(classifyIntent("Describe this afternoon scene")).toBe(
        "land_cover",
      );
    });

    it("still classifies a genuine Tamil change question", () => {
      expect(classifyIntent("இரு தேதிகளுக்கு இடையே என்ன மாற்றம்?")).toBe(
        "change",
      );
    });

    it("still classifies a genuine English before/after question", () => {
      expect(classifyIntent("Compare the before and after images")).toBe(
        "change",
      );
    });
  });

  it("reports which keywords drove the decision", () => {
    const r = classifyIntentDetailed("How much of this area is flooded?");
    expect(r.intent).toBe("water_extent");
    expect(r.matched).toContain("flood");
    expect(r.score).toBeGreaterThan(0);
  });

  it("reports no evidence when nothing matched", () => {
    const r = classifyIntentDetailed("என்பதை தமிழில் பின்வருமாறு கூறலாம்");
    expect(r.matched).toEqual([]);
    expect(r.score).toBe(0);
    expect(r.intent).toBe("land_cover");
  });
});
