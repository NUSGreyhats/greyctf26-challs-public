<!--
Copy this README.md when starting a new challenge.

Required sections are Name, Description, Author, and Flag.

Read the Whale section below if the challenge needs per-team/per-user instances.
-->

# Name
67

# Description

Can you 67 on a merry christmas?

https://six-seven.chal.zip/

# Author
jloh02

# Flag
`grey{676676767676767_0110_0111_0110_0111_736978736576656E}`

# Challenge

Play flappy bird with 67 hand gestures. Reach a pipe score of **67** on a verified run to receive the flag.

# Game architecture

The browser runs the game simulation locally (`shared/game-core.js`) for responsive play. During verified camera runs, the client streams compressed camera frames to the backend over the game WebSocket. The backend sends those frames to the bundled MediaPipe sidecar, derives the authoritative hand trace from server-extracted landmarks, and replays physics from that server trace.

| Phase            | Client                            | Server                                                                                                                                                |
| ---------------- | --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| Play             | Local physics + rendering         | Records `restart`, dev telemetry, live video frames, and dev/keyboard `flap` events with timestamps                                                   |
| End (score ≤ 50) | Shows final score                 | No replay; lightweight ack                                                                                                                            |
| End (score > 50) | Sends `{ type: "finish", score }` | Waits for frame landmark extraction, verifies continuous video/snapshot evidence, replays server-derived hand samples, returns `{ type: "verified" }` |

**Scoring**

- Pipe score is shown live on the client.
- **Flag threshold:** `WIN_SCORE` (67) from `shared/game-core.js` — also sent as `constants.winScore` / `config.winScore` in `welcome`.
- **Verification threshold:** scores strictly above `VERIFY_SCORE_THRESHOLD` (default 50). Anti-cheat heuristics apply only above that threshold during replay/live play (live camera snapshot challenges, camera trace liveness, cadence, gesture leadup, frozen dual-hand streams, repeated amplitude, constant velocity).
- **Continuous video verification:** during camera play, the browser streams `video_frame` messages. High-score replay uses server-extracted video landmarks as the authoritative hand trace, not client-submitted hand coordinates.
- **Snapshot challenges:** during camera play, the backend sends randomized `snapshot_challenge` messages over the game WebSocket. The browser must immediately return a camera frame plus current raw hand sample. Verified runs require enough valid, deadline-bound, non-reused frames.
- **Landmark matching:** enabled by default. The backend sends each accepted snapshot image to `HAND_LANDMARK_SERVICE_URL` and compares the server-extracted raw hand anchors to the submitted raw anchors. This is tolerance-based, not exact, because browser smoothing, JPEG compression, and independent model runs can shift coordinates slightly. Smoothing is used only for gameplay gesture interpretation.
- **Continuity checks:** server-side video landmarks must have enough frame cadence, enough two-hand detections, unique frame hashes, meaningful motion range, moving-frame ratio, no short-gap landmark jumps, and reasonable agreement with the client telemetry. Static hand photos, repeated images, sparse streams, cut-frame jumps, and client/video trace mismatches fail closed.

**WebSocket messages (client → server)**

- `restart` — start a new run (clears server input log).
- `hands` — `{ leftY, rightY, handCount, clientTime }` hand-height telemetry (~60 Hz in camera mode). Verified high-score camera runs use this only as corroborating telemetry; replay uses server-extracted video landmarks.
- `flap` — keyboard/dev mode explicit flap (`source: "gesture" | "manual"`). Explicit flap packets are not trusted for high-score camera verification.
- `video_frame` — continuous compressed camera frame plus current raw hand sample. Verified high-score replay derives canonical hand samples from server-side landmarks extracted from these frames.
- `snapshot` — response to a backend snapshot challenge, including a compressed camera frame and current raw hand sample.
- `finish` — `{ score, clientTime }` after game over when verification is required.

**WebSocket messages (server → client)**

- `welcome` — `constants` (includes `winScore`), `config.winScore`, `config.verifyScoreThreshold`, session best score.
- `snapshot_challenge` — randomized request for an immediate camera frame during a live run.
- `snapshot_result` — accepts/rejects the submitted challenge image. Rejection text is generic; detailed reasons stay server-side.
- `verified` — replay outcome, flag (if won), and a public verification summary. Blocked anti-cheat failures intentionally use a generic client-visible message.

Set `CLIENT_SIM=false` on the backend to restore the older server-authoritative mode (live 60 TPS sim + 30 FPS state snapshots) for debugging.

# Environment variables

| Variable                         | Default                                           | Description                                                                            |
| -------------------------------- | ------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `CLIENT_SIM`                     | `true`                                            | Log inputs during play; verify on `finish` instead of live authority                   |
| `VERIFY_SCORE_THRESHOLD`         | `50`                                              | Minimum claimed score before server replay                                             |
| `SNAPSHOT_CHALLENGES`            | `true`                                            | Require randomized live camera snapshots for verified runs                             |
| `SNAPSHOT_MIN_REQUIRED`          | `10`                                              | Minimum completed snapshot challenges for a verified high-score run                    |
| `SNAPSHOT_MAX_MISSING_HAND_RATIO` | `0.1`                                             | Fraction of snapshot responses allowed without two tracked hands                       |
| `SNAPSHOT_MAX_MISSING_HANDS`     | unset                                             | Optional absolute override for missing-hand snapshot responses                         |
| `SNAPSHOT_HAND_GRACE_MS`         | `420`                                             | Accept nearby hand telemetry when a snapshot response briefly loses tracking         |
| `SNAPSHOT_DEADLINE_MS`           | `1200`                                            | Response deadline for each live snapshot challenge                                     |
| `SNAPSHOT_LANDMARK_MODE`         | `required`                                        | `off`, `optional`, or `required` server-side image landmark matching                   |
| `HAND_LANDMARK_SERVICE_URL`      | `http://hand-landmarks:8790/landmarks` in Compose | HTTP endpoint that extracts hand landmarks from snapshot images                        |
| `HAND_LANDMARK_MAX_ANCHOR_DELTA` | `0.1`                                             | Max normalized Y difference between server-extracted anchors and submitted raw anchors |
| `HAND_LANDMARK_TIMEOUT_MS`       | `1200`                                            | Backend timeout for each snapshot landmark extraction request                          |
| `VIDEO_VERIFY_MODE`              | `required`                                        | `off` or `required` continuous server-side video landmark verification                 |
| `VIDEO_VERIFY_MIN_FRAMES`        | `80`                                              | Minimum video frames required for a verified high-score run                            |
| `VIDEO_VERIFY_MIN_VALID_FRAMES`  | `70`                                              | Minimum valid two-hand server landmark frames                                          |
| `VIDEO_VERIFY_MIN_AVERAGE_FPS`   | `4`                                               | Minimum average accepted frame rate across the run                                     |
| `FLAG` / `FINAL_FLAG`            | —                                                 | Flag string returned when verified score ≥ 67                                          |
| `DISABLE_ANTI_CHEAT`             | `false`                                           | Skip heuristics (dev only)                                                             |
| `SPACE_67_KEYBOARD`              | `false`                                           | Space bar emits synthetic gesture flaps                                                |
| `DIAGNOSTIC_PAGE`                | `false`                                           | Serve `/diagnostics` from the backend                                                  |

**Hand landmark service contract**

When `SNAPSHOT_LANDMARK_MODE=required`, verified high-score runs fail closed if
`HAND_LANDMARK_SERVICE_URL` is unset or unavailable. The service must accept
`POST` JSON:

```json
{ "challengeId": "...", "image": "data:image/jpeg;base64,...", "width": 480, "height": 270 }
```

It can return either raw anchors:

```json
{ "handCount": 2, "leftY": 0.42, "rightY": 0.58 }
```

or MediaPipe-like landmark arrays:

```json
{ "hands": [{ "landmarks": [{ "x": 0.7, "y": 0.42 }] }, { "landmarks": [{ "x": 0.3, "y": 0.58 }] }] }
```

The backend uses raw anchor Y values and compares them with a tolerance
(`HAND_LANDMARK_MAX_ANCHOR_DELTA`), not exact equality.

The Compose stacks include a bundled MediaPipe sidecar at
[hand-landmarks/server.py](/Users/jloh02/Documents/Programming/i26-q/hand-landmarks/server.py).
The backend points to it by default, so `SNAPSHOT_LANDMARK_MODE=required`
does not need an external service when using Docker. The first image build
downloads the MediaPipe hand landmarker model into the sidecar image.

**Failure feedback**

High-score verification failures return a **category-specific player hint** (for
example, choppy camera feed, missed snapshot, or sparse hand tracking) instead of
one generic message. Exact thresholds and internal rule strings stay in backend
logs; the `verified` payload may also include `failureCode` and `detail` for
solve tooling and operators.

Players still do not receive numeric tuning parameters — only actionable guidance
for the failure category that fired.

# Diagnostics

The hand-tracking diagnostic route is disabled by default. Start the frontend
with `DIAGNOSTIC_PAGE=true` to expose `/diagnostics`:

```sh
DIAGNOSTIC_PAGE=true npm run start:frontend
```

Open `http://127.0.0.1:4173/diagnostics` to view live hand-height, delta, threshold,
cross-count, and jump-trigger markers.

For Docker Compose, pass `DIAGNOSTIC_PAGE=true`; Compose forwards it to the
backend container, which serves `/diagnostics` when enabled.

# Local Development

**Single process (backend serves frontend):**

```sh
pnpm start
# or
pnpm start:backend
```

Open `http://127.0.0.1:8787` (set `DIAGNOSTIC_PAGE=true` in the start script for `/diagnostics`).

For solver tooling, use the solve lab at `http://127.0.0.1:4180` (`pnpm start:solve`). Solver libraries and scripts live under `solve/`.

**Split frontend dev server:**

```sh
pnpm start:backend   # port 8787
pnpm start:frontend  # port 4173, proxies WS to backend
```

**Solve lab** (trace record/replay proxy): see [solve/README.md](solve/README.md).

**CLI simulation:**

```sh
pnpm simulate:sussy
pnpm simulate:human
pnpm simulate:trace
```

Docker local stack: [docker-compose.local.yml](docker-compose.local.yml)

```sh
docker compose -f docker-compose.local.yml up -d backend
```

That starts both `backend` and the `hand-landmarks` dependency. App:
`http://127.0.0.1:8787`; sidecar health:
`http://127.0.0.1:8790/healthz`.

# HTTPS Deployment

The default [docker-compose.yml](/Users/jloh02/Documents/Programming/i26-q/docker-compose.yml)
is the production stack. It adds Nginx in front of the backend for TLS
termination and runs the MediaPipe hand-landmark sidecar on the internal
Docker network, so a dedicated server can simply run `docker compose up -d`.

Set these environment variables before starting:

```sh
export SERVER_NAME=your-domain.example
export CERTBOT_DOMAIN=$SERVER_NAME
export APP_PORT=36367
```

The production compose file publishes a single host port: `${APP_PORT:-36367}`
on the Nginx TLS listener. The backend is only reachable inside the Docker
network.

Nginx expects host-managed TLS files at:

```sh
/etc/letsencrypt/live/$CERTBOT_DOMAIN/fullchain.pem
/etc/letsencrypt/live/$CERTBOT_DOMAIN/privkey.pem
```

Use DNS-01 or another certificate flow that does not require this compose stack
to publish port 80. After the certificate exists, normal startup is:

```sh
docker compose up -d
```

Nginx terminates TLS and proxies `/`, `/api/`, and `/ws` to the backend. Game traffic uses WebSocket frames, including `hands` telemetry, continuous compressed `video_frame` evidence, randomized `snapshot` responses, and the small `finish` claim. Increasing `client_max_body_size` is only needed if you add HTTP endpoints that accept full trace uploads — see comments in [nginx/default.conf.template](nginx/default.conf.template).
