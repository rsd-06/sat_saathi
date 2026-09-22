import { expect, test } from "@playwright/test";
import { fileURLToPath } from "node:url";

const FIXTURE = fileURLToPath(
  new URL("../../../infra/fixtures/sample-scene.png", import.meta.url),
);

async function uploadAndAsk(
  page: import("@playwright/test").Page,
  locale: string,
  question: string,
) {
  await page.goto(`/${locale}/workspace`);
  await page.setInputFiles('input[type="file"]', FIXTURE);
  await expect(page.getByText("sample-scene.png").first()).toBeVisible();
  await page.locator("textarea").fill(question);
  await page.getByRole("button", { name: /Run analysis|चलाइए|இயக்கு|চালান/ }).click();
}

test("runs the whole pipeline on an uploaded image and answers", async ({
  page,
}) => {
  await uploadAndAsk(page, "en", "How much of this area is vegetated?");

  // All eight steps settle, and the answer appears.
  await expect(page.getByRole("heading", { name: "Answer" })).toBeVisible({
    timeout: 30_000,
  });

  const trace = page.locator("ol").first();
  await expect(trace.locator("li")).toHaveCount(8);

  // The measurement step reports a real figure taken from the fixture.
  await expect(page.getByText(/Vegetated pixels/).first()).toBeVisible();
  await expect(page.getByText(/ExG >/).first()).toBeVisible();
});

test("refuses NDVI on an RGB file instead of approximating it", async ({
  page,
}) => {
  await page.goto("/en/workspace");
  // The refusal is stated before a run, not only afterwards.
  await expect(page.getByText("NDVI needs a red and a near-infrared band.")).toBeVisible();
  const ndvi = page.getByText("NDVI", { exact: true }).first();
  await expect(ndvi).toHaveCSS("text-decoration-line", /line-through/);
});

test("does not route an unrelated Tamil sentence to change detection", async ({
  page,
}) => {
  // Regression: "பின்" (after) used to match inside "பின்வருமாறு" (as
  // follows), classifying this as a change question and holding it for review.
  await uploadAndAsk(page, "en", "என்பதை தமிழில் பின்வருமாறு கூறலாம்");

  await expect(page.getByRole("heading", { name: "Answer" })).toBeVisible({
    timeout: 30_000,
  });

  await page.getByText("Question understood").click();
  const understand = page.locator("li", { hasText: "Question understood" });
  await expect(understand).toContainText("intent=land_cover");
  await expect(understand).not.toContainText("intent=change");
});

test("routes a genuine Tamil change question to change detection", async ({
  page,
}) => {
  await uploadAndAsk(page, "ta", "இரு தேதிகளுக்கு இடையே என்ன மாற்றம்?");
  await expect(page.locator("ol").first().locator("li")).toHaveCount(8);
  await page.getByText("கேள்வி புரிந்துகொள்ளப்பட்டது").click();
  await expect(
    page.locator("li", { hasText: "கேள்வி புரிந்துகொள்ளப்பட்டது" }),
  ).toContainText("intent=change");
});
