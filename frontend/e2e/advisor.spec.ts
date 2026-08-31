import { expect, test } from "@playwright/test";

import { login } from "./fixtures";

/**
 * With no model reachable, the Cloud Advisor must say so. A canned paragraph
 * dressed up as a grounded answer — citation chip and all — is worse than an
 * honest error, and on this hardware an unreachable model is the normal case:
 * Docker passes no GPU through on Apple Silicon, so Ollama runs on the host or
 * not at all.
 *
 * If Ollama *is* running, this becomes a real generation and is skipped rather
 * than left to time out.
 */
test.describe("Cloud Advisor", () => {
  test("says the model is unavailable instead of inventing an answer", async ({
    page,
  }) => {
    // Reachable is not the same as usable: an Ollama with nothing pulled produces
    // the fallback just as a stopped one does, and that is the path under test.
    const modelReady = await page.request
      .get("http://localhost:11434/api/tags", { timeout: 2_000 })
      .then(async (r) => {
        if (!r.ok()) return false;
        const { models } = (await r.json()) as { models?: unknown[] };
        return (models?.length ?? 0) > 0;
      })
      .catch(() => false);
    test.skip(modelReady, "a model is available; this spec covers the offline path");

    await login(page);
    await page.goto("/chat");

    await page
      .getByRole("textbox")
      .first()
      .fill("How do I reduce spend on idle VMs?");
    await page.keyboard.press("Enter");

    await expect(
      page.getByText(/language model is unavailable/i),
    ).toBeVisible({ timeout: 60_000 });

    // And it must not echo the assembled prompt back into the chat window.
    await expect(page.getByText(/USER QUESTION:/)).toHaveCount(0);
    await expect(page.getByText(/CONTEXT DOCUMENTS/i)).toHaveCount(0);
  });
});
