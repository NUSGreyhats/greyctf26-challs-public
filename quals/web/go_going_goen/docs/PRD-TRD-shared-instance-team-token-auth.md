# PRD / TRD: Shared Instance with CTFd Team Token Authentication

**Document ID:** PRD-TRD-001  
**Version:** 1.0  
**Status:** Implemented in repo — pending CTFd ops validation and solver script updates  
**Last updated:** 2026-05-27  
**Supersedes:** Issue #8 Option B (Whale per-team instancing) as the deployment target

---

## 1. Summary

Go Going Goen moves from **per-team backend containers** (CTFd Whale) to **one shared backend** serving all teams against one PostgreSQL database. Team identity comes from the [NUSGreyhats ctfd-team-token-plugin](https://github.com/NUSGreyhats/ctfd-team-token-plugin). Players authenticate via a **query-string team token** (`?token=tt_...`); the frontend persists that token and the backend issues an opaque session cookie. **No CTFd team metadata** (`team_id`, `team_name`, internal hashes) may reach the client.

PgBouncer is retuned for the shared deployment: **1000 client connections** multiplexed to **200 real PostgreSQL connections** (transaction pool mode, unchanged).

This document is the single source of truth for the architectural shift. Implementation should follow it holistically — not as a partial rollout of deployment without auth, or auth without pooling changes.

---

## 2. Problem Statement

### Current model (deprecated)

- CTFd Whale spawns one backend container per team.
- Each container receives a unique `FLAG` env var; `team_id = sha256(FLAG || TEAM_ID_SALT)`.
- Each container runs its own PgBouncer sidecar (500 clients / 30 server pool).
- Auth is a process-wide singleton cookie with no upstream identity.

### Why change

| Issue | Impact |
|-------|--------|
| Whale operational cost | N containers × memory/CPU for N registered teams |
| Connection math at scale | 500 teams × 30 pool = 15,000 possible upstream connections |
| No CTFd identity bridge | Challenge app cannot correlate players with CTFd teams without per-instance env injection |
| Whale memory limits | 128 MB per instance is tight for Python + PgBouncer + static assets |

### Target model

- **One** backend + **one** PostgreSQL + **one** PgBouncer sidecar.
- CTFd Team Token plugin issues opaque `tt_...` tokens per `(team, challenge)`.
- Challenge backend resolves tokens server-to-server and maps to an internal opaque `team_id`.
- Row-level security (RLS) continues to isolate team data in shared tables.

---

## 3. Goals and Non-Goals

### Goals

| ID | Goal |
|----|------|
| G1 | Deploy exactly one challenge backend for all teams |
| G2 | Authenticate teams via CTFd team token (query string entry, persisted client-side) |
| G3 | Derive stable internal `team_id` per CTFd team without exposing CTFd identifiers to players |
| G4 | Retain existing RLS + singleton-user-per-team data model |
| G5 | Configure PgBouncer for 1000 clients / 200 server connections |
| G6 | Provide admin token config for operator-only routes |
| G7 | Keep all three stage exploits viable under the new pooling model |
| G8 | Flag submission remains on CTFd (standard Team Token challenge type) |

### Non-Goals

| ID | Non-Goal |
|----|----------|
| NG1 | CTFd Whale or any per-team container instancing |
| NG2 | Per-team `FLAG` env injection into the challenge backend |
| NG3 | Returning final flag from the challenge app (CTFd handles scoring) |
| NG4 | Token rotation, expiry, or revoke UI (plugin MVP limitation) |
| NG5 | User-mode CTFd support (team mode only) |
| NG6 | Subpath hosting (e.g. `/go-going-goen/`) — root path `/` only for this release |
| NG7 | Per-team connection fairness at the PgBouncer layer (global pool is acceptable) |

---

## 4. System Context

```mermaid
flowchart LR
    subgraph ctfd [CTFd]
        Plugin[team-token plugin]
        Challenge[Team Token challenge]
    end

    subgraph chall [Challenge stack - single instance]
        FE[React SPA]
        BE[FastAPI]
        PGB[PgBouncer 1000→200]
        PG[(PostgreSQL + RLS)]
    end

    Player --> Challenge
    Challenge -->|"description link ?token=tt_..."| FE
    FE --> BE
    BE -->|"resolve Bearer secret"| Plugin
    BE --> PGB --> PG
    Player -->|"submit flag"| ctfd
```

### External dependency: ctfd-team-token-plugin

Install from [NUSGreyhats/ctfd-team-token-plugin](https://github.com/NUSGreyhats/ctfd-team-token-plugin) into `CTFd/plugins/team-token`.

Relevant plugin behavior (from plugin PRD):

- Lazy-issues `tt_...` token per `(team_id, challenge_id)` on first challenge view
- Substitutes `{TEAM_TOKEN}` in challenge description
- Exposes server-to-server resolve API:

```http
GET /plugins/team-token/api/v1/resolve?token=tt_...
Authorization: Bearer <team_token_plugin_secret>
```

Success: `{"valid": true, "team_id": 42, "team_name": "TeamAlpha", "challenge_id": 7}`  
Failure: `{"valid": false}` (HTTP 200)

The challenge backend **must never forward** `team_name` or raw CTFd `team_id` to clients.

---

## 5. Functional Requirements

### 5.1 Player authentication entry (query string)

| ID | Requirement |
|----|-------------|
| FR-AUTH-1 | Accept team token via query string: `/?token=tt_...` on first visit |
| FR-AUTH-2 | Accept the same token via `POST /api/auth/session` body `{ "token": "tt_..." }` or `GET /api/auth/session?token=tt_...` |
| FR-AUTH-3 | On valid token: resolve via CTFd, bootstrap team-scoped user + progress + instance seed, issue session cookie |
| FR-AUTH-4 | On invalid token: HTTP 401 with generic error (`invalid_token`); do not distinguish unknown vs wrong-challenge tokens in client-visible messages |
| FR-AUTH-5 | After successful bootstrap: frontend removes token from URL via `history.replaceState` |
| FR-AUTH-6 | Subsequent API calls use httponly session cookie only (no token in every request header from browser) |

### 5.2 Client-side token persistence

| ID | Requirement |
|----|-------------|
| FR-PERSIST-1 | Frontend stores team token in `localStorage` key `ggg_team_token` after successful bootstrap |
| FR-PERSIST-2 | If session cookie expired/missing but `localStorage` has token, silently re-call `/api/auth/session` |
| FR-PERSIST-3 | If neither token nor valid session: show landing state instructing player to open the challenge from CTFd (no team-identifying info) |
| FR-PERSIST-4 | Do not display the raw token in UI after bootstrap (optional: show "Connected" only) |

### 5.3 Team metadata concealment

| ID | Requirement |
|----|-------------|
| FR-PRIV-1 | No API response field may contain CTFd `team_id`, `team_name`, or internal `team_id` hash |
| FR-PRIV-2 | Session cookie payload must not contain CTFd identifiers (use opaque `session_id` only) |
| FR-PRIV-3 | Error responses must not echo the submitted token |
| FR-PRIV-4 | Server logs may include truncated token fingerprint and internal `team_id` for ops; never log full tokens in production info-level logs |
| FR-PRIV-5 | HTML shell sets `Referrer-Policy: no-referrer` to reduce token leakage via Referer on outbound navigation |

### 5.4 Admin authentication

| ID | Requirement |
|----|-------------|
| FR-ADMIN-1 | New env var `ADMIN_TOKEN` for operator routes |
| FR-ADMIN-2 | Admin auth accepts `Authorization: Bearer <ADMIN_TOKEN>` or `?admin_token=<ADMIN_TOKEN>` on admin routes only |
| FR-ADMIN-3 | Constant-time comparison for admin token validation |
| FR-ADMIN-4 | `METRICS_TOKEN` remains separate (Prometheus scraper must not inherit admin powers) |
| FR-ADMIN-5 | Stage 1 diagnostics operator token (`PINPOINT_SECRET` fragment) remains separate — it is part of the exploit surface |

Admin route scope (initial):

| Route | Auth |
|-------|------|
| `GET /metrics` | `METRICS_TOKEN` (unchanged) |
| `POST /api/admin/reset-all` | `ADMIN_TOKEN` — wipe all team mutable state (pre-event reset) |
| `GET /api/admin/health-detail` | `ADMIN_TOKEN` — extended diagnostics beyond `/healthz` |

### 5.5 Challenge ID binding

| ID | Requirement |
|----|-------------|
| FR-BIND-1 | Env var `CTFD_CHALLENGE_ID` defines the expected challenge id from resolve |
| FR-BIND-2 | Reject tokens where resolve returns a different `challenge_id` (treat as invalid token) |

### 5.6 Scoring

| ID | Requirement |
|----|-------------|
| FR-SCORE-1 | Players submit the flag on CTFd using standard Team Token challenge flow |
| FR-SCORE-2 | Challenge app does not expose or validate the competition flag |
| FR-SCORE-3 | Do not use `FLAG` for team identity; keep it only for Stage 3 buy-flag gameplay |

---

## 6. Technical Requirements

### 6.1 Internal team identity

Replace env-derived identity:

```python
# REMOVED
team_id = sha256(f"{FLAG}:{TEAM_ID_SALT}").hexdigest()
```

With resolve-derived identity:

```python
# NEW — server-side only
internal_team_id = sha256(
    f"{TEAM_ID_SALT}:{ctfd_challenge_id}:{ctfd_team_id}"
).hexdigest()
```

Properties:

- Stable across app restarts (same salt + CTFd ids → same hash)
- Not reversible to CTFd `team_id` without `TEAM_ID_SALT`
- Not exposed to clients

### 6.2 Request-scoped RLS context

| ID | Requirement |
|----|-------------|
| TR-RLS-1 | Replace global `settings.team_id` with request-scoped `ContextVar[str]` for `app.team_id` |
| TR-RLS-2 | Every DB connection from a request sets `SELECT set_config('app.team_id', %s, false)` from session context |
| TR-RLS-3 | Unauthenticated requests must not open team-scoped DB connections except for auth bootstrap itself |
| TR-RLS-4 | Existing RLS policies in `shared_platform.sql` remain unchanged |

### 6.3 Session model

New table:

```sql
CREATE TABLE auth_sessions (
    id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL,
    token_fingerprint TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX auth_sessions_expires_at_idx ON auth_sessions (expires_at);
```

Session lifecycle:

1. Resolve token → derive `internal_team_id`
2. Insert or refresh `auth_sessions` row (TTL default: 7 days sliding)
3. Set `ggg_session` cookie: `{base64url(JSON)}.{HMAC}` where JSON is `{"session_id": "..."}` only
4. Middleware: cookie → session row → `internal_team_id` → ContextVar
5. `ensure_team_user(internal_team_id)` replaces `ensure_singleton_user()` — one `users` row per `(team_id, username)` as today

Remove: process-startup `InstanceService.ensure_seed()` for a global team.  
Add: lazy `ensure_seed(internal_team_id)` on first authenticated request per team.

### 6.4 CTFd resolve client

New module: `app/services/ctfd_token.py`

| ID | Requirement |
|----|-------------|
| TR-CTFD-1 | HTTP GET to `CTFD_RESOLVE_URL?token=...` with `Authorization: Bearer CTFD_TEAM_TOKEN_PLUGIN_SECRET` |
| TR-CTFD-2 | Timeout: 5s connect, 10s total; 2 retries with backoff on 503/timeout |
| TR-CTFD-3 | In-memory cache: `token → ResolvedContext` TTL 10 minutes (tokens are stable per plugin PRD) |
| TR-CTFD-4 | CTFd unreachable → HTTP 503 `upstream_unavailable` (fail closed) |
| TR-CTFD-5 | Validate token format before calling CTFd (`tt_` prefix, reasonable length) |

Environment:

| Variable | Required | Description |
|----------|----------|-------------|
| `CTFD_RESOLVE_URL` | yes (prod) | e.g. `https://ctfd.nusgreyhats.org/plugins/team-token/api/v1/resolve` |
| `CTFD_TEAM_TOKEN_PLUGIN_SECRET` | yes (prod) | From CTFd plugin admin page |
| `CTFD_CHALLENGE_ID` | yes (prod) | Integer challenge id in CTFd |
| `TEAM_ID_SALT` | yes | Deploy-wide salt for internal id derivation |
| `ADMIN_TOKEN` | yes (prod) | Operator bearer/query token |
| `FLAG` | yes | Stage 3 buy-flag string (gameplay; not team identity) |
| `SESSION_SECRET` | yes | Cookie HMAC signing |

### 6.5 PgBouncer and PostgreSQL

| Setting | Old (per-team instance) | New (shared instance) |
|---------|-------------------------|------------------------|
| `PGBOUNCER_MAX_CLIENT_CONN` | 500 | **1000** |
| `PGBOUNCER_DEFAULT_POOL_SIZE` | 30 | **200** |
| `PGBOUNCER_POOL_MODE` | transaction | transaction (unchanged) |
| `POSTGRES_MAX_CONNECTIONS` | 3600 | **~250** (200 pool + headroom) |
| `APP_LIMIT_CONCURRENCY` | 60 | **200–400** (tune after load test) |

Rationale:

- One global pool replaces N × 30 per-team pools
- Stage 2 exploit needs ~30 simultaneous transactions **per actively exploiting team**
- ~6 concurrent exploiting teams can saturate a 200-connection pool — acceptable tradeoff documented in challenge rules ("play nice")
- Transaction mode remains mandatory for Stage 2 race mechanics

Sizing formula (shared):

```text
worst_case_upstream = PGBOUNCER_DEFAULT_POOL_SIZE  # global cap, not × team count
active_exploit_teams × 30 ≤ 200  →  ~6 teams at full exploit parallelism
```

### 6.6 Deployment shape

| Component | Count |
|-----------|-------|
| `backend` container | 1 |
| `db` (PostgreSQL) container | 1 |
| PgBouncer | 1 (inside backend container, unchanged sidecar pattern) |
| Whale instances | 0 |

Production URLs:

| Service | URL |
|---------|-----|
| CTFd | `https://ctfd.nusgreyhats.org` |
| Challenge app | `https://challs.nusgreyhats.org` (root path) |

CTFd challenge description template:

```markdown
Open the challenge:

https://challs.nusgreyhats.org/?token={TEAM_TOKEN}
```

Remove from challenge README:

```yaml
# Whale
enabled: true
...
```

---

## 7. API Specification

### 7.1 `POST /api/auth/session`

Bootstrap or refresh session from team token.

**Request** (either):

```http
POST /api/auth/session
Content-Type: application/json

{"token": "tt_..."}
```

```http
GET /api/auth/session?token=tt_...
```

**Response 200:**

```json
{"ok": true, "authenticated": true}
```

Sets `ggg_session` cookie.

**Response 401:**

```json
{"error": "invalid_token", "message": "Authentication failed."}
```

**Response 503:**

```json
{"error": "upstream_unavailable", "message": "Authentication service unavailable."}
```

### 7.2 `GET /api/me` (updated behavior)

Requires valid session (not raw token).

**Response 200:**

```json
{"user_id": 1, "username": "team"}
```

No team-identifying fields. Username remains generic constant `team`.

### 7.3 Unchanged shared APIs

These continue to work scoped by session-derived `team_id`:

- `GET /api/progress`
- `POST /api/reset`
- `GET /api/downloads/*`
- All stage routes

### 7.4 Admin APIs (new)

**`POST /api/admin/reset-all`**

```http
Authorization: Bearer <ADMIN_TOKEN>
```

Clears all teams' mutable stage state; preserves `user_progress` unlock flags (operator decision — document in runbook).

**`GET /api/admin/health-detail`**

```http
Authorization: Bearer <ADMIN_TOKEN>
```

Returns pool stats, session count, cache size — no player tokens.

---

## 8. Frontend Requirements

### 8.1 Bootstrap flow

On app mount (`useShellData` or dedicated `useTeamTokenAuth` hook):

1. Parse `?token=` from URL
2. If present → `POST /api/auth/session` → on success persist to `localStorage`, strip URL
3. Else if `localStorage.ggg_team_token` → silent re-bootstrap
4. Else → unauthenticated landing (link text: "Open this challenge from CTFd")

### 8.2 UI copy changes

| Old | New |
|-----|-----|
| "Challenge instance" | "Connected" |
| Any per-instance language | Neutral shared-service language |

### 8.3 Files to modify

- `src/frontend/src/hooks/useShellData.ts` — auth bootstrap
- `src/frontend/src/lib/api.ts` — add `bootstrapSession(token)`
- `src/frontend/src/App.tsx` — unauthenticated gate
- `src/frontend/index.html` — Referrer-Policy meta

---

## 9. Backend Files to Modify

| Area | Files |
|------|-------|
| Config | `app/core/config.py`, `.env.example`, `compose.yml` |
| Auth | `app/services/auth.py`, new `app/services/ctfd_token.py` |
| Team context | new `app/core/team_context.py` (ContextVar) |
| DB | `app/db/session.py` |
| Routes | new `app/api/routes/auth.py`, new `app/api/routes/admin.py` |
| Bootstrap | `app/core/bootstrap.py`, `app/services/instance.py` |
| SQL | new migration for `auth_sessions` |
| Tests | new auth + two-team RLS isolation tests |

---

## 10. Security Requirements

| ID | Requirement |
|----|-------------|
| SEC-1 | Never trust client-supplied `team_id` — only resolved token → session → internal id |
| SEC-2 | `CTFD_TEAM_TOKEN_PLUGIN_SECRET` and `ADMIN_TOKEN` never in frontend bundle or public docs |
| SEC-3 | Rate-limit `/api/auth/session` (per IP: 30/min; per token: 10/min) |
| SEC-4 | Two-team integration test: Team A session cannot read/reset Team B state on every route |
| SEC-5 | Challenge id binding prevents token reuse from other challenges |
| SEC-6 | Admin routes return 404 or 401 uniformly (pick one, document — recommend 401) |
| SEC-7 | `FLAG` is deploy-wide for Stage 3 gameplay only; never derive team identity from it |

---

## 11. Migration from Whale

| Step | Action |
|------|--------|
| 1 | Install ctfd-team-token-plugin on CTFd; create Team Token challenge; note secret + challenge id |
| 2 | Implement auth + ContextVar team context per this document |
| 3 | Update PgBouncer/Postgres env defaults |
| 4 | Deploy single backend; point CTFd description link to shared URL |
| 5 | Disable/remove Whale block from challenge README |
| 6 | Decommission per-team Whale instances |
| 7 | Update solver scripts: `exploit_common.py` accepts `--token` or `GGG_TEAM_TOKEN` env |

No dual-mode production deployment (Whale + shared). Cut over atomically after staging validation.

---

## 12. Acceptance Criteria

| # | Criterion |
|---|-----------|
| AC-1 | Single backend serves ≥2 teams with isolated progress, seeds, and stage state (RLS verified) |
| AC-2 | `/?token=tt_...` establishes session; URL cleaned; token in `localStorage` |
| AC-3 | No client-visible API field contains CTFd or internal team identifiers |
| AC-4 | Invalid token → 401 generic error |
| AC-5 | Token from wrong challenge id → 401 |
| AC-6 | Admin routes reject without valid `ADMIN_TOKEN` |
| AC-7 | PgBouncer `max_client_conn=1000`, `default_pool_size=200` in deployed config |
| AC-8 | Stage 1, 2, 3 exploit scripts complete against shared instance with token auth |
| AC-9 | CTFd flag submission works via standard Team Token challenge (no app flag endpoint) |
| AC-10 | Whale disabled; deployment docs describe single-instance shape only |
| AC-11 | App restart preserves team progress and seeds |
| AC-12 | CTFd resolve outage → 503 on auth bootstrap; existing valid sessions continue until expiry |

---

## 13. Test Plan

| Test | Steps | Expected |
|------|-------|----------|
| T1 Two-team isolation | Bootstrap Team A and B tokens; cross-call `/api/progress`, stage routes, reset | No data leakage |
| T2 Token bootstrap | Visit `/?token=valid` | Cookie set, URL cleaned, `/api/me` works |
| T3 Token persistence | Clear cookie, keep localStorage | Silent re-bootstrap |
| T4 Invalid token | `/?token=tt_bad` | 401, no cookie |
| T5 Wrong challenge | Token for challenge 7, app expects 9 | 401 |
| T6 Admin gate | `/api/admin/reset-all` without token | 401 |
| T7 Resolve mock | Mock CTFd down | 503 on bootstrap |
| T8 Pool config | Inspect running PgBouncer | 1000/200 |
| T9 Exploit e2e | `exploit_stage{1,2,3}.py --base-url URL --token TT` | All pass |
| T10 Privacy audit | Grep API responses in test run | No `team_name`, CTFd id, internal hash |

---

## 14. Resolved Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Deployment model | Option C (shared instance) | Cost, ops simplicity, plugin fit |
| Identity source | ctfd-team-token-plugin resolve API | Purpose-built; no Whale needed |
| Auth entry | Query string `?token=` | User request; matches CTFd description link pattern |
| Token persistence | `localStorage` + httponly session cookie | Cookie for API; localStorage for re-bootstrap |
| Session storage | DB (`auth_sessions`) | Revocation, multi-worker clarity |
| Internal team id | `sha256(salt:challenge_id:ctfd_team_id)` | Stable, opaque, not client-visible |
| PgBouncer sizing | 1000 / 200 | User requirement; global pool tradeoff accepted |
| Admin auth | Separate `ADMIN_TOKEN` | Distinct from CTFd plugin secret and metrics |
| Scoring | CTFd only | Team Token challenge type handles flags |
| Subpath hosting | Not in scope | Root `/` only |

---

## 15. Related Documents

After implementation, these specs must stay consistent with this document:

- [shared-platform-spec.md](shared-platform-spec.md) — auth and team identity sections
- [deployment.md](deployment.md) — single-instance deployment and PgBouncer defaults
- [frontend-flow-spec.md](frontend-flow-spec.md) — token bootstrap UX
- [issue-8-instancing-spec.md](issue-8-instancing-spec.md) — decision record (Option C selected)
- Root [README.md](../README.md) — Whale removed, env var reference updated

---

## 16. Implementation Checklist

Use as a flat work list (not phased rollout):

- [ ] CTFd: install team-token plugin, create challenge, configure description link *(operator)*
- [x] Env: add `CTFD_*`, `ADMIN_TOKEN`, `FLAG`; remove per-team `FLAG` from identity path
- [x] SQL: `auth_sessions` migration
- [x] Backend: `ctfd_token.py` resolve client + cache
- [x] Backend: `team_context.py` ContextVar + session middleware refactor
- [x] Backend: `/api/auth/session` route (query string + JSON body)
- [x] Backend: `/api/admin/*` routes
- [x] Backend: lazy per-team seed bootstrap
- [x] Backend: rate limiting on auth endpoint
- [x] Frontend: token bootstrap hook + localStorage + URL strip
- [x] Frontend: unauthenticated landing state
- [x] Docker: PgBouncer 1000/200, Postgres max_connections ~250, `start.sh` defaults aligned
- [x] Docker: remove Whale overlay network from compose
- [x] Tests: auth flow, resolve mocks, admin gate
- [ ] Tests: two-team RLS integration test *(needs running Postgres + CTFd tokens)*
- [ ] Solvers: `--token` support in `exploit_common.py` *(deferred)*
- [x] Docs: update all related specs (see §15)
- [x] README: disable Whale block
