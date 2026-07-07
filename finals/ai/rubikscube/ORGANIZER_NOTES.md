# Organizer Notes

The deliverable layout is intentionally strict:

- `chall/` is the deployable service. It enables the default 24-bit PoW in Docker, validates team tokens, and submits completion scores to CTFd.
- `dist/` is the public runnable visual cube app and helper library copy. It must not import from `chall`.
- `solve/` contains the sample solver. It prepends `../dist` to `sys.path` and imports public cube mechanics from there.

Useful checks:

```bash
python3 -m unittest discover -s tests
```

Run the local deployable service without PoW for fast organizer testing:

```bash
PYTHONPATH=dist:chall python3 -u -m server.cli.app --cube-count 1 --seed 1 --headless
```

Run the sample solver against that service:

```bash
python3 solve/solve.py --challenge-command "python3 -u -m server.cli.app --cube-count 1 --seed 1 --headless"
```

Run the alternate GOFAI strategy against that service:

```bash
python3 solve/solve.py --strategy gofai --challenge-command "python3 -u -m server.cli.app --cube-count 1 --seed 1 --headless"
```

Official scoring environment:

- `CTFD_URL`
- `CTFD_API_TOKEN`
- `CTFD_TEAM_TOKEN_CHALLENGE_ID`
- `CTFD_TEAM_TOKEN_PLUGIN_SECRET` or `TEAM_TOKEN_PLUGIN_SECRET`
