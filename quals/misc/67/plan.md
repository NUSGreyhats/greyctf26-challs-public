# System Design: "67 Gesture" Maze Game (Server-Authoritative Edge AI)

> **Current implementation:** See **§5.6** below and [README.md](README.md). Default production mode is **client-sim + replay verify on finish** (scores > 50), continuous camera-frame verification over WebSocket, and server-side MediaPipe landmark extraction. Sections 1–4 below describe the original design intent and remain useful context, but no longer describe the shipped anti-cheat architecture exactly.

## 1. System Overview

This is a multiplayer-capable, fast-paced dodging game (similar to *Flappy Bird*) controlled by the "67 trend" hand gesture (alternating flat palms moving up and down).

The original target was minimal-latency edge-compute gesture play. The shipped verification path now trades extra bandwidth for stronger anti-cheat: the browser still runs local MediaPipe for responsive controls, but verified high-score runs also stream compressed camera frames to the backend. The backend extracts landmarks server-side, derives the authoritative hand trace, and replays high-scoring runs to verify score and flag eligibility.

---

## 2. Client Architecture (Frontend)

The frontend is responsible for rendering the game, capturing the webcam, and running the Edge AI for responsive local controls. In verified camera mode, it also sends compressed camera frames as `video_frame` evidence over the game WebSocket.

### 2.1 Edge AI Processing

* **Library:** @mediapipe/tasks-vision (Google's MediaPipe Hand Landmarker).
* **Pipeline:**
1. Capture webcam via navigator.mediaDevices.getUserMedia().
2. Feed frames into HandLandmarker.detectForVideo().
3. Extract a whole-hand anchor coordinate for both hands by taking the median x/y position across detected landmarks. Use the anchor y coordinate for the 67 height comparison and the anchor x/y coordinate for the preview overlay.


* **Performance:** MediaPipe runs in WebAssembly/WebGL. It must run in a separate requestAnimationFrame loop, detached from the game rendering loop, so vision processing doesn't stutter the game canvas.

### 2.2 The "67" Gesture Interpreter (Client-Side)

The client calculates the relative difference between the hands to trigger a "flap" or "jump" event.

```javascript
// Pseudocode for gesture extraction
let previousState = "NEUTRAL"; // Can be LEFT_HIGH or RIGHT_HIGH

function processHands(landmarks) {
    if (landmarks.length < 2) return; // Need both hands

    const hand1Y = median(landmarks[0].map((landmark) => landmark.y));
    const hand2Y = median(landmarks[1].map((landmark) => landmark.y));

    // Determine which hand is higher (Y is inverted: 0 is top, 1 is bottom)
    const currentState = (hand1Y < hand2Y) ? "LEFT_HIGH" : "RIGHT_HIGH";

    if (currentState !== previousState && previousState !== "NEUTRAL") {
        // The hands just crossed heights!
        sendToServer({ action: "FLAP", timestamp: Date.now() });
    }

    previousState = currentState;
}

```

### 2.3 Networking (Client)

* Connect to the server via WebSockets (wss://).
* Send `hands` telemetry for UI/corroboration, `video_frame` evidence for server-side landmark extraction, randomized `snapshot` responses, and `finish` claims.
* Explicit `flap` messages are retained for keyboard/dev paths but are not trusted for high-score camera verification.

---

## 3. Server Architecture (Backend)

The server is the absolute source of truth. It tracks the bird's physics, generates the maze, and enforces anti-cheat.

### 3.1 The Game Loop (Hot Path)

* **Tick Rate:** 60 Ticks Per Second (TPS).
* **State:** The server maintains the bird's y_velocity and y_position. Gravity applies every tick.
* **Maze Generation:** The server randomly generates the pipes/obstacles and streams their positions to the client slightly ahead of time. *The client must not know the entire maze layout in advance to prevent pre-scripted botting.*

### 3.2 Anti-Cheat Pipeline (Deterministic Heuristics)

Because the client is sending FLAP events via WebSockets, a cheater can easily write a script: setInterval(() => ws.send({action: "FLAP"}), 100).

The server drops connections that trigger these deterministic heuristic traps:

1. **The Biological Speed Limit:**
* *Logic:* Humans cannot alternate their hands faster than a certain threshold. If a player sends more than ~6 FLAP events per second, they are botting.
* *Action:* Disconnect.


2. **The Perfect Quantization Trap:**
* *Logic:* Scripts use perfect sleep() or setInterval() timers. Humans do not. The server logs the $\Delta t$ (time difference) between the last 10 FLAP events.
* *Action:* If the standard deviation of $\Delta t$ across 10 flaps is < 2ms, it is a machine. Disconnect.


3. **The "Impossible Reaction" Trap:**
* *Logic:* When an obstacle spawns, if the client sends a FLAP event within 100ms of the obstacle appearing on their screen (factoring in network ping), it is a script reacting to network data, not a human processing visuals.
* *Action:* Shadowban (let them hit the obstacle, then disconnect).



### 3.3 Concurrency & Scaling

Given your background in systems, the server should be built for high-throughput WebSocket management.

* **Language:** Go (using gorilla/websocket), Rust (using tokio + tungstenite), or Java (using Netty).
* **Architecture:** Use a single threaded event-loop per game room (similar to Node.js or Redis) to avoid mutex locking on the game state.

---

## 4. Sequence Diagram

```text
[Browser]                                    [Game Server]
   |                                              |
   |--- 1. Initialize WebSocket Connection ------>|
   |                                              |
   |<-- 2. Send initial Maze Seed / Gravity ------|
   |                                              |
   |=== 3. MediaPipe Tracking Starts (Local) ===  |
   |                                              |
   |--- 4. "FLAP" Event (timestamp: 1042) ------->|
   |                                              |---> [Anti-Cheat Checks]
   |                                              |---> Apply upward velocity
   |                                              |
   |<-- 5. Broadcast State (Bird Y: 420) ---------|
   |                                              |
   |--- 6. "FLAP" Event (timestamp: 1058) ------->|
   |                                              |---> [Anti-Cheat Checks]
   |                                              |---> ERROR: 16ms delta.
   |                                              |---> Fails quantization trap.
   |<-- 7. CLOSE_CONNECTION (Reason: Bot) --------|

```

---

## 5. Implementation Log

Created a vanilla browser prototype for the "67 trend" Flappy Bird-style clone.

* Added `frontend/index.html` as the app shell with the canvas game surface, camera controls, tracking telemetry, and authority audit log.
* Added `frontend/styles.css` for the responsive game layout, HUD, telemetry panels, camera preview, and canvas framing.
* Added `frontend/src/app.js` with:
  * A MediaPipe Hand Landmarker client pipeline loaded from `@mediapipe/tasks-vision`.
  * A 67 gesture interpreter that watches whole-hand anchor height, derived from the median of detected hand landmarks, and emits a flap when the higher hand alternates.
  * A Flappy Bird-style canvas loop with gravity, pipe generation, scoring, collisions, restart behavior, and local best-score persistence.
  * A local authority simulation that accepts flap events, applies game physics, and implements the biological speed-limit, timing-quantization, and delayed reaction-audit checks from this plan.
  * A manual input path via pointer/space/button so the game remains testable without camera access.
  * A ready state so the simulation does not start falling before the first manual or camera flap.

This early prototype kept webcam video local to the browser. The current production verifier now sends compressed camera-frame evidence to the backend; see §5.6 and [README.md](README.md).

### 5.1 Full Server-Authoritative App Pass

Reworked the prototype into a complete client/server app.

* Added `package.json` with `start` and `check` scripts intended to be run through `pnpm`.
* Added `backend/server.js`, a dependency-free Node server that:
  * Runs as the backend WebSocket authority service.
  * Upgrades `/ws` connections to WebSockets using the native HTTP upgrade path.
  * Owns the game loop at 60 TPS and broadcasts state snapshots at 30 FPS.
  * Maintains server-side bird position, velocity, score, best score, pipe generation, collision checks, and ready/game-over state.
  * Accepts only discrete `flap` and `restart` client messages.
  * Enforces the biological speed-limit, timing-quantization, and delayed reaction-audit checks on the server.
  * Closes the WebSocket with policy code `1008` when a deterministic botting rule is triggered.
* Replaced the frontend's in-browser authority simulation with a WebSocket client:
  * The canvas now renders authoritative state received from the server.
  * MediaPipe still runs locally in the browser and only emits `flap` events.
  * Manual input now sends the same `flap` event path used by camera gestures.
  * Restart requests are sent to the server instead of mutating local game state.
  * The authority audit log is populated from server messages.

At this stage the app matched the original raw-video-local architecture. The current production verifier later changed this by adding continuous server-side video landmark extraction for verified runs.

### 5.2 Package Manager Update

Switched the project workflow to `pnpm`.

* Added `packageManager: pnpm@10.30.3` to `package.json`.
* The intended local commands are now `pnpm start:backend` for the WebSocket backend, `pnpm start:frontend` for the static frontend, and `pnpm run check` for syntax verification.

### 5.3 Dev Gesture Input

Added a server-configured development setting for keyboard-driven gesture testing.

* Removed the in-game `Space = 67` toggle.
* Added `SPACE_67_KEYBOARD` as the server-side configuration flag; Compose sets it to `true`.
* The server sends this configuration in the WebSocket welcome message.
* When enabled, the Space key emits a synthetic `gesture` flap event, matching the MediaPipe event path.
* When disabled, Space sends a normal manual flap.
* The synthetic input alternates the visible gesture telemetry between left-hand-high and right-hand-high states so a full 67 rhythm can be tested without camera access.
* Standardized non-camera input as manual input throughout the UI and protocol wording.
* Removed the server log panel from the UI; authoritative game checks remain internal to the WebSocket game loop.
* Camera behavior now starts by default on page load, requests webcam access immediately, and displays the live preview in the sidebar; the Camera button remains as a retry path.
* Manual click/Space input is disabled once camera tracking is active so camera mode cannot be started or assisted by keyboard/mouse flaps.
* Camera gesture processing now orders detected hands by mirrored preview hand-anchor X before comparing hand-anchor heights, reducing missed jumps from unstable handedness labels and hand array ordering.
* Brief camera dropouts are held for a short grace window and hand-anchor positions are smoothed before gesture comparison, reducing dead zones when a raised hand briefly loses landmark confidence.

### 5.4 Docker and Visual Polish

Added container deployment and a more Flappy Bird-like visual direction using open-license assets.

* Added `backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`, and `.dockerignore`.
* The Compose stack now builds a backend service on port `8787` and a frontend service on port `4173`.
* Downloaded `frontend/public/assets/flappy_atlas.png` from OpenGameArt.
* Added `frontend/CREDITS.md` and an in-app credits link.
* Asset source: `Flappy Sprite Sheet 16x16` by Yorokobi Games / Rene Breitinger, CC0.
* Updated canvas rendering to use pixel-art bird and pipe sprites from the atlas.
* Added browser-side cleanup for the sprite sheet's border-connected white background so the bird renders without a square backing.
* Brightened the art style with a blue sky, clouds, rounded green hills, tile-like ground, bolder outlined overlay text, and warmer arcade UI colors.
* Fixed pipe rendering to use the atlas' explicit pipe frames: frame 0 for body, frame 1 for top-pipe head, and frame 2 for bottom-pipe head.

### 5.5 Frontend/Backend Split

Separated the deployment shape so it matches the architecture described above.

* Moved server-authoritative game state, physics, scoring, obstacle generation, and anti-cheat checks into the dedicated `backend/` service.
* Moved browser UI, MediaPipe gesture processing, canvas rendering, and static assets into the dedicated `frontend/` service.
* Added a lightweight `frontend/dev-server.js` so local development can run the browser app separately from the backend.
* Updated the browser WebSocket connection to target the backend service on port `8787` by default, with a `?backend=` override for alternate deployments.
* Replaced the single-container Compose app with separate `frontend` and `backend` services.

### 5.6 Client-Sim Play + Replay Verification (Current Production Shape)

The live game no longer reconciles client prediction against 30 FPS server state. Instead:

* **Client:** Runs `shared/game-core.js` locally at display rate. MediaPipe stays in the browser for responsive local controls; camera mode streams `hands` telemetry plus compressed `video_frame` evidence, keyboard mode sends explicit `flap` messages. Physics, collisions, and score are immediate on the client.
* **Server (default `CLIENT_SIM=true`):** Does not tick physics during play. Appends each `restart`, `hands`, `video_frame`, `snapshot`, and `flap` message to a per-session input log with `atMs` offsets. Video frames are sent to the bundled MediaPipe sidecar for server-side landmark extraction.
* **Finish:** When the client reports game over with **claimed score > 50**, it sends `{ type: "finish", score }`. The server waits for pending frame landmark extraction, verifies continuous video/snapshot evidence, canonicalizes replay from server-extracted landmarks, then replays through the same physics + `ServerGestureInterpreter` + anti-cheat pipeline.
* **Flag:** Awarded when replayed score **≥ `WIN_SCORE`** (67 in `shared/game-core.js`) and matches the claim.
* **Anti-cheat:** Heuristics (continuous video coverage, snapshot liveness, cadence, gesture leadup, amplitude/velocity traps, static/reused-frame checks, and cut-frame landmark jumps) run only while score **> 50** during replay or legacy live mode. Public failure messages are intentionally generic; detailed rule reasons stay in backend logs.
* **Legacy mode:** `CLIENT_SIM=false` restores server-authoritative 60 TPS simulation and 30 FPS `state` broadcasts for debugging.

See [README.md](README.md) for environment variables and protocol tables.
