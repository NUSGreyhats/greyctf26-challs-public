# AGENTS.md

## Project Overview

This challenge is organized as a CTF deliverable:

- `chall/`: deployable service, Dockerfile, team-token auth, PoW gate, CTFd score submission.
- `dist/`: public runnable visual cube app and helper libraries.
- `solve/`: sample solver that imports from `dist`, never from `chall`.
- `tests/`: regression tests for layout, import hygiene, PoW, CLI framing, and the sample solve.

## Rules

- Keep `dist` and `solve` free of imports from `chall`.
- Keep `dist` free of organizer-only artifacts and deployment-only code.
- Use package-local imports inside copied service/public code, not `finals.ai.rubikscube...`.
- Preserve the headless CLI protocol because Docker wraps it with `socat`.

## Checks

From `finals/ai/rubikscube`:

```bash
python3 -m unittest discover -s tests
```

Run the public CLI:

```bash
PYTHONPATH=dist python3 -u -m rubikscube.cli
```

Run the participant PoW helper:

```bash
python3 dist/pow.py <prefix> <difficulty>
```

Run the sample solver against the public CLI:

```bash
python3 solve/solve.py --challenge-command "python3 -u -m server.cli.app --cube-count 1 --seed 1 --headless"
```
