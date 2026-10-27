# Session report — 2026-08-31: surfacing provenance, and committing the browser suite

Follow-up to [`session-report-2026-08-25b.md`](session-report-2026-08-25b.md), which
closed the gaps carried forward from the demo-readiness pass. This session works
through the items that report left open, plus four defects found along the way that
nothing had flagged — three of which only became visible *because* the provenance
work put the data on screen.

Backend suite: **199 tests, all passing** (was 189). `ruff check .` clean, mypy
reports zero issues across all 87 source files. Frontend: **36 unit tests** (was 16),
typecheck clean, and a new **15-test Playwright suite** passing against a live stack.

---

## Summary

| # | Carried-forward item | Outcome |
|---|---|---|
| 1 | Pricing provenance tracked but never surfaced | **Done** — on every recommendation, and as a rate card |
| 2 | No committed frontend e2e suite | **Done** — 15 Playwright specs, `make e2e` |
| — | *(new)* The API never sent `metadata` under the name anything read | **Fixed** |
| — | *(new)* Every transcribed rate cited the wrong pricing page | **Fixed** |
| — | *(new)* The session bootstrap raced itself and lost deep links | **Fixed** |
| — | *(new)* CI never ran the frontend unit tests | **Fixed** |
| — | Live multi-cloud billing/metrics | **Still not attempted** — see the end |

---

## 1. Provenance, on screen

The backend has tracked where every rate came from since the pricing work: a
`PriceSource` per rate, an as-of date per snapshot, and `pricing_provenance()`
attached to each rightsizing recommendation. All of it stopped at the database. A
saving a reviewer cannot trace back to a published rate is a number they have to
take on faith, which is the one thing a FinOps tool must not ask for.

Two surfaces now expose it.

**On each recommendation** — a collapsed "How this saving was calculated"
disclosure that opens onto the derivation:

```
Standard_D4s_v3   $0.2400/hr   [Azure Retail API]   westeurope
     ↓ downsize to
Standard_D2s_v3   $0.1200/hr   [Azure Retail API]   westeurope
($0.2400/hr − $0.1200/hr) × 730 h × 3 nodes = $263/month
Rates quoted as of 14 Jul 2026.
```

Details that matter more than the layout:

- **It reconciles with the headline.** The arithmetic uses the full-precision
  catalog rate from the provenance record, not the agent's rounded display copy,
  and the result shown *is* the recommendation's stored saving. An e2e spec
  recomputes it from the API and asserts the two agree to the cent — a derivation
  that does not multiply out to the number being acted on is worse than none.
- **Transcribed rates are visibly different from fetched ones.** An API-verified
  rate gets a green badge; a published list price gets an amber one plus an
  explicit line saying it was transcribed rather than machine-fetched. Only 35% of
  the card is API-verified, so this distinction is not decoration.
- **A rate with no recorded provenance says so** rather than rendering a blank
  badge that reads as attribution.
- **It renders nothing when there is no basis** — older rows, and the architect
  agent, which quotes no derived figure. A disclosure that opens onto air is worse
  than no disclosure.
- Cost anomalies and forecast alerts get their own compact basis (billed vs
  expected, and MTD vs budget), each labelled with what it was derived *from*: the
  anomaly block says outright that it comes from billed amounts, not the rate card.

**As a rate card** — `GET /api/v1/pricing/catalog` and a Pricing tab in Settings:
all 23 SKUs with rate, region, source and meter, plus snapshot-level provenance.

The catalog is deliberately **not** org-scoped. It is public rate-card data,
identical for every tenant; the endpoint is authenticated only because the set of
SKUs CloudPilot prices hints at the estate it was built for.

`CatalogMeta` also grew `age_days` / `is_stale` against a 90-day window, so the
"an as-of date should make a stale snapshot visible, not silently trusted" claim in
`pricing/models.py` is now enforced somewhere a person can see. The current
snapshot is 47 days old and reports itself as such.

## 2. The e2e suite

`frontend/e2e/` is a committed Playwright suite — 15 specs, run with `make e2e`.
The previous two sessions' browser checks were ad-hoc scripts that verified a fix
and were then thrown away.

Every spec corresponds to a bug that reached a running app and that no unit test
could have caught:

| Spec | The bug it stands guard over |
|---|---|
| `budget.spec.ts` | Forecast and Recommendations quoting two different budgets |
| `pricing-provenance.spec.ts` | a saving whose derivation does not reconcile |
| `advisor.spec.ts` | a fabricated answer where an honest error belongs |
| `auth.spec.ts` | a deep link lost to the session bootstrap; a token in storage |

Three design choices worth recording:

- **It refuses to run against a half-up stack.** `global-setup.ts` checks
  `/health` first and fails with the exact commands to run. Without that, the whole
  suite fails on obscure selector timeouts when the real cause is that nobody
  started the API — the failure mode that makes people stop trusting a suite.
- **Playwright starts Vite, but not the database.** It can start a dev server; it
  cannot bring up Postgres. The split is explicit rather than pretended.
- **The Advisor spec asserts the offline path** and skips itself only when a model
  is genuinely available. On this hardware unreachable is the normal case, and the
  designed behaviour — an explicit notice, no citation chips, no echo of the
  assembled prompt — is worth pinning. Checking that Ollama *responds* is not
  enough: a running Ollama with nothing pulled produces the same fallback.

It is not wired into CI, which has no stack to run against. Adding a job that could
not be verified without pushing would be worse than documenting `make e2e`.

## 3. `metadata` never reached the client under the name anything read

Found while wiring the disclosure: the API sent the field as `metadata_json`, but
the schema declared it `metadata` and so did the frontend type.

`RecommendationResponse` used `Field(alias="metadata_json")` to map the ORM column.
FastAPI serialises response models with `by_alias=True`, so a plain `alias` renames
the field on the wire too. `chat.py` already had this right — it uses
`validation_alias` for exactly the same ORM-mapping job — so `recommendation.py`
was the odd one out.

Nothing caught it because nothing consumed the field until this session. Every
recommendation had been carrying its pricing provenance to a key no client looked
at. Fixed, and pinned by a test that asserts `metadata` in and `metadata_json` out
of `model_dump(by_alias=True)`.

## 4. Every transcribed rate cited the wrong page

The `meter` field records the provider-side identifier a rate came from, "for
auditability". For the 15 transcribed rates it was one hardcoded string per
provider:

- all nine AWS SKUs — EC2, RDS and ElastiCache instances included — cited
  `aws.amazon.com/s3/pricing`
- all six GCP SKUs, including Cloud SQL and Cloud Storage, cited
  `cloud.google.com/compute/all-pricing`

So a reviewer following an EC2 rate's citation landed on a page that does not
contain it. The comment above the table even names the right pages
(`aws.amazon.com/{ec2,rds,elasticache,s3}/pricing`) — the implementation collapsed
them to one.

Latent for as long as nothing displayed the field. Wrong the moment the rate card
did. The source page is now carried per SKU, and the committed snapshot was patched
in place: the citations changed, the amounts and `generated_at` did not, because
these are the same rates with an accurate record of where they were read. Three
tests now hold it: every rate cites *a* meter, the snapshot's citations match what
the source module would produce, and no AWS SKU is cited against another service's
page.

## 5. The session bootstrap raced itself

Found by the e2e suite on its first run, which is the argument for having one:
`page.goto("/forecast")` landed on the Overview.

`SessionBootstrap` calls `loadSession()` in an effect. React StrictMode
double-invokes effects in development, so two calls hit `/auth/refresh`
concurrently — and refresh tokens are single-use and rotate on every call, a
property a previous session deliberately made atomic. The second call therefore
presents a token the first has already consumed, gets a 401, and reports the user
as *signed out*. `ProtectedRoute` redirects to `/login`, replacing the history
entry; the login page then sees an authenticated user and sends them to `/`. The
requested page is gone, silently.

`loadSession` now shares one in-flight promise — the same guard `lib/api.ts`
already uses around its own refresh. Deep links survive, and the spec that found it
stays as the regression.

Scope note: StrictMode's double-invoke is development-only, so this exact trigger
would not fire in a production build. The underlying fragility is not
development-only — any two concurrent session loads hit the same rotation race —
and it made deep links unusable in the environment the app is actually developed
and demoed in.

## 6. CI never ran the frontend unit tests

The frontend job ran ESLint, typecheck and build. The 16 committed vitest tests
were never executed by CI; `pnpm test` also ran `vitest` in **watch** mode, which
would have hung the job had anyone added it.

`test` is now `vitest run` (with `test:watch` for the watching variant) and CI runs
it. The e2e specs are type-checked too — `tsconfig.json` now includes `e2e/`, so a
broken spec fails `pnpm typecheck` rather than only failing at runtime.

---

## New findings from this pass

1. **`metadata` was serialised as `metadata_json`** — `alias` vs `validation_alias`
   in a FastAPI response model (§3).
2. **All 15 transcribed rates cited one wrong pricing page** (§4).
3. **`loadSession` raced itself against single-use refresh tokens**, losing deep
   links on every reload in development (§5).
4. **CI never ran the frontend unit tests**, and `pnpm test` would have hung it (§6).

## Still open

- **Live multi-cloud billing/metrics** — still deliberately not attempted, for the
  same reason: those adapter methods raise `NotImplementedError` by design, and
  implementing them needs real cloud credentials to test against. Writing them
  blind would reintroduce exactly the "presenting invented figures as a real
  invoice" risk the design exists to avoid.
- **The e2e suite is not in CI** — it needs a running stack; `make e2e` locally is
  the supported path (§2).
- **The rate card snapshot is 47 days old.** Not stale by the 90-day window, but
  `make pricing` before the defence would make the card current and could raise the
  API-verified share above 35%.
- **Backend tests on the host** still need Python 3.11; run them in the container.

## How to reproduce this session's verification

```bash
docker compose up -d postgres redis chromadb backend
docker compose exec -T backend alembic upgrade head
docker compose exec -T postgres createdb -U cp cloudpilot_test    # once

docker compose run --rm --no-deps \
  -e CLOUDPILOT_TEST_DB="postgresql+asyncpg://cp:cp@postgres:5432/cloudpilot_test" \
  backend pytest -p no:warnings                        # 199 passed

docker compose run --rm --no-deps backend ruff check .        # clean
docker compose run --rm --no-deps backend mypy cloudpilot     # zero issues, 87 files

cd frontend && pnpm test && pnpm typecheck             # 36 passed, clean
make e2e                                               # 15 passed

# The rate card, and the field that never arrived:
curl -s localhost:8000/api/v1/pricing/catalog -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['age_days'],'days,',d['api_verified_pct'],'% verified')"
curl -s "localhost:8000/api/v1/recommendations?agent=rightsizing" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import sys,json;print('metadata' in json.load(sys.stdin)[0])"
```
