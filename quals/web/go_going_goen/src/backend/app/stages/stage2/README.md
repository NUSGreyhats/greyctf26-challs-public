# Stage 2 Integration Notes

This module implements the Stage 2 surface described in:

- `docs/shared-platform-spec.md`
- `docs/stage2-queens-spec.md`
- `docs/frontend-flow-spec.md`

Current state:

- route wiring is live through the backend scaffold
- the service uses temporary in-memory persistence
- Stage 3 unlock tokens are temporary deterministic placeholders

Shared-platform code should replace:

1. `get_current_user_id()` in `dependencies.py`
2. the in-memory board/submission stores with real SQL-backed implementations
3. `PlaceholderProgressGateway` with `user_progress` writes

Keep the intended vulnerability intact:

- preserve intentional `READ COMMITTED` behavior
- do not add row or column uniqueness constraints
- do not add row locks that close the race
- if the race window needs tuning, prefer richer DB-backed validation audit work such as checked-prefix occupancy snapshots over arbitrary sleeps
