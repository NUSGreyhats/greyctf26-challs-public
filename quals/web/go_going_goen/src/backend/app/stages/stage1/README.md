# Stage 1 Integration Notes

This module implements the Stage 1 surface described in:

- `docs/shared-platform-spec.md`
- `docs/stage1-pinpoint-spec.md`
- `docs/frontend-flow-spec.md`

Current state:

- route wiring is live through the backend scaffold
- the service uses temporary in-memory persistence
- Stage 2 unlock tokens are temporary deterministic placeholders

Shared-platform code should replace:

1. `get_current_user_id()` in `dependencies.py`
2. `InMemoryPinpointRepository` with a real SQL-backed repository
3. `PlaceholderProgressGateway` with `user_progress` writes
4. the placeholder word list with the deployment dictionary

The service intentionally preserves the vulnerable read-then-write guess flow from the spec. Do not add row locks, `SELECT ... FOR UPDATE`, or conditional compare-and-swap updates around the guess limit check.
