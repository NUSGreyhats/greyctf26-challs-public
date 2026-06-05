# SDPA Graph Attention CTF Package

Folder contract:

- `chall/` — challenge-author files. Not for participants.
- `dist/` — participant distribution and deployable checker. Contains no real flag.
- `service/` — deployment Dockerfile for the remote checker.
- `solve/` — reference solve. It reads only from `../dist`.

Quick sanity test:

```bash
python chall/make_challenge.py
python chall/audit_package.py
python chall/redteam_suite.py
cd solve
python solve.py
```

The local checker returns a dummy flag unless `FLAG` is set in the environment. The Docker image exposes the checker on TCP port `38267`.
