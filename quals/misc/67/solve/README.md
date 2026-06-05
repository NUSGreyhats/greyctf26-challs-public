# Solve Lab

Local tooling for the supported video-backed solver. Solver libraries live in
`solve/lib/`; CLI helpers live in `solve/scripts/`. The solve lab serves those
modules at `/solve-lib/*` and only exposes `game-core.js` and `frontend-client.js`
from `/shared/*`.

The solver takes one recording
of a human **stable -> 67 -> stable** gesture, lets you crop it, builds a 67-point
hand replay by alternating that clip forward/backward, renders the exact preview
frames that will be submitted, then replays the run to the backend.

## Run

```sh
pnpm start:backend   # terminal 1 - game authority on :8787
pnpm start:solve     # terminal 2 - solver UI on :4180
```

Open `http://127.0.0.1:4180`. The solve UI proxies WebSocket traffic to the
backend target shown in the sidebar.

## Browser Workflow

1. Record one clean source video of both hands: steady pose, perform one 67
   crossing, then return to a steady pose.
2. Click **Import video**.
3. Click **Auto crop** to scan the video and isolate the single stable -> 67 ->
   stable motion. The solver reports both the action-start timestamp and the
   later interpreter trigger timestamp. Manual start/end crop controls remain
   available when the scan finds more than one possible gesture.
4. Click **Extract clip** if you adjusted the crop manually. MediaPipe samples
   the cropped video and stores the
   hand trace.
5. Click **Build preview**. The solver plans pipe-safe jumps, alternates the
   cropped clip forward/backward for each jump, and renders the JPEG frames that
   will be sent as `video_frame` evidence.
6. Click **Submit preview**. The UI replays the hand trace and submits the same
   preview frames to the backend, then sends `finish`.

The preview canvas is the submission surface: if the rendered video looks wrong,
the server will see the same bad frames.

Section speeds below `1` slow part of the source unit down; values above `1`
speed that part up. The `lead` section ends at the detected action start, while
`gesture` spans action start through the 67 trigger. Overlapping forward/reverse
units are resolved by whichever unit owns the nearest trigger time, so reversed
clips keep their own timing instead of borrowing the forward frame order.

## CLI Build

For a fast local sanity check with an exported cropped trace:

```sh
pnpm solve:build-video -- path/to/cropped-trace.json
# -> video-solve-pack.json
```

This emits a hand trace plus `videoSolve.frames` timing metadata. The browser UI
is still required for real submission because it needs the matching source video
file to render actual frame images.

## Suite

```sh
pnpm solve:suite -- --trace path/to/cropped-trace.json
```

The suite contains one mode: `recorded-video-pingpong`. The old empty-claim,
no-collision, mechanical, and explicit-flap replay paths were removed from the
solver surface because they were diagnostic negatives, not submission candidates.

## Environment

| Variable | Purpose |
|----------|---------|
| `SIMULATE_CLAIMED_SCORE` | Score passed to `finish` in CLI checks (default `67`) |
| `VERIFY_SCORE_THRESHOLD` | Minimum claim before replay verification (default `50`) |
| `SNAPSHOT_LANDMARK_MODE` | Snapshot landmark extraction mode |
| `HAND_LANDMARK_SERVICE_URL` | HTTP endpoint that extracts hand landmarks from submitted images |
| `VIDEO_VERIFY_MODE` | Video verification mode; high-score runs require continuous submitted frames |
| `SOLVE_OVERSHOOT` | Extra planned score before claiming 67; default video build uses `0` |

## Trace Format

```json
{
  "version": 1,
  "events": [
    { "atMs": 0, "message": { "type": "hands", "leftY": 0.43, "rightY": 0.57, "handCount": 2 } }
  ]
}
```

Verified runs need continuous, live-paced hand samples, synchronized video
frames, and valid live snapshot challenge responses. Explicit `flap` packets are
not part of the supported solver path.
