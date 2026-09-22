import { describe, expect, it } from "vitest";

import { classifyIntent } from "./intent";

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
});
