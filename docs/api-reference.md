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

---

## Forecast

### `GET /forecast?horizon_days=30`
Reads the latest persisted Prophet snapshot (30/60/90). Returns `404` if the
ForecastAgent has not produced one yet.

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
