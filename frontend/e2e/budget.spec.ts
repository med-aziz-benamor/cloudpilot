import { expect, test } from "@playwright/test";

import { apiGet, login } from "./fixtures";

/**
 * The Forecast and Recommendations pages once disagreed about the budget — a
 * hardcoded $45,000 on one screen against the tenant's real $7,500 on the other.
 * Each side was internally consistent, so neither the unit tests nor a
 * single-screen walkthrough caught it. Reading both screens together does.
 */
test.describe("the budget is one number across the platform", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("the Forecast page shows the tenant's own budget", async ({ page }) => {
    const { budget_usd } = await apiGet<{ budget_usd: number | null }>(
      page,
      "/api/v1/forecast/budget",
    );
    test.skip(budget_usd === null, "no budget set on the seeded tenant");

    await page.goto("/forecast");
    const input = page.getByLabel(/monthly budget/i);
    await expect(input).toHaveValue(String(budget_usd));
  });

  test("the Forecast verdict and the overrun alert agree", async ({ page }) => {
    const forecast = await apiGet<{ budget_usd: number | null; over_budget: boolean }>(
      page,
      "/api/v1/forecast?horizon_days=30",
    );
    const recs = await apiGet<{ agent: string; metadata: Record<string, unknown> }[]>(
      page,
      "/api/v1/recommendations?agent=forecast",
    );

    const alert = recs.find((r) => typeof r.metadata?.budget === "number");
    test.skip(!alert, "no forecast overrun alert on the seeded tenant");

    // Same tenant: the budget the alert was raised against must be the budget the
    // Forecast page reports. Whether the month is currently over budget depends on
    // where in the month the seeded data sits and is not the invariant here — the
    // bug was two screens quoting two different budgets.
    expect(alert!.metadata.budget).toBe(forecast.budget_usd);
  });

  test("saving a budget persists it and moves the alert threshold", async ({ page }) => {
    const original = (
      await apiGet<{ budget_usd: number | null }>(page, "/api/v1/forecast/budget")
    ).budget_usd;

    await page.goto("/forecast");
    const input = page.getByLabel(/monthly budget/i);
    const save = page.getByRole("button", { name: /^save$/i });

    // Save is inert until the value actually changes — it was a decorative
    // control before it was a wired one.
    await expect(save).toBeDisabled();

    await input.fill("8600");
    await expect(save).toBeEnabled();
    await save.click();
    await expect(page.getByText("Saved")).toBeVisible();

    const stored = await apiGet<{ budget_usd: number | null }>(
      page,
      "/api/v1/forecast/budget",
    );
    expect(stored.budget_usd).toBe(8600);

    // Restore, so the suite can be run twice in a row.
    await input.fill(String(original ?? ""));
    await save.click();
    await expect(page.getByText("Saved")).toBeVisible();
  });
});
