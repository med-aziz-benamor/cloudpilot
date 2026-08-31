# CloudPilot — API Reference

Base URL: `http://localhost:8000` · All endpoints are under `/api/v1`.
Interactive docs: **Swagger** `/docs` · **ReDoc** `/redoc`.

Authentication: send `Authorization: Bearer <access_token>` on every request except
the public auth endpoints. Tokens are obtained from `/auth/login`.

## Error format

All errors share a consistent envelope:

```json
{ "error": { "code": 401, "message": "Token expired." } }
```

| Code | Meaning |
|------|---------|
| 401 | Not authenticated / token invalid, expired or revoked |
| 403 | Authenticated but the role lacks the required permission |
| 404 | Resource not found (or not in the caller's organization) |
| 422 | Request body failed validation |
| 429 | Rate limit exceeded |
| 500 | Internal error |

---

## Auth

### `POST /auth/register`
Create an organization and its first (admin) user. **Public.**
```bash
curl -X POST localhost:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"a@b.com","password":"demo1234","full_name":"A B","organization_name":"Acme"}'
```

### `POST /auth/login`
Returns an access token and sets the refresh cookie. **Public.**
```bash
curl -X POST localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@cloudpilot.dev","password":"demo1234"}'
```

### `POST /auth/refresh`
Rotate the refresh token (from cookie or body) and mint a new access token.

### `POST /auth/logout`
Revoke the current access token (jti) and invalidate the refresh token.

### `GET /auth/me`
Return the authenticated user.

---

## Cloud accounts

| Method | Path | Permission |
|--------|------|-----------|
| GET | `/cloud-accounts` | read |
| POST | `/cloud-accounts` | cloud_accounts.manage |
| POST | `/cloud-accounts/test` | cloud_accounts.manage |
| PATCH | `/cloud-accounts/{id}` | cloud_accounts.manage |
| DELETE | `/cloud-accounts/{id}` | cloud_accounts.manage |
| POST | `/cloud-accounts/{id}/sync` | cloud_accounts.manage |

```bash
curl localhost:8000/api/v1/cloud-accounts -H "Authorization: Bearer $TOKEN"
```

---

## Resources

| Method | Path | Notes |
|--------|------|-------|
| GET | `/resources?provider=&service=&region=` | filtered inventory |
| GET | `/resources/tree` | provider → region → service hierarchy |
| GET | `/resources/{id}` | detail with metrics + cost trend |

---

## Costs

| Method | Path | Returns |
|--------|------|---------|
| GET | `/costs/summary` | KPI summary (MTD, projection, savings, score) |
| GET | `/costs/breakdown` | by provider / service / region |
| GET | `/costs/timeseries?period_days=90` | daily spend per provider |
| GET | `/costs/top-drivers?limit=5` | top cost resources |
| GET | `/costs/anomalies` | CostAgent anomaly timeline |

---

## Recommendations

| Method | Path | Permission |
|--------|------|-----------|
| GET | `/recommendations?agent=&status=&sort=impact` | read |
| GET | `/recommendations/savings` | read |
| PATCH | `/recommendations/{id}/status` | recommendations.write |

```bash
curl -X PATCH localhost:8000/api/v1/recommendations/$ID/status \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"status":"accepted"}'
```

Each recommendation carries a `metadata` object holding the basis it was derived
from — for a rightsizing recommendation, both SKUs' rates and the provenance of
each (see [Pricing](#pricing)); for a cost anomaly, the expected and actual billed
amounts. The UI renders this as the "how this was calculated" disclosure on the
card.

---

## Forecast

### `GET /forecast?horizon_days=30`
Reads the latest persisted Prophet snapshot (30/60/90). Returns `404` if the
ForecastAgent has not produced one yet.

| Method | Path | Permission |
|--------|------|-----------|
| GET | `/forecast/budget` | read |
| PATCH | `/forecast/budget` | budget.manage (admin) |

`monthly_budget_usd` is nullable end to end: with none set the API returns `null`,
`over_budget` is false, and the UI says "Not set" rather than falling back to a
number nobody chose. `PATCH` is audited with the previous and new value, because it
moves the threshold every overrun alert in the platform is measured against.

```bash
curl -X PATCH localhost:8000/api/v1/forecast/budget \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"budget_usd":8600}'
```

---

## Pricing

### `GET /pricing/catalog`
The rate card every quoted saving is derived from, with per-rate and
snapshot-level provenance. Authenticated, but **not** org-scoped: it is public
rate-card data, identical for every tenant.

| Field | Meaning |
|-------|---------|
| `generated_at` / `age_days` | when the snapshot was taken, and how old it is |
| `is_stale` / `stale_after_days` | true once past the freshness window (90 days) |
| `api_verified_count` / `_pct` | how much of the card came from a provider API |
| `rates[].source` | `azure_retail_api`, `aws_price_list` or `published_list_price` |
| `rates[].api_verified` | derived from `source` — fetched, not transcribed |
| `rates[].meter` | the provider-side meter or pricing page the rate was read off |

```bash
curl localhost:8000/api/v1/pricing/catalog -H "Authorization: Bearer $TOKEN"
```

Refresh the snapshot with `make pricing` (or `make pricing-deep` to pull the large
AWS offer files and upgrade those rates to `aws_price_list`).

---

## Chat (Cloud Advisor)

| Method | Path | Permission |
|--------|------|-----------|
| GET | `/chat/sessions` | chat.use |
| POST | `/chat/sessions` | chat.use |
| GET | `/chat/sessions/{id}` | chat.use |
| DELETE | `/chat/sessions/{id}` | chat.use |
| POST | `/chat/sessions/{id}/messages` | chat.use (100 req/min) |

```bash
curl -X POST localhost:8000/api/v1/chat/sessions/$SID/messages \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"content":"Is my AKS cluster correctly sized?"}'
```

---

## Admin (admin role only)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/admin/audit-log?limit=100` | view audit events |
| GET | `/admin/audit-log/verify` | recompute & verify the hash chain |
| GET | `/admin/agent-runs` | agent execution history |
| POST | `/admin/agents/{agent}/run` | manually run a scheduled agent |

---

## System

| Method | Path |
|--------|------|
| GET | `/health` |
| GET | `/metrics` (Prometheus) |
