# CloudPilot — Security

Security is priority #2 (above UI). CloudPilot handles cloud credentials for
enterprise clients, so it is **secure by design** across seven trust boundaries.

## Six principles

1. **Least privilege** — cloud connectors use read-only IAM roles; there is no write API.
2. **Defense in depth** — independent trust boundaries; RBAC *and* an ORM tenant filter.
3. **Zero trust** — every request authenticated, every query tenant-scoped.
4. **Secure by default** — all endpoints require JWT unless explicitly public.
5. **Fail closed** — auth failure → 401, permission failure → 403; never silent.
6. **Privacy by design** — local LLM default, no telemetry, minimal PII.

## Trust boundaries

```
Internet
  ↓  TLS 1.2/1.3, HSTS, WAF, rate limiting (nginx)
Reverse proxy
  ↓  security-headers + request-id middleware
Auth middleware           JWT verify (HS256, aud pinned), jti revocation, brute-force lockout
  ↓
RBAC middleware           role → permission matrix
  ↓
Business logic            SQLAlchemy tenant filter (auto org_id scoping)
  ↓
Data + AI                 Fernet-encrypted credentials at rest, local LLM
  ↓
Cloud providers           read-only IAM roles
```

## Authentication

- **Access token** — HS256 JWT, 60-min TTL, claims `{sub, org, role, jti, iat, exp, aud}`.
  The algorithm whitelist rejects `none` and asymmetric algorithms; `aud` is pinned to
  `cloudpilot`. Stored in browser memory only — never `localStorage`.
- **Refresh token** — opaque 64-hex string (not a JWT), 7-day TTL, HttpOnly + Secure +
  SameSite=Strict cookie. Rotated on every use; the old token is consumed in Redis.
- **Revocation** — on logout the access-token `jti` is added to a Redis set with a TTL
  matching its remaining lifetime; `deps.get_token_payload` rejects revoked jtis.
- **Brute force** — 5 failed logins / 5 min / IP → 429 with cooldown; 10 failures /
  email / hour tracked for lockout.

## Authorization (RBAC)

Roles: `admin` > `analyst` > `viewer`. The permission matrix lives in `core/rbac.py`.
Layer 1 is the `require_permission` dependency. Layer 2 is the SQLAlchemy
`do_orm_execute` listener (`core/tenant.py`), which appends
`WHERE organization_id = :current_org` to every SELECT against an entity that
**declares an `organization_id` column** — and, since 2026-07-20, to *every* such
entity in a statement rather than only the first (it used to `break` after one, so a
multi-entity select left the trailing side unfiltered).

### What layer 2 does not cover

The listener can only filter entities that carry the column. Seven models do:
`user`, `cloud_account`, `recommendation`, `chat_session`, `forecast_snapshot`,
`agent_run_log`, `audit_log`.

`resource`, `billing_entry` and `metric_sample` — the three largest tables — do **not**.
They are scoped transitively (`resource.cloud_account_id → cloud_account.organization_id`),
which the listener cannot see. Their isolation rests entirely on services resolving the
caller's `account_ids` first and constraining on them, which `CostService` and
`ResourceService` do correctly. Treat that as a single layer, not defence in depth,
until `organization_id` is denormalised onto those tables.

The scheduler is a third case: it has no request lifecycle, so nothing binds the
`ContextVar` and the listener is a no-op there by design. The agents take
`organization_id` as a parameter and filter on it explicitly; see
`tests/test_scheduler_isolation.py`.

## Startup secrets guard

`Settings._guard_secrets` (a Pydantic `model_validator` in `config.py`) refuses to
construct the settings object — so the app cannot boot — when `APP_ENV=production` and
any of `JWT_SECRET`, `APP_SECRET_KEY` or `FERNET_MASTER_KEY` is empty or still at its
placeholder value. The error names exactly which ones are wrong.

This closes a specific hole: an empty `FERNET_MASTER_KEY` falls back to a key derived
from a **source-code constant**, so anyone holding the repo could decrypt every stored
cloud credential. Failing to start is the correct response.

Separately, a *malformed* `FERNET_MASTER_KEY` is rejected in **every** environment,
including dev — a bad key is never intentional, and without this check it surfaces much
later as an opaque error deep inside credential encryption.

Dev and demo still boot on the placeholders; the guard only tightens in production.
Covered by `backend/tests/test_config.py`.

## Credential encryption

Cloud credentials are Fernet-encrypted (AES-128-CBC + HMAC) before storage via
`core/security.encrypt_credential`. The `FERNET_MASTER_KEY` is sourced from the
environment and is **never** committed, stored in the DB, logged, or returned by the API.

### Key rotation (zero-downtime, 4 steps)

1. Generate a new key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
2. Deploy with a `MultiFernet([new, old])` so both keys decrypt (see `utils/crypto.verify_with_multi`).
3. Re-encrypt every `credentials_enc` blob with the new key (`utils/crypto.reencrypt_blob`).
4. Remove the old key and redeploy.

## HTTP security headers

Enforced on every response by middleware: `Strict-Transport-Security`,
`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy: strict-origin-when-cross-origin`, a restrictive `Permissions-Policy`,
and a `Content-Security-Policy` with `frame-ancestors 'none'`.

## Audit log integrity

`audit_log` is append-only. Each row stores `signature = SHA-256(prev_sig + canonical_row)`,
chaining from a 64-zero genesis. `GET /admin/audit-log/verify` recomputes the chain;
any retroactive edit breaks every subsequent signature.

## Input validation

- Pydantic v2 strict schemas with `extra='forbid'` (unknown fields rejected).
- ORM only — no raw string SQL.
- Max request body 1 MB (nginx + FastAPI).
- Chat endpoints rate-limited to 100 req/min/user; auth to 5/min/IP.

## Incident response runbook

| Scenario | First actions |
|----------|---------------|
| Leaked `FERNET_MASTER_KEY` | Rotate keys (4-step), force credential re-entry, revoke all sessions. |
| Stolen access token | The 60-min TTL caps exposure; revoke the jti; rotate the user's refresh token. |
| Suspected tenant leak | Run `/admin/audit-log/verify`; review the tenant listener; audit recent queries. |
| Brute-force attack | nginx + Redis limiter throttle automatically; block the IP at the WAF if sustained. |
| Compromised cloud creds | Disconnect the account (read-only limits blast radius), rotate the SP/role, re-test. |

## Compliance mapping

| Standard | Status | Coverage |
|----------|--------|----------|
| OWASP ASVS 4.0 L2 | Aligned | auth, session, access control, validation |
| NIST SP 800-53 (Moderate) | Aligned | AC, AU, IA, SC families |
| ISO 27001:2022 | Partial | A.5, A.8, A.9 controls |
| GDPR | Aligned | data minimization, local processing, no telemetry |
