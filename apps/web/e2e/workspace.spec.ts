import { expect, test, type Page } from "@playwright/test";
import { fileURLToPath } from "node:url";

/**
 * These drive the real stack: Next.js in front, FastAPI behind, Postgres and
 * PostGIS underneath. They are skipped when the API is not reachable rather
 * than failing, so a frontend-only checkout still runs its unit tests.
 */

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const GEOTIFF = fileURLToPath(
  new URL("../../../infra/fixtures/sample-scene.tif", import.meta.url),
);
const PNG = fileURLToPath(
  new URL("../../../infra/fixtures/sample-scene.png", import.meta.url),
);

test.beforeAll(async ({ request }) => {
  try {
    const health = await request.get(`${API}/api/v1/health`, { timeout: 5000 });
    test.skip(!health.ok(), "analysis API is not reachable");
  } catch {
    test.skip(true, "analysis API is not reachable");
  }
});

async function upload(page: Page, locale: string, file: string) {
  await page.goto(`/${locale}/workspace`);
  const chooser = page.waitForEvent("filechooser");
  await page.locator("aside").first().getByRole("button").first().click();
  await (await chooser).setFiles(file);
  // Wait on the filename rather than a label: every label is localised, and
  // this helper runs against all four locales.
  const name = file.split(/[\\/]/).pop()!;
  await expect(page.getByText(name).first()).toBeVisible({ timeout: 20_000 });
  // The band panel only appears once the server has registered the asset.
  await expect(page.locator("aside").first().locator("select")).toBeVisible({
    timeout: 20_000,
  });
}

async function ask(page: Page, question: string) {
  await page.locator("textarea").fill(question);
  await page.getByRole("button", { name: "Run analysis" }).click();
}

test("measures a georeferenced raster and reports area on the ground", async ({
  page,
}) => {
  await upload(page, "en", GEOTIFF);

  // The server read a real coordinate system out of the file.
  await expect(page.getByText("EPSG:32645").first()).toBeVisible();

  // Band roles are never inferred, so nothing is computable until a preset
  // is applied.
  await expect(page.getByText("NDVI needs nir, red.").first()).toBeVisible();
  await page.locator("aside").first().locator("select").selectOption("cartosat-2s-mx");

  // With bands mapped, NDVI and NDWI unlock but LSWI stays refused — this
  // sensor has no SWIR band and one is never substituted.
  await expect(page.getByText("LSWI needs swir1.").first()).toBeVisible();

  await ask(page, "How much of this area is under water?");

  await expect(page.getByRole("heading", { name: "Answer" })).toBeVisible({
    timeout: 60_000,
  });
  // 4320 pixels of 100 m2 -> 43.2 ha, checkable by hand against the fixture.
  await expect(page.getByText("43.19 ha").first()).toBeVisible();
  await expect(page.getByText(/Measured from NDWI/).first()).toBeVisible();
});

test("holds an answer for review when nothing could be measured", async ({
  page,
}) => {
  // A PNG carries three visible bands and no coordinate system, so no index
  // is computable. The run must not present a confident answer anyway.
  await upload(page, "en", PNG);
  await expect(page.getByText("none (not georeferenced)").first()).toBeVisible();

  await ask(page, "How much of this area is under water?");

  await expect(page.getByRole("heading", { name: "Answer" })).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByText("Sent for expert review").first()).toBeVisible();
});

test("runs all eight steps and records which of them measured anything", async ({
  page,
}) => {
  await upload(page, "en", GEOTIFF);
  await page.locator("aside").first().locator("select").selectOption("cartosat-2s-mx");
  await ask(page, "Describe the land cover in this image.");

  await expect(page.getByRole("heading", { name: "Answer" })).toBeVisible({
    timeout: 60_000,
  });

  const steps = page.locator("ol").first().locator("li");
  await expect(steps).toHaveCount(8);

  // Fixture steps are labelled as such; measured ones are not.
  await expect(page.getByText("Placeholder").first()).toBeVisible();
  await expect(page.getByText("Measurements computed").first()).toBeVisible();
});

test("routes a Tamil water question to NDWI rather than NDVI", async ({
  page,
}) => {
  // Regression: the server's keyword list once missed the inflected Tamil
  // form, and a water question was answered with a vegetation index.
  await upload(page, "ta", GEOTIFF);
  await page.locator("aside").first().locator("select").selectOption("cartosat-2s-mx");

  await page.locator("textarea").fill("இந்தப் பகுதியில் எவ்வளவு நீரில் மூழ்கியுள்ளது?");
  await page.getByRole("button", { name: "பகுப்பாய்வை இயக்கு" }).click();

  await expect(page.getByText(/NDWI/).first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/· water/).first()).toBeVisible();
});

test("offers the trace and layers as real downloads", async ({ page }) => {
  await upload(page, "en", GEOTIFF);
  await page.locator("aside").first().locator("select").selectOption("cartosat-2s-mx");
  await ask(page, "Describe the land cover in this image.");

  await expect(page.getByRole("heading", { name: "Answer" })).toBeVisible({
    timeout: 60_000,
  });

  // The identifier must be real; a broken stream once rendered these as
  // /jobs/undefined/trace.
  const trace = page.getByRole("link", { name: /Download trace/ });
  await expect(trace).toHaveAttribute("href", /\/jobs\/[0-9a-f-]{36}\/trace$/);

  const geojson = page.getByRole("link", { name: /Download layers/ });
  await expect(geojson).toHaveAttribute(
    "href",
    /\/jobs\/[0-9a-f-]{36}\/result\.geojson$/,
  );
});
