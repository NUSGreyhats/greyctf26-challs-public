# Frontend Shell

This workspace implements Workstream B from [docs/workstreams.md](../../docs/workstreams.md).

Current scope:

- app routing
- landing, progress, and downloads pages
- stage page shells for Pinpoint, Queens, and Tango
- lock state display
- how-to-play modals
- typed mock payloads that follow the docs contracts

Backend integration notes:

- shared payloads follow [docs/shared-platform-spec.md](../../docs/shared-platform-spec.md)
- stage shells follow [docs/frontend-flow-spec.md](../../docs/frontend-flow-spec.md)
- the client tries live API routes first and falls back to local mocks while the backend streams are still landing

## Local Development

1. Install dependencies with `make frontend-install` from the repo root.
2. Run `make frontend-dev`.
3. Open `http://localhost:5173`.

The Vite dev server proxies `/api` requests to `VITE_API_PROXY_TARGET`, which defaults to `http://127.0.0.1:8000` for local development and is overridden in Docker Compose for the container network.
