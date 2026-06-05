# Go Going Goen - Master Plan

This folder is the implementation-ready planning set for the challenge.

## Document Map

- [README.md](README.md): spec index and reading order
- **[PRD-TRD-shared-instance-team-token-auth.md](PRD-TRD-shared-instance-team-token-auth.md)**: shared-instance architecture, CTFd auth, pooling, admin tokens
- [shared-platform-spec.md](shared-platform-spec.md): deployment, auth, DB, resets, progression, downloads, shared API rules
- [frontend-flow-spec.md](frontend-flow-spec.md): pages, unlock flow, token bootstrap, UI surfaces, modals, and frontend responsibilities
- [deployment.md](deployment.md): single-instance Docker Compose and production hosts
- [issue-8-instancing-spec.md](issue-8-instancing-spec.md): Option C decision (Whale deprecated)
- [stage1-pinpoint-spec.md](stage1-pinpoint-spec.md): Stage 1 game and backend spec
- [stage2-queens-spec.md](stage2-queens-spec.md): Stage 2 game and backend spec
- [stage3-tango-spec.md](stage3-tango-spec.md): Stage 3 game and backend spec
- [workstreams.md](workstreams.md): suggested parallel delegation split for multiple developers
- [GEMINI_INITIAL.md](GEMINI_INITIAL.md): original source draft kept for reference

## Deployment Direction

One shared backend for all teams. CTFd [team-token plugin](https://github.com/NUSGreyhats/ctfd-team-token-plugin) provides per-team opaque tokens; the challenge app resolves them server-to-server. Whale per-team instancing is not used. See PRD-TRD for the full contract.

## Final Direction

The challenge should be presented as three games, not as a story wrapper.

The progression should feel like:

1. Stage 1: exploit a straightforward request race.
2. Stage 2: exploit non-atomic validation under PostgreSQL `READ COMMITTED`.
3. Stage 3: exploit a two-request saga deadlock where failed validation leaves spendable pending ledger credit.

## Core Principles

- No artificial sleeps.
- No arbitrary time wasters.
- Every exploit window should come from bad logic or realistic bookkeeping.
- Resets must be first-class so players can retry freely.
- Unlocks must persist across resets.
- Source downloads should unlock progressively after clearing prior stages.

## Build Strategy

This plan is intentionally split so multiple developers can work in parallel:

- one developer can own shared platform and auth
- one can own frontend shell and challenge hub
- one can own Stage 1
- one can own Stage 2
- one can own Stage 3

The shared contracts are defined in the platform and frontend specs. Stage specs are written to minimize cross-file ambiguity.
