import { expect, test } from "@playwright/test";

import { DEMO, login } from "./fixtures";

test.describe("authentication", () => {
  test("an unauthenticated visitor is sent to the login page", async ({ page }) => {
    await page.goto("/recommendations");
    await expect(page).toHaveURL(/\/login/);
  });

  test("a wrong password is refused, and does not navigate", async ({ page }) => {
    await page.goto("/login");
    await page.getByPlaceholder("you@company.com").fill(DEMO.email);
    await page.getByPlaceholder("••••••••").fill("not-the-password");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page.getByText(/invalid|incorrect|credential/i)).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test("the demo tenant signs in and lands on the cockpit", async ({ page }) => {
    await login(page);
    await expect(page.getByRole("link", { name: /recommendations/i })).toBeVisible();
  });

  test("a deep link survives the session bootstrap", async ({ page }) => {
    // Restoring a session used to race with itself. Refresh tokens are single-use,
    // so the losing call reported the user as signed out, the guard redirected to
    // /login, and the login page then sent the now-authenticated user to the
    // Overview — silently dropping whichever page had been asked for.
    await login(page);
    await page.goto("/forecast");

    await expect(page).toHaveURL(/\/forecast$/);
    await expect(page.getByRole("heading", { name: /forecast/i }).first()).toBeVisible();
  });

  test("the access token is never written to browser storage", async ({ page }) => {
    // The security model puts it in memory only; a regression here would be silent.
    await login(page);
    const stored = await page.evaluate(() => ({
      local: Object.entries(window.localStorage),
      session: Object.entries(window.sessionStorage),
    }));
    const all = JSON.stringify(stored).toLowerCase();
    expect(all).not.toContain("bearer");
    expect(all).not.toMatch(/eyj[a-z0-9_-]{10,}/i); // a JWT's base64 header
  });
});
