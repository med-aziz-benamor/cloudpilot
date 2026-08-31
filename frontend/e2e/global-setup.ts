import { API_URL } from "./fixtures";

/**
 * Refuse to run against a stack that is not up.
 *
 * Without this the whole suite fails on obscure selector timeouts when the real
 * cause is that nobody started the API — the failure mode that makes people stop
 * trusting an e2e suite.
 */
export default async function globalSetup(): Promise<void> {
  try {
    const res = await fetch(`${API_URL}/health`, {
      signal: AbortSignal.timeout(5_000),
    });
    if (!res.ok) throw new Error(`health returned ${res.status}`);
  } catch (err) {
    throw new Error(
      `The CloudPilot API is not reachable at ${API_URL} (${String(err)}).\n\n` +
        "Start it first:\n" +
        "  make up && make migrate && make seed\n\n" +
        "The Cloud Advisor spec expects Ollama to be DOWN and asserts the honest\n" +
        '"model unavailable" notice, so there is no need to start it.',
    );
  }
}
