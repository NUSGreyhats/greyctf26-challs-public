# Name

Enshittification Detector

# Description

I trained a ticket classifier, and an auditor wants to know which disputed candidate tickets were actually used to train the deployed model.

Download your audit pack, compare the target model against the provided shadow models, and label every candidate with one of the binary labels:
- `IN`: this exact candidate was used to train the target model.
- `OUT`: this exact candidate was not used to train the target model.

Exactly half of each audit pack is `IN`.

The endpoint is a Flask app which supports 2 operations
1. `GET /audit-pack?team=<team_name>`
- Please use your team name, although TECHNICALLY you can use anything.
- You will receive 3 files:
  - `manifest.json`
  - `audit_candidate_ids.json`
  - `target.pt`
- You are supposed to classify whether each of the candidates in `audit_candidate_ids.json` was used to train `target.pt`
2. `POST /submit`
Once you're done, submit with the following JSON body
```json
  {
    "team": "<team_name>",
    "nonce": "<copy the thingy from manifest.json>",
    "predictions": {
      "candidate_000": "IN",
      "candidate_001": "OUT"
      ...
    }
  }
```

# Author

N00bcak

# Flag

`grey{https://www.youtube.com/watch?v=T4Upf_B9RLQ}`

# Whale

enabled: false
redirect_port: 5000
memory_limit: 512m
cpu_limit: 1.0

# Deployment

Build the service image from this challenge root using `chall/Dockerfile`. The container listens on port `5000` and serves the HTTP API used by the public solver.

Required environment:

- None.

Optional environment:

- `FLAG`: override the bundled private flag from `chall/real_flag.txt`.
- `SOCAT_CLOSE_TIMEOUT`: SABLE-style close timeout passed to `socat -t` when the service is fronted by socat. Default: `20`.
- `SOCAT_IDLE_TIMEOUT`: idle timeout passed to `socat -T` when the service is fronted by socat. Default: `1800`.

Build:

```bash
docker build -f chall/Dockerfile -t enshittification-detector-chall .
```

Local Docker smoke:

```bash
docker run --rm -d --name enshit-smoke -p 127.0.0.1:35067:5000 enshittification-detector-chall
curl -fsS "http://127.0.0.1:35067/audit-pack?team=docker-smoke" -o /tmp/enshit-audit-pack.zip
python3 solve/solve.py --dist dist --audit-pack /tmp/enshit-audit-pack.zip --out /tmp/enshit-payload.json
python3 solve/submit.py --url http://127.0.0.1:35067 --payload /tmp/enshit-payload.json
docker rm -f enshit-smoke
```
