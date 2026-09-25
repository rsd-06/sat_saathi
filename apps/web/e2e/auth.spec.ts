import { expect, test } from "@playwright/test";

/**
 * Signing in and out, including the ways a session goes stale.
 *
 * These register throwaway accounts, so run them against the Docker database,
 * never a hosted one.
 */

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const PASSWORD = "an-e2e-passphrase-long-enough";

test.beforeAll(async ({ request }) => {
  try {
    const health = await request.get(`${API}/api/v1/health`, { timeout: 5000 });
    test.skip(!health.ok(), "analysis API is not reachable");
  } catch {
    test.skip(true, "analysis API is not reachable");
  }
});

function newEmail() {
  return `auth-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@e2e.example.gov.in`;
}

test("signing up lands on the dashboard, signed in", async ({ page }) => {
  await page.goto("/en/sign-up");
  await page.fill("#full_name", "E2E Surveyor");
  await page.fill("#email", newEmail());
  await page.fill("#password", PASSWORD);
  await page.click('button[type="submit"]');

  await page.waitForURL("**/en/dashboard");
  await expect(page.locator("header").first()).toContainText("E2E Surveyor");
});

test("a stale session cookie never locks anyone out of signing in", async ({
  page,
  context,
  baseURL,
}) => {
  /**
   * Regression: the guard trusted a cookie merely existing. A cookie the API
   * no longer honoured — left by a database reset, or by moving to a new
   * database — bounced every visit to /sign-in onto a dashboard that could
   * not load, so the form was unreachable.
   */
  await context.addCookies([
    { name: "satsaathi_session", value: "not-a-session-anymore", url: baseURL! },
  ]);

  await page.goto("/en/sign-in");
  await expect(page.locator("#email")).toBeVisible();

  // A protected page clears the dead cookie and says why.
  await page.goto("/en/dashboard");
  await page.waitForURL("**/en/sign-in?error=session_expired");
  await expect(page.getByRole("alert").first()).toContainText(/session ended/i);
  const cookies = await context.cookies(baseURL);
  expect(cookies.find((c) => c.name === "satsaathi_session")?.value ?? "").toBe("");
});

test("signing out ends the session", async ({ page }) => {
  const email = newEmail();
  await page.request.post("/api/auth/register", {
    data: { email, password: PASSWORD, full_name: "Leaving Soon" },
  });
  await page.goto("/en/dashboard");
  await expect(page.locator("header").first()).toContainText("Leaving Soon");

  await page.locator("header button[aria-haspopup='menu']").click();
  await page.getByRole("menuitem").click();
  await page.waitForURL(/\/en$/);

  await page.goto("/en/dashboard");
  await page.waitForURL("**/en/sign-in**");
});

test("a wrong password says so, and stays on the form", async ({ page }) => {
  const email = newEmail();
  await page.request.post("/api/auth/register", {
    data: { email, password: PASSWORD, full_name: "Right Password" },
  });
  await page.context().clearCookies();

  await page.goto("/en/sign-in");
  await page.fill("#email", email);
  await page.fill("#password", "definitely-not-the-password");
  await page.click('button[type="submit"]');

  await expect(page.getByRole("alert").first()).toContainText(/not right/i);
  expect(page.url()).toContain("/en/sign-in");
});
