import { expect, test } from "@playwright/test";

import { apiGet, login } from "./fixtures";

/**
 * The cost aggregates are served from a Redis cache, and the cache is the part
 * that broke: `/costs/breakdown` cached Pydantic models through
 * `json.dumps(default=str)`, which stored their *repr*. The first request
 * computed fresh and worked; every request for the next five minutes hit the
 * cache, tried to validate a list of strings, and returned 500.
 *
 * So a single visit proves nothing here — these specs load twice on purpose.
 */
test.describe("cost aggregates survive their own cache", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("the Costs page renders identically on a reload", async ({ page }) => {
    // The donut's legend is rendered straight from /costs/breakdown, so its
    // percentages are the visible proof the endpoint answered with real numbers.
    // Anchored on both ends so it matches only the legend's bare "59%" spans.
    const legend = () => page.getByText(/^\d+(\.\d+)?%$/);

    await page.goto("/costs");
    await expect(legend().first()).toBeVisible();
    const first = await legend().allInnerTexts();
    expect(first.length, "no provider shares rendered").toBeGreaterThan(0);

    await page.reload();
    await expect(legend().first()).toBeVisible();
    expect(await legend().allInnerTexts()).toEqual(first);
  });

  test("every cached endpoint answers twice", async ({ page }) => {
    // Cold, then warm — the warm path is the one that used to 500.
    for (const path of [
      "/api/v1/costs/summary",
      "/api/v1/costs/breakdown",
      "/api/v1/costs/timeseries?period_days=90",
    ]) {
      const cold = await apiGet<Record<string, unknown>>(page, path);
      const warm = await apiGet<Record<string, unknown>>(page, path);
      // A cache hit must reproduce the computed answer exactly, not merely
      // return 200 — a wrong-shaped hit is the failure mode being guarded.
      expect(warm, `${path} differs between cold and warm`).toEqual(cold);
    }
  });

  test("the breakdown carries real provider totals, not stringified models", async ({
    page,
  }) => {
    const body = await apiGet<{
      by_provider: { provider: string; cost_usd: number }[];
    }>(page, "/api/v1/costs/breakdown");

    expect(body.by_provider.length).toBeGreaterThan(0);
    for (const p of body.by_provider) {
      expect(typeof p.provider).toBe("string");
      expect(typeof p.cost_usd).toBe("number");
    }
  });
});
