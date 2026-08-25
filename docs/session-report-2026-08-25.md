# Session report — 2026-08-25: demo-readiness hardening pass

A fix-and-polish pass to get CloudPilot genuinely demo-ready: security gaps and
correctness bugs surfaced by a fresh code-level audit, the one glaring test-coverage
hole (RBAC), and a portability fix — followed by a live browser walkthrough that
found four more bugs the audit and the unit-test suite had both missed. 17 commits
on `feat/pricing-grounded-simulator`, following the 36-day gap since the last commit
(20 July) that the [5 August status audit](session-report-2026-08-05.md) recorded.

Backend suite: **155 tests, all passing** (was 116). Frontend suite: **16 tests, all
passing** (was 0 meaningful component-level coverage — the prior single file covered
pure utility functions only). Ruff and mypy show no new issues in any file this pass
touched — verified line-by-line against the diff, not assumed.

---

## Summary

| # | Area | Outcome |
|---|------|---------|
| 1 | Auth: email lockout + timing side-channel | **Real gap, fixed.** Lockout counter was tracked but never enforced. |
| 2 | Security: X-Forwarded-For trust | **Real gap, fixed.** IP-based rate limiting was spoofable. |
| 3 | Security: JWT revocation fail-open | **Real gap, fixed.** Contradicted the module's own documented principle. |
| 4 | Security: refresh-token TOCTOU | **Real gap, fixed.** GET-then-DELETE replaced with atomic GETDEL. |
| 5 | Chat Advisor crash + wrong data | **Four bugs, all fixed** — two found only by opening the app in a browser. |
| 6 | CostAgent cross-account dedup | **Real bug, fixed.** |
| 7 | Azure pricing fetcher resilience | **Real bug, fixed.** Docstring promised tolerance that didn't exist. |
| 8 | ForecastAgent MTD/lookback | **Real bug, fixed.** Dormant today, would corrupt budget alerts on aged data. |
| 9 | Frontend: chat wrong-session bug | **Real bug, fixed and browser-verified.** |
| 10 | Frontend: five smaller UX/hygiene fixes | Budget UI honesty, dead store state, error boundary, confirm dialogs, `useAuth` selectors. |
| 11 | RBAC test coverage | **Was zero, now 12 mutation-verified tests.** |
| 12 | `make dev` portability | **Fixed.** Named volume replaces the hardcoded machine path. |

---

## 1–4. Security fixes

All four came from a code-level audit (three parallel reviews: security, AI/backend,
frontend) run before this session, then re-verified against the current tree before
any code changed.

- **`services/auth_service.py`** — `_record_failed_login` called `check_rate_limit`
  and discarded the return value; `LOGIN_MAX_ATTEMPTS_PER_EMAIL`/`LOGIN_LOCKOUT_SECONDS`
  existed but gated nothing. Now enforced: the 11th failed attempt against one email
  returns `423 Locked`. Separately, `verify_password` was only reached when a user
  existed, so response timing revealed which emails were registered — a fixed dummy
  hash closes that regardless of lockout state.
- **`api/deps.py`** — `client_ip()` trusted the first, client-suppliable value of
  `X-Forwarded-For`, letting an attacker reset the IP rate limiter on every request.
  Now prefers `X-Real-IP` (nginx sets this itself, unspoofable), falling back to the
  *last* `X-Forwarded-For` segment — the hop nginx appended — never the first.
- **`core/rate_limit.py`** — `is_revoked` returned `False` on a Redis error,
  contradicting the module's documented fail-closed principle; a Redis outage meant a
  revoked token stayed valid for the rest of its TTL. Now fails closed (`True`) —
  **an accepted availability tradeoff**: a Redis blip now costs a 401 storm instead of
  silently honoring revoked credentials, mitigated by both compose files already
  gating backend startup on Redis health.
- Same file — `consume_refresh_token` did GET-then-DELETE, a TOCTOU race letting one
  refresh token be consumed twice under concurrent calls. Replaced with a single
  atomic `GETDEL`.

## 5. The Cloud Advisor: four bugs, two only found by using the app

The original audit flagged one bug here — `LLMClient.generate()` could return `None`
and crash `_build_citations`'s regex — plus the unused, never-executed `TOOL_DEFINITIONS`
advertised to the LLM. Both fixed as planned.

Then the chat flow was driven in a real headless-Chromium browser (Playwright,
installed for this session — no project skill covered launching the app yet) to verify
the wrong-session fix below, and it **crashed on the very first message**. Three more
bugs surfaced, none of which a static read of the code or the existing test suite had
caught:

1. `citations_json`/`tool_calls_json` are nullable ORM columns — `NULL` for every user
   message, and for any assistant message with nothing to cite. The response schema's
   `default_factory=list` only fills in a field that's *absent*, not one that's
   explicitly `None`. Every chat session containing such a message **500'd on GET**.
2. `mock_data.py`'s seeded assistant messages never set `tool_calls_json` at all —
   stored `NULL` — so all 3 seeded demo conversations were broken by bug 1 out of the
   box, before any live message was ever sent.
3. The schema used `alias="citations_json"` to map the ORM attribute name. FastAPI
   serializes response models **by alias by default** — so once bug 1 was fixed, the
   API was still sending `citations_json`/`tool_calls_json` as the actual JSON keys.
   The frontend's `ChatMessage` type (correctly) reads `citations`/`tool_calls`, which
   were therefore `undefined` on every assistant reply — crashing `ChatBubble` (caught
   live by the new error boundary, see §10) the moment any session with a real answer
   rendered.

Fix: bug 1 closed with a `field_validator(mode="before")` coercing `None` → `[]`
(the general, correct fix — covers every current and future write path, not just the
ones patched); bug 2's write site now stores `[]`; bug 3 fixed by switching from
`alias` to `validation_alias`, which only affects input mapping, not output.

**This is the headline finding of the session**: three of these four bugs were
invisible to code review and to unit tests, and would have crashed the chat page
in front of the supervisor on the very first demo click. They surfaced only because
the app was actually driven in a browser — the exact gap the project's own docs
already flagged (`docs/session-report-2026-08-05.md`, item 5: "no frontend
e2e/visual test tooling").

## 6–8. Backend/AI correctness

- **`cost_agent.py`** — anomaly dedup key was `(service, date)`, no account. Two
  accounts with an anomaly in the same service on the same day collided; the second
  was silently dropped. Fixed both the in-run key and `_pending_anomaly_dates`, which
  independently reconstructed the same under-scoped key on later runs.
- **`pricing/sources.py`** — the module docstring promised Azure fetchers degrade
  gracefully on failure like the AWS fetcher does; none of the three actually had
  exception handling. One Azure hiccup aborted the whole `make pricing` run. Fixed by
  centralizing a try/except in `_azure_query`, which all three funnel through.
- **`forecast_agent.py`** — the MTD filter matched on month number only, no year;
  dormant for a new org, would silently pull in every past year sharing today's month
  once an org has >12 months of history. `_daily_totals` also had no date bound at
  all, contradicting its own "90+ days" docstring. Both fixed.

## 9–10. Frontend

- **The headline frontend bug**: `useSendMessage(activeId ?? "")` bound the mutation's
  target session at render time. Starting a new conversation created a session and
  called `setActiveId(...)`, but the same-tick `mutateAsync` call still used the
  mutation closed over the stale, empty `activeId` — the first message in any new
  chat posted to the wrong URL. Fixed by making the session id a per-call mutation
  argument instead of a hook parameter. **Verified in the browser via the Network
  tab**, not just the added regression test: the POST now targets the real,
  newly-created session UUID.
- Five smaller fixes: the Forecast budget controls are now honestly disabled instead
  of decorative; `cloud.store.ts`'s four dead fields removed and the Costs page now
  reads/writes the same `timeRange` Overview does (previously hardcoded to 30 days,
  disagreeing with the shared selector); a top-level `ErrorBoundary` added (its first
  real catch was the chat crash above, before the underlying bug was fixed); destructive
  deletes (cloud account, chat session) now confirm before firing; `useAuth()` now
  selects individual fields instead of subscribing to the whole store, fixing an effect
  that was tearing down and re-adding the logout listener on every auth state change.

## 11. RBAC test coverage

Zero coverage before this session, despite `core/rbac.py` calling itself "the FIRST
layer of authorization" in its own docstring, sitting next to a tenant-isolation suite
with 18 mutation-verified tests. `backend/tests/test_rbac.py` introduces the suite's
first HTTP-level test client (`httpx.AsyncClient` over `ASGITransport`, no new
dependency) rather than only unit-testing `role_has_permission` — a unit test can't
catch a route that forgot to apply the guard at all.

12 tests: one deny + one allow per actually-wired permission (`chat.use`,
`recommendations.write`, `cloud_accounts.manage` — admin-only, `audit.read`,
`agents.trigger`). **`users.manage` gates no endpoint anywhere in the codebase**
(confirmed by grep) — covered as a direct unit test against `role_has_permission`
instead, called out explicitly so it doesn't read as an oversight.

Mutation-verified the same way the July tenant-isolation work was: temporarily
inverted `role_has_permission`'s `role in allowed` check, confirmed all 12 tests went
red, reverted. Also had to reset `rate_limit`'s module-level Redis client per test —
it's a singleton bound to whichever event loop first created it, and pytest-asyncio
gives each test its own loop; this only became visible once `is_revoked` started
failing closed (§3), since the old fail-open behavior masked it.

## 12. Portability

`docker-compose.yml`'s `ollama` service mounted `/Volumes/AzizBNA SSD/ollama/models`
directly — hardcoded to the original dev machine, unquoted space and all. Replaced
with a named `ollama_models` volume; removed the now-resolved "known issue" callout
from `docs/development.md` and the README.

---

## New findings from this pass, not in any prior audit

1. **The three chat-serialization bugs in §5** — a static read of `schemas/chat.py`
   would not obviously catch the `alias` vs `validation_alias` distinction; it only
   surfaced by inspecting the raw JSON response and comparing it against what the
   frontend types expect.
2. **The mock-data seeder independently reproduces the same NULL-handling bug** its
   own live-write-path had — two different code paths, same class of mistake, meaning
   a partial fix (chat_service.py alone) would have left every seeded demo
   conversation broken.
3. **`rate_limit`'s module-level Redis client is a bare singleton with no event-loop
   awareness** — harmless while `is_revoked` failed open (an error was swallowed
   either way), but became a hard test failure the moment it started failing closed.
   Worth knowing if any other test file starts exercising real Redis-backed code
   paths across multiple test functions.

## Still open (not attempted this pass — explicitly out of scope)

- Live multi-cloud billing/metrics adapters — `NotImplementedError` by design.
- Dashboard aggregate caching — `CACHE_DASHBOARD_TTL` still defined, unused.
- RAG corpus — still 7 chunks, unchanged.
- Budget-setting write API — the frontend control is now honest about not having one
  (§10), but there is still no `PATCH` endpoint for `organizations.monthly_budget_usd`.
- `metric_samples` still has no `organization_id` — single-layer isolation via
  `resource_id`, unchanged from the July hardening pass.
- Mypy: 80 pre-existing errors across 29 files, none introduced or worsened by this
  pass (verified by cross-referencing every flagged line against this session's diffs).
  Real, but a separate, larger effort than a demo-readiness pass warrants.

## How to reproduce this session's verification

```bash
docker compose up -d postgres redis
docker compose run --rm --no-deps backend alembic upgrade head
docker compose run --rm --no-deps \
  -e CLOUDPILOT_TEST_DB="postgresql+asyncpg://cp:cp@postgres:5432/cloudpilot_test" \
  backend pytest -p no:warnings -q          # 155 passed

cd frontend && pnpm exec vitest run          # 16 passed
pnpm run typecheck && pnpm run lint          # clean

# Live browser smoke test (the one that found §5's bugs):
npx playwright install chromium
# then drive login -> chat -> forecast -> settings -> costs against
# http://localhost:5173 with a real Chromium instance, not just curl.

make seed   # re-seed after any code change touching agent output or chat
```
