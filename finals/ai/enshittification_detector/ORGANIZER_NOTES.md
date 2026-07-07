
## Layout

- `chall/`: private service sources, the production flag, and local
  generation/checking helpers.
- `dist/`: public player artifacts.
- `solve/`: reference player-side solve.
- `tests/`: package, red-team, and optional Docker smoke tests.

## Local Checks

Regenerate the public artifacts and private service state:

```bash
python3 chall/generate.py
```

Run tests:

```bash
python3 -m pytest tests/test_challenge.py -q
```

## Docker End-to-End

Build the deployable private service image from this challenge root:

```bash
docker build -f chall/Dockerfile -t enshittification-detector-chall .
```

The Dockerfile installs PyTorch from the CPU-only wheel index because the
service does not need GPU support.

Run the Flask service. The image includes `chall/real_flag.txt` by default for
production deployment. Set `FLAG` only when intentionally overriding it.

```bash
docker run --rm -d --name enshit-smoke \
  --cpus 2 --memory 1g --pids-limit 128 \
  --log-driver json-file --log-opt max-size=10m --log-opt max-file=3 \
  -p 127.0.0.1:35067:5000 \
  enshittification-detector-chall
```

Or deploy with the challenge-local Compose file:

```bash
docker compose -f compose.yml up --build -d
```

Exercise the same HTTP interface a player sees:

```bash
curl -fsS "http://127.0.0.1:35067/audit-pack?team=docker-smoke" -o /tmp/enshit-audit-pack.zip
python3 solve/solve.py --dist dist --audit-pack /tmp/enshit-audit-pack.zip --out /tmp/enshit-payload.json
python3 solve/submit.py --url http://127.0.0.1:35067 --payload /tmp/enshit-payload.json
docker rm -f enshit-smoke
```

The submit command should print the flag below.

The pytest Docker smoke is gated so it does not run on machines without Docker:

```bash
RUN_DOCKER_SMOKE=1 python3 -m pytest tests/test_challenge.py -q
```
