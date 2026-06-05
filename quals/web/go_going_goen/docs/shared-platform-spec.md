# Shared Platform Spec

## Scope

This document defines the shared pieces all stages depend on:

- deployment shape
- database conventions
- auth/session model
- progression and unlock storage
- global reset behavior
- source download gating
- shared API response conventions

## Deployment

Current supported baseline:

- one shared PostgreSQL service
- **one** backend container with bundled frontend assets for **all teams**
- CTFd Team Token plugin for upstream team identity ([PRD-TRD](PRD-TRD-shared-instance-team-token-auth.md))

Not used:

- CTFd Whale or per-team container instancing
- per-team `FLAG` env injection

See [deployment.md](deployment.md) and [issue-8-instancing-spec.md](issue-8-instancing-spec.md) for the Option C decision record.

## Runtime Assumptions

- PostgreSQL is the only database.
- PostgreSQL default isolation level remains `READ COMMITTED`.
- App workers must allow meaningful request concurrency.
- DB pool size should be large enough to allow stage exploits but not so large that spam solves everything.

Recommended starting point (shared instance):

- Uvicorn `APP_LIMIT_CONCURRENCY`: 300 default (tune after load test)
- PgBouncer: 1000 client / 200 server connections
- PostgreSQL `max_connections`: ~250

## Team Identity and Seeds

Use one stable internal `team_id` per CTFd team and one stable per-team seed.

`team_id` contract:

- resolve player's `tt_...` token via CTFd plugin API (server-to-server)
- derive internal `team_id` from `sha256(TEAM_ID_SALT || CTFD_CHALLENGE_ID || ctfd_team_id)`
- **never** expose CTFd `team_id`, `team_name`, or internal hash to clients
- the shared PostgreSQL database stores rows for many teams at once
- each request-scoped DB connection sets `app.team_id` from the authenticated session
- row-level security policies use `team_id = current_setting('app.team_id')` to isolate data

Important clarification:

- `app.team_id` is a per-connection PostgreSQL session variable, not a global database setting
- Team A and Team B use the same tables in the same database, but each connection sees only rows for its own `app.team_id`

Seed contract:

Requirements:

- generated lazily on first authenticated request for that team (not at process startup)
- persisted in shared PostgreSQL under that team's internal `team_id`
- reused across app restarts

Progression unlocks are durable booleans in `user_progress`:

- `stage1_cleared = TRUE` unlocks Stage 2
- `stage2_cleared = TRUE` unlocks Stage 3

Do not clear unlocks on reset.

## Authentication

Auth spec: [PRD-TRD-shared-instance-team-token-auth.md](PRD-TRD-shared-instance-team-token-auth.md)

Player flow:

1. Player opens CTFd challenge; description contains link with `?token={TEAM_TOKEN}`
2. Frontend reads query param, calls `POST /api/auth/session`
3. Backend resolves token via CTFd, derives internal `team_id`, bootstraps user/progress/seed
4. Backend sets httponly `ggg_session` cookie; frontend persists token in `localStorage` and strips URL
5. Subsequent requests use session cookie only

Rules:

- one fixed singleton username (`team`) per internal `team_id`
- no player-managed passwords or registration
- no CTFd team metadata in any API response

Admin auth:

- `ADMIN_TOKEN` for `/api/admin/*` (bearer or query param on admin routes)
- `METRICS_TOKEN` for `/metrics` (unchanged, separate from admin)
- Stage 1 diagnostics operator token unchanged (`PINPOINT_SECRET` fragment)

New table: `auth_sessions` (see PRD-TRD §6.3).

## Shared Tables

Minimum shared tables:

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    team_id TEXT NOT NULL,
    username TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (team_id, username)
);

CREATE TABLE instance_state (
    team_id TEXT NOT NULL,
    singleton_key TEXT NOT NULL,
    instance_seed TEXT NOT NULL,
    PRIMARY KEY (team_id, singleton_key)
);

CREATE TABLE user_progress (
    team_id TEXT NOT NULL,
    user_id INT PRIMARY KEY REFERENCES users(id),
    stage1_cleared BOOLEAN NOT NULL DEFAULT FALSE,
    stage2_cleared BOOLEAN NOT NULL DEFAULT FALSE,
    stage3_cleared BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (team_id, user_id)
);
```

All mutable stage tables follow the same rule:

- include `team_id`
- constrain `(team_id, user_id)` back to `users`
- enable RLS with `team_id = current_setting('app.team_id')`

## Progression Rules

- Stage 1 clear unlocks Stage 2 access by setting `stage1_cleared = TRUE`.
- Stage 2 clear unlocks Stage 3 access by setting `stage2_cleared = TRUE`.
- Stage 3 clear returns the final flag.

The UI should rely on `user_progress` rather than recomputing unlocks from stage-local tables.

## Global API

### `POST /api/auth/session`

Bootstrap session from CTFd team token (query string or JSON body). Sets `ggg_session` cookie. Returns `{ "ok": true, "authenticated": true }` — no team-identifying fields.

See PRD-TRD §7.1 for error shapes.

### `GET /api/me`

Requires valid session. Ensures the team-local singleton user exists and returns:

```json
{
  "user_id": 1,
  "username": "team"
}
```

### `GET /api/progress`

Returns:

```json
{
  "stage1": {
    "cleared": true
  },
  "stage2": {
    "cleared": false
  },
  "stage3": {
    "cleared": false
  },
  "downloads": {
    "stage1": true,
    "stage2": false,
    "stage3": false
  }
}
```

### `POST /api/reset`

Resets all stage-local mutable state for the authenticated singleton user within the active `team_id`.

Must reset:

- Stage 1 guesses and solved bit
- Stage 2 board and submission progress
- Stage 3 Tango attempts, ledger entries, validation audit rows, lock barrier rows, and in-flight guards

Must preserve:

- user account
- cleared stage flags

## Source Download Gating

Unlock rules:

- after Stage 1 clear: Stage 1 source becomes downloadable
- after Stage 2 clear: Stage 2 source becomes downloadable
- after Stage 3 clear: Stage 3 source may also become downloadable

Recommended routes:

- `GET /api/downloads`
- `GET /api/downloads/stage1`
- `GET /api/downloads/stage2`
- `GET /api/downloads/stage3`

Returned artifact:

- zip or tarball

Included files for each stage:

- backend handler code for that stage
- frontend stage page code
- relevant schema or migration snippets

Do not include:

- future-stage source before its unlock
- shared secrets
- deployment-only config

## Shared Response Conventions

Use small, predictable JSON responses.

Error shape:

```json
{
  "error": "limit_reached",
  "message": "Guess limit reached."
}
```

Success shape:

```json
{
  "ok": true
}
```

Stage-specific routes may add fields, but should keep a stable top-level structure.

## Reset and Restart Requirements

The challenge must stay solvable after:

- browser refresh
- app restart
- player-issued reset

It must not require:

- organizer intervention
- instance recreation
- manual DB edits

## Backend Module Ownership Boundary

Shared-platform owner is responsible for:

- auth
- session middleware
- instance seed bootstrapping
- `user_progress`
- global reset orchestration
- download gating

Stage owners are responsible for:

- stage-local tables
- stage-local reset helpers
- stage-local routes
- clear-condition hooks that update `user_progress`
