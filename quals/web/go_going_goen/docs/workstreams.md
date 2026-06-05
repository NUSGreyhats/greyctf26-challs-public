# Parallel Workstreams

## Goal

This split is designed so several developers can work at the same time with minimal merge pain.

## Workstream A - Shared Platform

Owner:

- backend lead

Responsibilities:

- CTFd team token auth and session ([PRD-TRD](PRD-TRD-shared-instance-team-token-auth.md))
- per-team lazy seed bootstrap
- `user_progress`
- `/api/auth/session`
- `/api/me`
- `/api/progress`
- `/api/reset`
- `/api/admin/*`
- source download gating

Files likely touched:

- app bootstrap
- auth middleware
- shared models
- shared routes
- download packaging code

Depends on:

- no stage-specific implementation details beyond clear/reset hooks

## Workstream B - Frontend Shell

Owner:

- frontend lead

Responsibilities:

- app routing
- **team token bootstrap and localStorage persistence**
- landing page (including unauthenticated state)
- progress page
- downloads page
- lock state display
- stage page shells
- how-to-play modals

Files likely touched:

- frontend router
- shared layout
- stage page components
- polling helpers

Depends on:

- shared platform API contract

## Workstream C - Stage 1

Owner:

- backend developer 1

Responsibilities:

- Stage 1 tables
- answer seeding
- guess endpoint
- status endpoint
- stage reset helper
- Stage 2 unlock hook

Depends on:

- shared auth and progress tables

## Workstream D - Stage 2

Owner:

- backend developer 2

Responsibilities:

- Stage 2 tables
- board seed/reset
- add/remove endpoints
- submit validation loop
- progress updates
- Stage 3 unlock hook

Depends on:

- shared auth and progress tables

Notes:

- this owner must preserve the intentional `READ COMMITTED` behavior
- do not "fix" the race with DB constraints or row locks

## Workstream E - Stage 3

Owner:

- backend developer 3

Responsibilities:

- Stage 3 tables
- attempt lifecycle
- ledger lifecycle
- deterministic validation lock path
- buy-flag endpoint
- reset logic
- final flag path

Depends on:

- shared auth and progress tables

## Recommended Build Order

Parallel start:

1. Workstream A
2. Workstream B
3. Workstream C
4. Workstream D
5. Workstream E

Integration order:

1. merge shared platform
2. merge frontend shell against mock payloads
3. merge Stage 1
4. merge Stage 2
5. merge Stage 3
6. hook up source downloads
7. run exploit verification

## Cross-Team Integration Contracts

To reduce merge conflicts:

- shared platform owns `user_progress` and unlock helpers
- stage owners expose stage-local reset and clear functions
- frontend uses only documented payloads from the spec files
- source download packaging is owned centrally, but stage owners supply manifest paths for included files

## Verification Ownership

After implementation, assign one person to write:

- Stage 1 exploit script
- Stage 2 exploit script
- Stage 3 two-request deadlock exploit script

This should be someone other than the primary stage implementer if possible.
