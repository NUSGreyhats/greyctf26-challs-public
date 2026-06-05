# Docs Index

## Reading Order

1. [PLAN.md](PLAN.md)
2. **[PRD-TRD-shared-instance-team-token-auth.md](PRD-TRD-shared-instance-team-token-auth.md)** — architecture decision and implementation contract
3. [shared-platform-spec.md](shared-platform-spec.md)
4. [frontend-flow-spec.md](frontend-flow-spec.md)
5. [deployment.md](deployment.md)
6. [issue-8-instancing-spec.md](issue-8-instancing-spec.md)
7. Stage specs:
   - [stage1-pinpoint-spec.md](stage1-pinpoint-spec.md)
   - [stage2-queens-spec.md](stage2-queens-spec.md)
   - [stage3-tango-spec.md](stage3-tango-spec.md)
8. [hardening-and-update-plan.md](hardening-and-update-plan.md)
9. [workstreams.md](workstreams.md)

## What Each File Is For

- `PLAN.md`: high-level summary and intended challenge arc
- `PRD-TRD-shared-instance-team-token-auth.md`: **authoritative spec** for shared-instance deployment, CTFd team token auth, PgBouncer sizing, admin tokens, and acceptance criteria
- `shared-platform-spec.md`: the contract every backend/frontend developer depends on
- `frontend-flow-spec.md`: page structure, unlock behavior, token bootstrap UX, and source-download UX
- `deployment.md`: single-instance Docker Compose shape, env vars, PgBouncer defaults
- `issue-8-instancing-spec.md`: decision record (Option C selected; Whale deprecated)
- `stage1-pinpoint-spec.md`: exact Stage 1 logic
- `stage2-queens-spec.md`: exact Stage 2 logic, with `READ COMMITTED` called out as core
- `stage3-tango-spec.md`: exact Stage 3 logic for the Tango ledger saga/deadlock design
- `hardening-and-update-plan.md`: pre-release fixes derived from solver feedback, constrained by challenge design philosophy
- `workstreams.md`: practical split for parallel implementation

## Expected Outcome

By the time these specs are implemented, the project should have:

- one shared backend serving all teams with CTFd token auth
- one challenge hub UI with query-string bootstrap and session persistence
- three independent stage modules with RLS-scoped team isolation
- progressive source downloads
- stable resets and restart behavior
- PgBouncer at 1000 clients / 200 server connections
