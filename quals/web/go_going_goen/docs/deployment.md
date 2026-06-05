# Deployment Notes

## Decision

This repository deploys as **one shared backend** for all teams. CTFd Team Token authentication replaces Whale per-team instancing.

Authoritative spec: [PRD-TRD-shared-instance-team-token-auth.md](PRD-TRD-shared-instance-team-token-auth.md)

Supported shape:

- `compose.yml` — one `db` + one `backend` (local dev and production baseline)
- backend image includes PgBouncer sidecar managed by Supervisor
- CTFd hosts scoring; challenge app handles gameplay only

## Architecture

```
Player → CTFd challenge (Team Token type, ?token= in description link)
       → https://challs.nusgreyhats.org:34167/?token=tt_...
       → FastAPI (resolve token → session → RLS-scoped DB)
       → PgBouncer (127.0.0.1:6432, 1000 → 200)
       → PostgreSQL (shared, RLS)
```

Whale is **not used**. Do not deploy per-team backend containers.

## HTTP Shape

- Public web UI at `/`
- API under `/api/...`
- PostgreSQL internal-only (Compose network or overlay alias for ops)
- Root-path hosting only — no subpath basename

## Compose Stacks

### `dev/db/docker-compose.yml`

Local backend/frontend development when you only need PostgreSQL:

- PostgreSQL on a random `127.0.0.1` port (`make db-up` prints it)
- Start: `make db-up` / stop: `make db-down`

### `compose.yml`

Full stack:

- PostgreSQL on Compose-internal `db:5432` only (not published to the host)
- bundled FastAPI + frontend on `http://127.0.0.1:${BACKEND_PUBLISH_PORT:-34167}`
- PgBouncer inside backend on a free in-container loopback port (`PGBOUNCER_LISTEN_PORT=0`, not published to the host)

`compose.yml` passes every backend runtime variable from `.env.example` into the `backend` service. Copy `.env.example` to `.env` and override values there; Compose substitutes `${VAR:-default}` from that file.

## Team Isolation

All teams share one database. Isolation is enforced by:

```text
internal_team_id = sha256(TEAM_ID_SALT || CTFD_CHALLENGE_ID || ctfd_team_id)
```

- derived server-side after CTFd token resolve — **never exposed to clients**
- every connection sets `app.team_id` from the authenticated session
- RLS policies: `team_id = current_setting('app.team_id')`

`app.team_id` is a per-connection session variable, not a global setting.

## PgBouncer Config

Local dev connects directly to Postgres:

```text
postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5432/${POSTGRES_DB}
```

Bundled app uses in-container PgBouncer:

```text
postgresql+psycopg://postgres:postgres@127.0.0.1:6432/go_going_goen
```

Upstream via `PGBOUNCER_DB_HOST`, `PGBOUNCER_DB_PORT`, `PGBOUNCER_DB_NAME`, `PGBOUNCER_DB_USER`, `PGBOUNCER_DB_PASSWORD`.

### Defaults (shared instance)

| Setting                         | Value         |
| ------------------------------- | ------------- |
| `POSTGRES_MAX_CONNECTIONS`      | ~250          |
| `PGBOUNCER_MAX_CLIENT_CONN`     | **1000**      |
| `PGBOUNCER_DEFAULT_POOL_SIZE`   | **200**       |
| `PGBOUNCER_POOL_MODE`           | `transaction` |
| `PGBOUNCER_QUERY_WAIT_TIMEOUT`  | 120           |
| `PGBOUNCER_CLIENT_IDLE_TIMEOUT` | 60            |
| `PGBOUNCER_SERVER_IDLE_TIMEOUT` | 30            |
| `PGBOUNCER_SERVER_LIFETIME`     | 600           |

Global pool sizing:

```text
worst_case_upstream = PGBOUNCER_DEFAULT_POOL_SIZE  # 200, not × team count
```

Stage 2 needs ~30 simultaneous transactions per actively exploiting team. At pool 200, expect meaningful cross-team contention when more than ~6 teams exploit concurrently. Document in challenge rules.

Uvicorn: `APP_LIMIT_CONCURRENCY` defaults to **300** for the shared instance. Tune after load testing if needed.

## Secrets and Runtime Config

### Challenge backend

| Variable                        | Purpose                                                           |
| ------------------------------- | ----------------------------------------------------------------- |
| `SESSION_SECRET`                | Cookie HMAC signing                                               |
| `TEAM_ID_SALT`                  | Internal team id derivation (stable across restarts)              |
| `CTFD_RESOLVE_URL`              | CTFd plugin resolve endpoint                                      |
| `CTFD_TEAM_TOKEN_PLUGIN_SECRET` | Server-to-server resolve auth (never client-facing)               |
| `CTFD_CHALLENGE_ID`             | Expected challenge id from resolve                                |
| `ADMIN_TOKEN`                   | Operator routes (`/api/admin/*`)                                  |
| `METRICS_TOKEN`                 | Prometheus `/metrics` scraper                                     |
| `PINPOINT_SECRET`               | Stage 1 wordbank + diagnostics operator token                     |
| `FLAG`                          | Stage 3 buy-flag string returned after clearing the ledger puzzle |

`FLAG` is **not** used for team identity. Competition flag submission stays on CTFd.

### CTFd admin

1. Install [ctfd-team-token-plugin](https://github.com/NUSGreyhats/ctfd-team-token-plugin)
2. Create Team Token challenge; description links to `https://challs.nusgreyhats.org:34167/?token={TEAM_TOKEN}`
3. Copy plugin secret → `CTFD_TEAM_TOKEN_PLUGIN_SECRET`
4. Set `CTFD_CHALLENGE_ID` to the challenge's CTFd id

## Production Hosts

| Service       | URL                                    |
| ------------- | -------------------------------------- |
| CTFd          | `https://ctfd.nusgreyhats.org`         |
| Challenge app | `https://challs.nusgreyhats.org:34167` |

Single backend at the challenge URL. No per-team subdomains or Whale instances.

## Cutover Checklist

- [ ] CTFd plugin installed and challenge published
- [ ] Shared backend deployed with new env vars
- [ ] PgBouncer 1000/200 verified in running container
- [ ] Two-team isolation test passed *(manual / staging with real CTFd tokens)*
- [ ] Exploit scripts updated for token auth *(deferred)*
- [ ] Whale disabled in challenge README
- [ ] Per-team Whale instances decommissioned
