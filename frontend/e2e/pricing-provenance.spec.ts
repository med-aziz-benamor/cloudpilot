import { expect, test } from "@playwright/test";

import { apiGet, login } from "./fixtures";

interface Catalog {
  total_count: number;
  api_verified_count: number;
  is_stale: boolean;
  rates: { sku: string; source: string; meter: string }[];
}

test.describe("pricing provenance", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("a rightsizing saving can be traced to a published rate", async ({ page }) => {
    await page.goto("/recommendations");
    await page.getByRole("button", { name: /^rightsizing$/i }).click();

    const card = page
      .locator("div")
      .filter({ hasText: /Underutilized resource/ })
      .first();
    const disclose = page
      .getByRole("button", { name: /how this saving was calculated/i })
      .first();

    // Collapsed by default — the feed is for scanning.
    await expect(page.getByText(/quoted as of/i)).toHaveCount(0);

    await disclose.click();

    // The rates, the hours, and the publisher behind each rate.
    await expect(page.getByText(/\$\d+\.\d{4}\/hr/).first()).toBeVisible();
    await expect(page.getByText(/730 h/).first()).toBeVisible();
    await expect(page.getByText(/Azure Retail API|AWS Price List|Published list price/).first()).toBeVisible();
    await expect(page.getByText(/quoted as of/i).first()).toBeVisible();
    await expect(card).toBeVisible();
  });

  test("the derivation multiplies out to the saving on the card", async ({ page }) => {
    // The whole point: the arithmetic shown must reconcile with the number the
    // platform is asking someone to act on.
    const recs = await apiGet<
      {
        agent: string;
        estimated_saving_usd: number | null;
        metadata: Record<string, unknown>;
      }[]
    >(page, "/api/v1/recommendations?agent=rightsizing");

    const rec = recs.find((r) => r.metadata?.pricing && r.estimated_saving_usd);
    expect(rec, "no rightsizing recommendation carries pricing provenance").toBeTruthy();

    const meta = rec!.metadata as {
      pricing: { current: { rate: number }; target: { rate: number } };
      node_count: number;
      billable_hours_per_month: number;
    };
    const derived =
      (meta.pricing.current.rate - meta.pricing.target.rate) *
      meta.billable_hours_per_month *
      meta.node_count;

    // Within a cent of the stored saving the UI displays.
    expect(Math.abs(derived - rec!.estimated_saving_usd!)).toBeLessThan(0.01);
  });

  test("a cost anomaly says it came from billed amounts, not the rate card", async ({
    page,
  }) => {
    await page.goto("/recommendations");
    await page.getByRole("button", { name: /^costagent$/i }).click();

    await page.getByRole("button", { name: /what triggered this/i }).first().click();
    await expect(page.getByText(/not from the rate card/i).first()).toBeVisible();
  });

  test("the rate card lists every SKU with its source", async ({ page }) => {
    const catalog = await apiGet<Catalog>(page, "/api/v1/pricing/catalog");

    await page.goto("/settings");
    await page.getByRole("tab", { name: /pricing/i }).click();

    await expect(page.getByRole("heading", { name: "Rate card" })).toBeVisible();
    // One row per rate, plus the header row.
    await expect(page.locator("tbody tr")).toHaveCount(catalog.total_count);

    // Every rate is attributed, and API-verified ones are distinguishable from
    // transcribed ones — the distinction is the reason the field exists.
    const verified = page.getByText("Azure Retail API");
    await expect(verified).toHaveCount(catalog.api_verified_count);
  });

  test("a transcribed rate cites the page it was read off", async ({ page }) => {
    // Every AWS list price once cited the S3 pricing page, EC2 rates included.
    const catalog = await apiGet<Catalog>(page, "/api/v1/pricing/catalog");
    const ec2 = catalog.rates.find((r) => r.sku === "m5.xlarge");
    expect(ec2?.meter).toContain("/ec2/");

    await page.goto("/settings");
    await page.getByRole("tab", { name: /pricing/i }).click();
    await expect(
      page.getByRole("row", { name: /m5\.xlarge/ }).getByText("aws.amazon.com/ec2/pricing"),
    ).toBeVisible();
  });

  test("a stale snapshot is called out rather than quietly used", async ({ page }) => {
    const catalog = await apiGet<Catalog>(page, "/api/v1/pricing/catalog");

    await page.goto("/settings");
    await page.getByRole("tab", { name: /pricing/i }).click();

    const warning = page.getByText(/snapshot is older than/i);
    if (catalog.is_stale) {
      await expect(warning).toBeVisible();
    } else {
      await expect(warning).toHaveCount(0);
    }
  });
});
