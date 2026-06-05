# Issue 8 Instancing Spec

## Status

**Decision recorded:** Option C — single shared backend with CTFd Team Token authentication.

Implementation spec: [PRD-TRD-shared-instance-team-token-auth.md](PRD-TRD-shared-instance-team-token-auth.md)

Whale per-team instancing (Options A and B) is **deprecated** as the deployment target for this challenge.

## Problem

The challenge needs predictable team isolation while still allowing the intended database-concurrency exploits, without operating one container per registered team.

Three deployment directions were considered:

- **Option A:** per-team instance with isolated database (Whale, rCTF, or equivalent)
- **Option B:** per-team app with shared PostgreSQL and local PgBouncer sidecar
- **Option C:** single shared app and database with CTFd-provided team identity

## Decision: Option C

Use one backend container, one PostgreSQL service, and one PgBouncer sidecar for all teams. Team identity comes from the [NUSGreyhats ctfd-team-token-plugin](https://github.com/NUSGreyhats/ctfd-team-token-plugin). Players authenticate via `?token=tt_...`; the backend resolves tokens server-to-server and scopes all state through RLS.

### Why Option C over Option B

| Factor | Option B (rejected) | Option C (selected) |
|--------|---------------------|---------------------|
| Container count | N teams → N backends | 1 backend |
| PgBouncer math | N × 30 pool → 15k possible upstream conns | 1 × 200 pool globally |
| CTFd integration | Per-team `FLAG` env injection via Whale | Native team-token plugin |
| Ops | Whale lifecycle, memory limits, cold starts | Single deploy, one URL |
| Auth | Process-wide singleton (no upstream identity) | Query-string token → opaque session |

### Accepted tradeoffs

- Global PgBouncer pool (200 server connections) is shared across all teams — ~6 teams can run the Stage 2 exploit at full parallelism simultaneously before pool contention affects others.
- One team's traffic can affect global latency for all teams — mitigated by Uvicorn concurrency caps and challenge rules ("play nice").
- CTFd resolve API becomes a bootstrap dependency — fail closed on outage for new sessions; existing sessions continue until expiry.

## Target Shape

```
┌─────────────┐     ┌────────────────────────────────────┐     ┌──────────────┐
│   CTFd      │     │  Single backend container          │     │  PostgreSQL  │
│  + plugin   │────▶│  FastAPI + frontend + PgBouncer    │────▶│  + RLS       │
│             │     │  1000 clients → 200 server conns   │     │              │
└─────────────┘     └────────────────────────────────────┘     └──────────────┘
```

Shared-PostgreSQL invariants (unchanged):

- one stable internal `team_id` per CTFd team (derived, not exposed to clients)
- one stable team-scoped seed in `instance_state`
- one singleton local user row per internal `team_id`
- per-user progress rows team-scoped through RLS
- stage-local mutable state protected by `team_id` and RLS
- flag submission on CTFd only (Team Token challenge type)

## PgBouncer Config (shared instance)

```ini
[pgbouncer]
listen_addr = 127.0.0.1
listen_port = 6432
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 200
min_pool_size = 0
reserve_pool_size = 0
```

PostgreSQL `max_connections`: ~250 (200 pool + admin/migration headroom).

`pool_mode = transaction` remains mandatory for Stage 2 race mechanics.

## Failure Modes to Design Against

See [PRD-TRD-shared-instance-team-token-auth.md §10](PRD-TRD-shared-instance-team-token-auth.md) for the full security and failure-mode contract. Key items:

### Identity and Auth

- forged tokens or session cookies granting another team's identity
- CTFd `team_id` or `team_name` leaking to clients
- token left in browser history or Referer headers

Mitigations:

- resolve tokens server-to-server only; bind to `CTFD_CHALLENGE_ID`
- opaque session cookies with DB-backed `auth_sessions`
- strip token from URL after bootstrap; `Referrer-Policy: no-referrer`

### Team Isolation

- missing `WHERE team_id = ...` or unset `app.team_id` on connections
- global admin reset without `ADMIN_TOKEN`

Mitigations:

- RLS on all mutable tables
- request-scoped `ContextVar` for team context
- two-team integration tests on every route

### Database Pooling

- global pool exhaustion when many teams exploit Stage 2 concurrently
- PgBouncer bypass via misconfigured `DATABASE_URL`

Mitigations:

- document ~6-team concurrent exploit ceiling at pool 200
- startup logs and health checks confirm PgBouncer path
- load-test exploits through shared pool before prod cutover

## Acceptance Criteria

Full checklist: [PRD-TRD §12](PRD-TRD-shared-instance-team-token-auth.md).

Summary:

- one backend serves all teams with verified RLS isolation
- query-string token auth with client persistence and no team metadata exposure
- PgBouncer 1000/200 in production config
- all three stage exploits pass against shared instance
- Whale disabled; CTFd Team Token challenge is the player entry point

## Historical Options (reference only)

<details>
<summary>Option A: Per-Team Instance (deprecated)</summary>

One app stack and isolated database per team via Whale. Strongest isolation, highest cost. Rejected due to Whale operational overhead and connection math at 500 teams.

</details>

<details>
<summary>Option B: Per-Team App With Shared PostgreSQL (deprecated)</summary>

One backend per team, each with local PgBouncer (500/30), shared PostgreSQL. Was the previous issue #8 target. Rejected in favor of Option C after ctfd-team-token-plugin became available.

</details>
