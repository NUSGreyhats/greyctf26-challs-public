# Hardening and Update Plan (Pre-CTF)

## Purpose

This document translates findings from `../jloh-test-gh-quals/FOR-DEV.md` into a concrete update plan for this repository.

Scope:

- apply fixes before release
- stay aligned with the existing challenge philosophy in `docs/PLAN.md` and stage specs
- avoid adding new mechanics that change intended stage identity

## Design Philosophy Guardrails

The following constraints are treated as non-negotiable:

- keep the intended exploit arc: Stage 1 TOCTOU -> Stage 2 `READ COMMITTED` race -> Stage 3 deadlock + saga compensation bug
- no artificial sleeps or arbitrary time-waster mechanics
- resets stay first-class and retry-friendly
- stage mechanics should come from realistic logic/accounting flaws, not random luck alone
- source downloads stay progressive by stage

Where `FOR-DEV.md` suggestions conflict with these constraints, we apply a narrowed version.

## Cross-Cutting Updates

### Adopt now

- Reconcile source download naming so API keys, frontend usage, and download routes use one contract.
  - Fix mismatch between `stage1_source`-style keys and `/api/downloads/stage1` route usage.
- Reduce unnecessary source leakage in player tarballs.
  - Exclude `InMemory*Repository` classes from player-facing artifacts where possible.
- Remove dead-weight or clarify dead-weight config fields.
  - If `TEAM_ID_SALT` / `SESSION_SECRET` / related derivation paths are load-bearing, surface their role clearly.
  - If not load-bearing for this mode, remove from player-visible surface and comments.

### Keep as-is (documented intent)

- `HEAD` returning `405` with `allow: GET` is acknowledged but not treated as a release blocker.
  - This is recognized as endpoint shape leakage, but low impact relative to source release model.

## Stage 1 (Pinpoint) Updates

Reference: Stage 1 section in `FOR-DEV.md`.

### Adopt now

- De-telegraph comments and adjacency hints around the race.
  - Remove or rewrite comments that directly narrate the vulnerable check-then-update path.
- Tune gate-value signaling.
  - Keep race solvable, but avoid conspicuous values that visually "point" at the exploit.
- Remove misleading placeholder hints.
  - Replace placeholder wordbank values that can be mistaken for live answer hints.
- Align guess-shape messaging.
  - Ensure regex behavior and UI copy describe the same rule (exactly-five vs at-least-five).
- Preserve `recent_guesses` as informational only and ensure no answer leakage in solved UI states.

### Narrowed from `FOR-DEV.md` due to philosophy

- Do not rate-limit `/reset` as a default hardening step.
  - Stage 1 spec explicitly expects rapid reset-and-retry loops.
  - Instead, we improve clarity and de-telegraphing while preserving retry ergonomics.

## Stage 2 (Queens) Updates

Reference: Stage 2 section in `FOR-DEV.md`.

### Adopt now

- Remove gate inconsistency and simplify signal.
  - Eliminate `capacity=4` vs `capacity=30` split; use one source of truth.
  - Avoid noisy capacity values that suggest an unrelated exploit path.
- Keep vulnerability in intended place but reduce explicit architecture signposts.
  - Keep `READ COMMITTED`-driven behavior as core mechanic.
  - Avoid making "separate validation DB factory" look like a textbook hint in code comments/API shape.
- Improve race fairness across network conditions.
  - Validate exploit reliability at higher RTT profiles.
  - Preserve DB-shaped validation work window (audit/progress work), not fixed sleeps.
- Improve operator observability around race outcomes.
  - Track which `add-batch` call contributes to a winning crossing where practical.
  - Reduce audit noise that obscures successful exploit traces.
- Clarify intentional route exposure.
  - Since `/add-batch` is a source-read discovery path, explain this in release notes/docs to avoid "oversight" interpretation.

### Keep as-is (documented intent)

- Do not remove the Stage 2 race itself before release.
  - Stage 2 spec defines this race as the core learning objective.

## Stage 3 (Tango) Updates

Reference: Stage 3 section in `FOR-DEV.md`.

### Adopt now

- Remove explicit hint comments that point directly to the bug path.
  - Rewrite comments like "error without awarding play credit" to neutral language.
- Keep two-request precision model but reduce obviousness in prose/comments.
  - Preserve capacity-two gate behavior as intentional anti-spray design.
- Clarify ledger and UX semantics so puzzle logic is intentional, not accidental copy mismatch.
  - Align player-facing text with settlement model and pending-credit behavior.
- Improve `ledger/refresh` safety messaging.
  - Keep explicit refresh behavior, but label consequences clearly to prevent accidental self-reset confusion.
- Document deadlock timing expectations for local parity.
  - Note `deadlock_timeout` behavior and expected runtime profile in docs.

### Narrowed from `FOR-DEV.md` due to philosophy

- Keep lock-order derivation deterministic with a constrained order space for first release shape.
  - `FOR-DEV.md` suggests broadening lock derivation scope aggressively.
  - Current Stage 3 direction keeps exactly two deterministic lock-order groups derived from full-grid top-half vs bottom-half imbalance, preserving precise two-request exploitation without spray tuning. We should use number of suns and moons on the first versus second half. Which means users have to intentionally give wrong answers.

## Local Testability and Player Experience

Reference: Local-test friction section in `FOR-DEV.md`.

### Adopt now

- Ship practical local scaffolding guidance for stage validation.
  - Provide stage-local run instructions or compose workflow compatible with source drops.
- Provide SQL DDL or migration snippets with source artifacts where intended by shared/platform docs.
  - Ensure players can reason about referenced tables without guesswork.
- Clarify singleton-instance assumptions and what is intentionally out-of-scope for player workflow.

## Implementation Checklist

- [x] Align download naming contract across backend, frontend, and docs.
- [x] Strip test-only/in-memory repository classes from player source artifacts.
- [x] Stage 1: remove hinty comments, clean placeholder wordbank hints, align guess-rule messaging.
- [x] Stage 2: unify submission gate configuration source and value; reduce architecture telegraphing.
- [ ] Stage 2: run RTT fairness verification and tune DB-shaped validation workload if needed.
- [ ] Stage 2: improve audit traceability for winning race events.
- [x] Stage 3: rewrite hint comments; align UI copy with ledger semantics.
- [x] Stage 3: improve `ledger/refresh` wording/UX warning.
- [x] Stage 3: document deadlock timing behavior for local reproduction.
- [x] Publish local run + DDL guidance for stage-source consumers.

## Out of Scope for This Document

This plan does not include post-CTF vulnerability removal.

Examples intentionally out-of-scope here:

- making Stage 1 counter enforcement atomic
- removing Stage 2 race conditions entirely
- removing Stage 3 pending-credit spendability bug

Those belong to a separate post-event security hardening track.
