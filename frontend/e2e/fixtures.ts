import { expect, type Page } from "@playwright/test";

export const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";

/** The seeded demo tenant (Acme Corp), created by `make seed`. */
export const DEMO = { email: "demo@cloudpilot.dev", password: "demo1234" };

/** Sign in through the real login form and land on the Overview. */
export async function login(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByRole("button", { name: /try demo/i }).click();
  await expect(page).toHaveURL(/\/$/);
}

/**
 * Read a value straight from the API, to check a screen against its own source.
 *
 * This authenticates separately rather than reusing the app's token: per the
 * security model the access token lives in memory only and is deliberately not
 * reachable from page scripts, which is a property worth keeping true.
 *
 * Several of these specs exist because two screens disagreed while each was
 * internally consistent; comparing a screen against the API it reads is what
 * catches that class of bug.
 */
export async function apiGet<T>(page: Page, path: string): Promise<T> {
  const auth = await page.request.post(`${API_URL}/api/v1/auth/login`, {
    data: DEMO,
  });
  expect(auth.ok(), "API login failed — is the demo tenant seeded?").toBeTruthy();
  const { access_token } = (await auth.json()) as { access_token: string };

  const res = await page.request.get(`${API_URL}${path}`, {
    headers: { Authorization: `Bearer ${access_token}` },
  });
  expect(res.ok(), `GET ${path} returned ${res.status()}`).toBeTruthy();
  return (await res.json()) as T;
}
