# Stage 3 Tango

This module implements [docs/stage3-tango-spec.md](../../../../../docs/stage3-tango-spec.md)
using the same `models.py` / `repository.py` / `service.py` / `router.py` layout as Stages 1 and 2.

Important:

- keep the projection path ahead of final accept/reject
- let `/hint` observe a fresh projection after a rejected attempt
- keep the public goal ladder masked so the hint oracle is needed to recover the middle words
- keep reset scoped to stage-local mutable state
