<!--
Copy this README.md when starting a new challenge.

Required sections are Name, Description, Author, and Flag.

Instancing is NOT used. This challenge runs as a single shared backend with
CTFd Team Token authentication. See docs/PRD-TRD-shared-instance-team-token-auth.md.
-->

# Name
Go Going Goen

# Description

Climbing the corporate ladder is tough, why not try our LinkedOut ladder instead?

Play nice, don't DOS / pwn the DB / other users on the DB

# Author
jloh02

# Flag
`grey{re4D_c0mm1tTed_wIl1_n0t_s4v3_Y0u}`

<!--
Whale instancing is disabled. One shared backend serves all teams.
Players authenticate via CTFd Team Token (?token=tt_...) from the challenge description.
See docs/PRD-TRD-shared-instance-team-token-auth.md and docs/deployment.md.
-->
# Team Token
enabled: true

# Whale
enabled: false

# Go Going Goen

This repository is scaffolded to match the planning docs in [docs/README.md](docs/README.md) and to let multiple developers start in parallel quickly.

## Layout

- `docs/`: planning and implementation specs
- `src/backend/`: FastAPI backend scaffold
- `src/frontend/`: frontend shell scaffold
- `Dockerfile`: bundled backend image with frontend static assets and PgBouncer
- `compose.yml`: image-based app + PostgreSQL stack

## Workstream Mapping

- Shared platform: `src/backend/app/core`, `src/backend/app/api/routes/shared.py`, `src/backend/app/services`
- Stage 1: `src/backend/app/stages/stage1`
- Stage 2: `src/backend/app/stages/stage2`
- Stage 3: `src/backend/app/stages/stage3`
- Frontend shell: `src/frontend/src`

## Quick Start

1. Copy `.env.example` to `.env`.
2. Install dependencies with `make install`.
3. Start PostgreSQL with Docker if you do not already have a local database:
   `make db-up`
4. In one terminal, run `make backend-dev`.
5. In a second terminal, run `make frontend-dev`.
6. Open the frontend at `http://localhost:5173` and the backend health check at `http://localhost:8000/healthz`.

Authentication requires a CTFd team token (`?token=tt_...`) from the challenge description. See [docs/PRD-TRD-shared-instance-team-token-auth.md](docs/PRD-TRD-shared-instance-team-token-auth.md).

## Observability

- `GET /healthz` is the public liveness/readiness endpoint.
- `GET /metrics` exposes Prometheus-format service + database metrics, but is
  **token-gated**: scrapers must send `Authorization: Bearer $METRICS_TOKEN`.
  This avoids leaking validator-internal timing through a public side channel
  (per-request DB query counts double as a stage-2 progress oracle if exposed
  unauthenticated). If `METRICS_TOKEN` is unset the endpoint returns 503.
- `DB_SLOW_QUERY_SECONDS` (default `0.1`) sets the threshold above which a
  query bumps `db_slow_queries_total`, so tail latency can be alerted on
  separately from the histograms.

### Metrics inventory

- HTTP: `http_requests_total{method,route,status_class}`,
  `http_request_duration_seconds{method,route}`,
  `http_response_bytes{method,route}`, `http_inprogress_requests`.
- DB:  `db_queries_total{operation,statement}`,
  `db_query_duration_seconds{operation,statement}`,
  `db_query_errors_total{operation,statement}`,
  `db_slow_queries_total{operation,statement}`, `db_pool_checked_out`,
  `db_connection_open_seconds`.
- Stage internals: `stage_gate_wait_seconds{stage,outcome}` where
  `outcome ∈ {acquired,timeout}`, and
  `stage_submit_duration_seconds{stage,outcome}` where
  `outcome ∈ {accepted,rejected,error,win,valid,invalid}`.

Histogram bucket boundaries are tuned for sub-second responses (the default
prometheus-client buckets bottom out at 5 ms, which collapsed p50/p95 for
this service into the same bucket). p95/p99 can be computed in PromQL with
`histogram_quantile(0.95, sum by(le, route) (rate(http_request_duration_seconds_bucket[5m])))`.

### Suggested initial alerts

- Latency SLO: `histogram_quantile(0.95, sum by(le, route) (rate(http_request_duration_seconds_bucket[5m])))` above your service target.
- Tail outliers: `histogram_quantile(0.99, sum by(le, route) (rate(http_request_duration_seconds_bucket[5m])))` over your tail budget.
- Error budget burn: `sum(rate(http_requests_total{status_class="5xx"}[5m])) / sum(rate(http_requests_total[5m]))` above threshold.
- DB regression: `histogram_quantile(0.95, sum by(le, operation, statement) (rate(db_query_duration_seconds_bucket[5m])))` sustained above baseline.
- DB failure spike: `rate(db_query_errors_total[5m])` above normal background.
- Slow-query rate: `rate(db_slow_queries_total[5m])` over your budget.
- Pool saturation: `db_pool_checked_out` near the process-level max for sustained windows.
- Stage queueing: `histogram_quantile(0.95, sum by(le, stage) (rate(stage_gate_wait_seconds_bucket{outcome="acquired"}[5m])))` rising means a per-stage gate is contending; the matching `{outcome="timeout"}` count tells you how often callers fall off.

## Stage Validation Notes

- Stage source archives ship a flat layout (`stage1/router.py`, `stage1/service.py`, …) with the minimum implementation files needed for the puzzle. SQL schema, dependency wiring, and core platform code intentionally do not ship; solvers reason from the route surface and the service classes.
- Stage 2 exposes `/api/v2/queens/add` with two request shapes: single-queen (`{"row":r,"col":c}`) and batch (`{"queens":[...]}` capped at `ADD_BATCH_MAX=50` per request). The batch form is the intended primitive for the validation race.
- Stage 3's `derive_lock_order` is a SHA-256-seeded permutation of the six `row_balance:N` locks. Solvers mine grid pairs whose lock orderings interlock to trigger a Postgres deadlock during validation.
- PostgreSQL deadlock timing depends on `deadlock_timeout` (default ~1s) and bounds Stage 3 wall-clock by `~1s × rounds_needed`.

## Docker Compose

Use `make docker-up` to start the full local stack:

- PostgreSQL on the Compose-internal `db:5432` network only (not published to the host)
- bundled FastAPI app and frontend on `http://127.0.0.1:${BACKEND_PUBLISH_PORT:-34167}`
- PgBouncer inside the backend container on a free in-container loopback port (`PGBOUNCER_LISTEN_PORT=0`, not published to the host)

### Challenge deployer quickstart

For challenge deployment with Docker Compose:

1. Copy `.env.example` to `.env` and set deployment values: `SESSION_SECRET`, `TEAM_ID_SALT`, `PINPOINT_SECRET`, `FLAG`, `CTFD_RESOLVE_URL`, `CTFD_TEAM_TOKEN_PLUGIN_SECRET`, `CTFD_CHALLENGE_ID`, and `ADMIN_TOKEN`. See `.env.example` for generation recipes.
2. Install [ctfd-team-token-plugin](https://github.com/NUSGreyhats/ctfd-team-token-plugin) on CTFd; create a Team Token challenge linking to `https://your-challenge-url/?token={TEAM_TOKEN}`.
3. Build and start: `docker compose up -d backend` (starts `db` automatically).

One backend serves all teams. Whale per-team instancing is not used.

The Docker Compose stack is image-based and ephemeral:

- no named volumes
- no bind mounts
- no `tmpfs`
- frontend assets and backend code are baked into the backend image
- backend database traffic goes through the local PgBouncer sidecar by default

In local development, the Vite frontend still runs on `http://localhost:5173` and proxies `/api` requests to the backend. In Docker Compose, the backend serves the compiled frontend assets directly.

Because the database data directory now lives only inside the container filesystem, stopping and recreating the `db` container will discard its data.

For backend/frontend development without the bundled app stack, use the inner DB compose file through `make db-up` and `make db-down`. That runs only `dev/db/docker-compose.yml`, so starting a local database does not also activate the root Compose app stack.

The standalone development DB binds PostgreSQL to a random `127.0.0.1` port. The root Compose stack does not publish PostgreSQL or PgBouncer to the host. Run `make db-up` to print the helper DB port.

PgBouncer uses these defaults in Docker Compose (shared single instance):

- local dev `DATABASE_URL`: use the `POSTGRES_USER` and `POSTGRES_PASSWORD` values from `.env` against the host port printed by `make db-up`
- bundled app database traffic: `start.sh` builds `DATABASE_URL` from an in-container PgBouncer listen port (`PGBOUNCER_LISTEN_PORT=0` picks a free port)
- PostgreSQL real connection cap: `POSTGRES_MAX_CONNECTIONS=250`
- upstream Postgres host: `PGBOUNCER_DB_HOST=db` in local Compose
- pool mode: `PGBOUNCER_POOL_MODE=transaction` (required for the Stage 2 race)
- client cap: `PGBOUNCER_MAX_CLIENT_CONN=1000`
- Postgres-facing pool cap: `PGBOUNCER_DEFAULT_POOL_SIZE=200`
- queue wait cap: `PGBOUNCER_QUERY_WAIT_TIMEOUT=120`
- idle client cap: `PGBOUNCER_CLIENT_IDLE_TIMEOUT=60`
- idle server cap: `PGBOUNCER_SERVER_IDLE_TIMEOUT=30`
- server lifetime cap: `PGBOUNCER_SERVER_LIFETIME=600`
- Uvicorn in-flight cap: `APP_LIMIT_CONCURRENCY=300`

The global 200-connection pool is shared across all teams. Stage 2 needs ~30 simultaneous transactions per actively exploiting team; expect cross-team contention when more than ~6 teams exploit concurrently. See [docs/PRD-TRD-shared-instance-team-token-auth.md](docs/PRD-TRD-shared-instance-team-token-auth.md) for the full pooling and auth contract.

## Deployment Shape

One shared backend + one PostgreSQL for all teams. CTFd Team Token plugin handles per-team identity; flag submission stays on CTFd.

Authoritative spec: [docs/PRD-TRD-shared-instance-team-token-auth.md](docs/PRD-TRD-shared-instance-team-token-auth.md)

The app is intended for root-path hosting at `/`, not an arbitrary subpath.

## Make Targets

- `make install`: install backend and frontend dependencies
- `make backend-dev`: start the backend without file watching
- `make backend-dev-reload`: start the backend with Uvicorn reload enabled
- `make frontend-dev`: start the frontend dev server
- `make backend-test`: run the backend test suite
- `make frontend-build`: build the frontend
- `make db-up`: start only the local PostgreSQL helper from `dev/db/docker-compose.yml`
- `make db-down`: stop only the local PostgreSQL helper
- `make docker-up`: build and start the image-based Docker Compose stack
- `make docker-down`: stop the Docker Compose stack

## Local Tooling

Python and Node version managers are intentionally not pinned in-repo.
Use whatever local setup you prefer, such as `asdf`, `mise`, `pyenv`, `nvm`, or a system install, as long as it can run the backend and frontend toolchains in this repository.
For the backend, use Python `3.12+` as required by the project metadata, with Python `3.12` recommended as the safest baseline for dependency installation.

## Intended Solver Scripts

`solve/exploit_stage{1,2,3}.py` are reference solvers — they take `--base-url` and walk the intended exploit chain end-to-end. Use them to validate a deploy is functional:

```
cd solve
python exploit_stage1.py --base-url https://your-deploy-url --token tt_your_token
python exploit_stage2.py --base-url https://your-deploy-url --token tt_your_token
python exploit_stage3.py --base-url https://your-deploy-url --token tt_your_token
```

Obtain `tt_...` from the CTFd challenge description, or set `GGG_TEAM_TOKEN` in the environment. The scripts share an `exploit_common.py` with HTTP/2-enabled httpx and cross-globe-friendly timeouts. Stage 1 caches the enumerated subset to `solve/.pinpoint_subset.cache.txt` so resumes don't re-walk the wordlist.
