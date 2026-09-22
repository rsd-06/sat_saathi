import { test } from "@playwright/test";
import { fileURLToPath } from "node:url";

/**
 * Not assertions — this file exists so a human can look at the result.
 * Run with: pnpm e2e shots
 */

const FIXTURE = fileURLToPath(
  new URL("../../../infra/fixtures/sample-scene.png", import.meta.url),
);
const OUT = "D:/Projects/.playwright-out";

test.use({ viewport: { width: 1600, height: 1100 } });

test("capture the fixed Tamil run", async ({ page }) => {
  await page.goto("/en/workspace");
  await page.setInputFiles('input[type="file"]', FIXTURE);
  await page.locator("textarea").fill("என்பதை தமிழில் பின்வருமாறு கூறலாம்");
  await page.getByRole("button", { name: "Run analysis" }).click();
  await page.getByRole("heading", { name: "Answer" }).waitFor({ timeout: 30000 });
  await page.getByText("Question understood").click();
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/fixed-tamil.png`, fullPage: true });
});

test("capture a vegetation run", async ({ page }) => {
  await page.goto("/en/workspace");
  await page.setInputFiles('input[type="file"]', FIXTURE);
  await page.locator("textarea").fill("How much of this area is crop land?");
  await page.getByRole("button", { name: "Run analysis" }).click();
  await page.getByRole("heading", { name: "Answer" }).waitFor({ timeout: 30000 });
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/vegetation.png`, fullPage: true });
});
