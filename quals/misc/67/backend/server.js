/**
 * 67 Flight backend — WebSocket game service.
 *
 * Default mode (CLIENT_SIM=true): the browser runs physics locally for smooth play.
 * The server records `restart`, `hands`, continuous `video_frame` evidence, and
 * dev/keyboard `flap` events. High-score camera verification derives physics flaps
 * from server-extracted video landmarks, not trusted client coordinates. When a run
 * ends with score > VERIFY_SCORE_THRESHOLD (50), the client sends
 * `{ type: "finish", score }` and the server replays the server-derived trace through
 * shared/game-core.js plus gesture + anti-cheat heuristics. The flag is granted when
 * replay score >= WIN_SCORE and the claim matches.
 *
 * Anti-cheat heuristics run only while replay/live score is above VERIFY_SCORE_THRESHOLD.
 *
 * Set CLIENT_SIM=false to restore the older server-authoritative loop (60 TPS sim,
 * 30 FPS state snapshots) for debugging or tooling.
 */
import { createHash, randomInt, randomUUID } from "node:crypto";
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize, resolve } from "node:path";
import {
  GAME_CONSTANTS,
  WIN_SCORE,
  applyFlap as applyCoreFlap,
  createGameState,
  stepGameState,
} from "../shared/game-core.js";

const PORT = Number(process.env.PORT || "8787");
const HOST = process.env.HOST || "127.0.0.1";
const SPACE_67_KEYBOARD = parseBoolean(process.env.SPACE_67_KEYBOARD, false);
const DISABLE_ANTI_CHEAT = parseBoolean(process.env.DISABLE_ANTI_CHEAT, false);
const FINAL_FLAG = process.env.FINAL_FLAG || process.env.FLAG || "";
const DIAGNOSTIC_PAGE = parseBoolean(process.env.DIAGNOSTIC_PAGE, false);
const FRONTEND_ROOT = resolve(process.cwd(), "frontend");
const SHARED_ROOT = resolve(process.cwd(), "shared");
const PUBLIC_SHARED_MODULES = new Set(["game-core.js", "frontend-client.js"]);
const MIME_TYPES = new Map([
  [".html", "text/html; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".md", "text/markdown; charset=utf-8"],
  [".svg", "image/svg+xml"],
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".ico", "image/x-icon"],
]);

const GAME_WIDTH = GAME_CONSTANTS.width;
const GAME_HEIGHT = GAME_CONSTANTS.height;
const BIRD_X = GAME_CONSTANTS.birdX;
const BIRD_RADIUS = GAME_CONSTANTS.birdRadius;
const FLOOR_Y = GAME_CONSTANTS.floorY;
const TICK_SECONDS = 1 / 60;
const TICK_MS = TICK_SECONDS * 1000;
const STATE_SEND_MS = 1000 / 30;
const MAX_LAG_COMPENSATION_MS = 200;
const MAX_GESTURE_REPLAY_MS = 420;
const HISTORY_CAPACITY = 16;
const HAND_SAMPLE_HISTORY_CAPACITY = 96;
const CLIENT_SIM = parseBoolean(process.env.CLIENT_SIM, true);
// Runs with claimed score above this value are replay-verified on `finish`.
const VERIFY_SCORE_THRESHOLD = Number(process.env.VERIFY_SCORE_THRESHOLD || "50");
const FLAG_SCORE_HINT = `psss... hearsay the score you need to hit is ${WIN_SCORE}!`;
const PUBLIC_ANTI_CHEAT_FAILURE =
  "Verification failed. Please retry with both hands visible and steady camera framing.";
const PUBLIC_SNAPSHOT_FAILURE = "Snapshot challenge failed. Keep both hands visible.";

/** Player-facing hint from an internal verification rule (no thresholds exposed). */
function verificationPublicMessage(key, detail = "") {
  const normalized = String(detail).toLowerCase();

  if (key === "snapshot") {
    if (normalized.includes("missed")) {
      return "Snapshot challenge missed. Keep both hands visible and respond when prompted.";
    }
    if (normalized.includes("deadline")) {
      return "Snapshot challenge was too slow. Keep both hands in frame and ready.";
    }
    if (normalized.includes("reused")) {
      return "Snapshot image was reused. Use a live camera — don't repeat the same frame.";
    }
    if (normalized.includes("two tracked hands") || normalized.includes("two-hand")) {
      return "Snapshot needed both hands clearly visible in the camera.";
    }
    if (normalized.includes("not enough live camera snapshot challenges")) {
      return "Not enough snapshot challenges completed. Play the full run with the camera active.";
    }
    if (
      normalized.includes("image is missing") ||
      normalized.includes("format is unsupported") ||
      normalized.includes("could not be decoded") ||
      normalized.includes("too small") ||
      normalized.includes("too large") ||
      normalized.includes("dimensions are invalid") ||
      normalized.includes("resolution is too low") ||
      normalized.includes("lacks enough visual detail")
    ) {
      return "Snapshot image was unreadable. Improve lighting and keep both hands in frame.";
    }
    return PUBLIC_SNAPSHOT_FAILURE;
  }

  if (key === "video") {
    if (normalized.includes("too few frames")) {
      return "Not enough camera frames were captured. Keep the game tab active with both hands visible.";
    }
    if (normalized.includes("too sparse")) {
      return "Camera feed was too sparse. Avoid minimizing the tab or pausing the camera.";
    }
    if (normalized.includes("poor median frame cadence")) {
      return "Camera feed was choppy. Use steady lighting and keep hands in frame.";
    }
    if (normalized.includes("repeated long frame gaps")) {
      return "Camera feed stalled or paused. Keep the camera running steadily through the run.";
    }
    if (normalized.includes("cut or large missing-frame gap")) {
      return "Camera feed had a long gap. Don't switch tabs or hide your hands mid-run.";
    }
    if (normalized.includes("too few valid camera images")) {
      return "Too many camera frames were unreadable. Improve lighting and hand visibility.";
    }
    if (normalized.includes("repeat too often")) {
      return "Camera feed looked frozen or duplicated. Use a live camera, not a recording.";
    }
    if (normalized.includes("did not find enough two-hand frames")) {
      return "Both hands weren't visible in enough frames. Center both hands in view.";
    }
    if (normalized.includes("does not match server-extracted")) {
      return "Hand tracking didn't match the camera feed. Retry with a live camera view.";
    }
    if (normalized.includes("too static")) {
      return "Hands didn't move enough in the camera for a real 67 run.";
    }
    if (normalized.includes("cut-frame jump")) {
      return "Hand positions jumped unnaturally in the camera. Keep a steady live view.";
    }
    if (normalized.includes("still or nearly-still")) {
      return "Hands looked mostly still in the camera. Perform visible 67 gestures.";
    }
    if (normalized.includes("not configured")) {
      return "Camera verification is unavailable on the server. Contact the challenge operator.";
    }
    return PUBLIC_ANTI_CHEAT_FAILURE;
  }

  if (key === "landmark") {
    if (normalized.includes("not configured")) {
      return "Hand landmark verification is unavailable on the server. Contact the challenge operator.";
    }
    if (normalized.includes("did not find two hands")) {
      return "Server could not see both hands in enough snapshots. Keep both hands clearly visible.";
    }
    return "Hand landmark check failed. Keep both hands visible with steady lighting.";
  }

  if (key === "coverage") {
    if (normalized.includes("too few hand samples")) {
      return "Hand tracking dropped out too much. Keep both hands in the camera view.";
    }
    if (normalized.includes("too sparse")) {
      return "Hand samples were too sparse. Track steadily through the whole run.";
    }
    return PUBLIC_ANTI_CHEAT_FAILURE;
  }

  if (key === "cadence") {
    if (normalized.includes("not continuous enough")) {
      return "Hand tracking was too irregular. Keep steady framing throughout the run.";
    }
    if (normalized.includes("long gaps")) {
      return "Hand tracking had long pauses. Don't hide hands or leave the camera.";
    }
    if (normalized.includes("implausibly large")) {
      return "Hand tracking had an unusually long gap mid-run. Stay in frame continuously.";
    }
    return PUBLIC_ANTI_CHEAT_FAILURE;
  }

  if (key === "variability") {
    return "Hand positions looked too repetitive. Use natural live hand movement.";
  }

  if (key === "motion") {
    if (normalized.includes("straight constant-speed")) {
      return "Hand movement looked too mechanical. Perform natural 67 gestures.";
    }
    return "Hand movement looked unnatural. Perform real 67 gestures with varied motion.";
  }

  if (key === "timestamps") {
    return "Hand tracking timestamps were invalid. Retry the run without pausing or tabbing away.";
  }

  if (key === "wall-clock") {
    return "Run timing didn't match live play. Complete the run in real time without fast-forwarding.";
  }

  return PUBLIC_ANTI_CHEAT_FAILURE;
}

/** Stable code for logs, solve suite, and support (not shown to casual players by default). */
function verificationFailureCode(key, detail = "") {
  const normalized = String(detail).toLowerCase();
  const rules = {
    video: [
      ["too-few-frames", "too few frames"],
      ["sparse", "too sparse"],
      ["cadence-median", "poor median frame cadence"],
      ["cadence-gaps", "repeated long frame gaps"],
      ["cadence-cut", "cut or large missing-frame gap"],
      ["invalid-images", "too few valid camera images"],
      ["duplicate-frames", "repeat too often"],
      ["two-hand-coverage", "did not find enough two-hand frames"],
      ["client-mismatch", "does not match server-extracted"],
      ["static-motion", "too static"],
      ["cut-jump", "cut-frame jump"],
      ["still-hands", "still or nearly-still"],
      ["unconfigured", "not configured"],
    ],
    snapshot: [
      ["missed", "missed"],
      ["deadline", "deadline"],
      ["reused", "reused"],
      ["two-hands", "two tracked hands"],
      ["insufficient-challenges", "not enough live camera snapshot challenges"],
      ["bad-image", "image is missing"],
      ["bad-image", "format is unsupported"],
      ["bad-image", "could not be decoded"],
      ["bad-image", "too small"],
      ["bad-image", "resolution is too low"],
      ["bad-image", "lacks enough visual detail"],
    ],
    landmark: [
      ["unconfigured", "not configured"],
      ["two-hands", "did not find two hands"],
    ],
    coverage: [
      ["too-few-samples", "too few hand samples"],
      ["sparse", "too sparse"],
    ],
    cadence: [
      ["irregular", "not continuous enough"],
      ["gaps", "long gaps"],
      ["large-gap", "implausibly large"],
    ],
    variability: [["repetitive", "repeat too exactly"]],
    motion: [
      ["repetitive-vectors", "repeat too exactly"],
      ["mechanical", "straight constant-speed"],
    ],
    timestamps: [["burst", "same replay timestamp"]],
    "wall-clock": [["fast-replay", "replayed faster"]],
  };

  const keyRules = rules[key];
  if (keyRules) {
    for (const [slug, needle] of keyRules) {
      if (normalized.includes(needle)) {
        return `${key}:${slug}`;
      }
    }
  }
  return `${key}:unknown`;
}
const SNAPSHOT_CHALLENGES = {
  enabled: parseBoolean(process.env.SNAPSHOT_CHALLENGES, true),
  minRequired: Number(process.env.SNAPSHOT_MIN_REQUIRED || "10"),
  startDelayMs: Number(process.env.SNAPSHOT_START_DELAY_MS || "2500"),
  minIntervalMs: Number(process.env.SNAPSHOT_MIN_INTERVAL_MS || "4500"),
  maxIntervalMs: Number(process.env.SNAPSHOT_MAX_INTERVAL_MS || "9000"),
  deadlineMs: Number(process.env.SNAPSHOT_DEADLINE_MS || "1200"),
  maxOutstanding: 1,
  maxHandSampleOffsetMs: 250,
  maxSnapshotHandDelta: 0.08,
  minBytes: 8000,
  maxBytes: 450000,
  minWidth: 320,
  minHeight: 180,
  minEntropy: 4.2,
  minUniqueBytes: 48,
};
const SNAPSHOT_LANDMARKS = {
  serviceUrl: process.env.HAND_LANDMARK_SERVICE_URL || "",
  mode: process.env.SNAPSHOT_LANDMARK_MODE || "required",
  timeoutMs: Number(process.env.HAND_LANDMARK_TIMEOUT_MS || "1200"),
  maxAnchorDelta: Number(process.env.HAND_LANDMARK_MAX_ANCHOR_DELTA || "0.1"),
};
const VIDEO_VERIFY = {
  mode: process.env.VIDEO_VERIFY_MODE || "required",
  maxFrameMs: Number(process.env.VIDEO_VERIFY_MAX_FRAME_MS || "600000"),
  minFrames: Number(process.env.VIDEO_VERIFY_MIN_FRAMES || "80"),
  minValidFrames: Number(process.env.VIDEO_VERIFY_MIN_VALID_FRAMES || "70"),
  minAverageFps: Number(process.env.VIDEO_VERIFY_MIN_AVERAGE_FPS || "4"),
  maxMedianFrameGapMs: Number(process.env.VIDEO_VERIFY_MAX_MEDIAN_GAP_MS || "320"),
  maxP90FrameGapMs: Number(process.env.VIDEO_VERIFY_MAX_P90_GAP_MS || "900"),
  maxP99FrameGapMs: Number(process.env.VIDEO_VERIFY_MAX_P99_GAP_MS || "1800"),
  maxDuplicateHashRatio: Number(process.env.VIDEO_VERIFY_MAX_DUPLICATE_HASH_RATIO || "0.04"),
  minUniqueHashRatio: Number(process.env.VIDEO_VERIFY_MIN_UNIQUE_HASH_RATIO || "0.72"),
  minMotionRange: Number(process.env.VIDEO_VERIFY_MIN_MOTION_RANGE || "0.18"),
  minMovingFrameRatio: Number(process.env.VIDEO_VERIFY_MIN_MOVING_FRAME_RATIO || "0.28"),
  motionEpsilon: Number(process.env.VIDEO_VERIFY_MOTION_EPSILON || "0.012"),
  maxShortGapJump: Number(process.env.VIDEO_VERIFY_MAX_SHORT_GAP_JUMP || "0.55"),
  shortGapJumpMs: Number(process.env.VIDEO_VERIFY_SHORT_GAP_JUMP_MS || "260"),
  maxClientAnchorDelta: Number(process.env.VIDEO_VERIFY_MAX_CLIENT_ANCHOR_DELTA || "0.14"),
  maxClientFrameOffsetMs: Number(process.env.VIDEO_VERIFY_MAX_CLIENT_FRAME_OFFSET_MS || "300"),
};
const GESTURE_CONFIG = {
  crossThreshold: 0.08,
  minCrossesPerFlap: 2,
  trackingGraceMs: 420,
  anchorSmoothing: 0.45,
  fastAnchorSmoothing: 0.72,
  fastMovementThreshold: 0.075,
  jumpDebounceMs: 150,
  levelResetMs: 360,
};
const ANTI_CHEAT = {
  maxFlapsPerSecond: 8,
  scoreDecayPerSecond: 40,
  blockScore: 150,
  cadenceAudit: {
    minSamples: 12,
    minMeanMs: 88,
    maxStdDevMs: 2,
    maxCv: 0.015,
    score: 35,
    cooldownMs: 2500,
  },
  gestureLeadup: {
    windowMs: 420,
    minSamples: 3,
    maxSampleGapMs: 280,
    missingEvidenceScore: 15,
    cooldownMs: 2000,
  },
  repeatedAmplitude: {
    minSamples: 10,
    minMean: 0.18,
    maxCv: 0.1,
    score: 16,
    cooldownMs: 2000,
  },
  jitterBurst: {
    minSamples: 10,
    maxSpanMs: 20,
    minMean: 0.18,
    score: 160,
    cooldownMs: 1500,
  },
  constantVelocity: {
    minSamples: 10,
    minAbsVelocity: 0.0012,
    maxCv: 0.15,
    minDirectionChanges: 4,
    score: 14,
    cooldownMs: 2000,
  },
  frozenHands: {
    windowMs: 900,
    minSamples: 20,
    minSpanMs: 450,
    maxRange: 1e-5,
    score: 18,
    cooldownMs: 2500,
  },
  cameraTrace: {
    minSamples: 120,
    minAverageSampleHz: 8,
    maxMedianSampleGapMs: 120,
    maxP90SampleGapMs: 280,
    maxP99SampleGapMs: 1200,
    maxSameTimestampSamples: 6,
    minWallClockRatio: 0.82,
    maxWallClockLeadMs: 1800,
    minWallAuditDurationMs: 8000,
    minVariabilitySamples: 80,
    minUniquePairs: 32,
    minUniquePairRatio: 0.16,
  },
  motionTexture: {
    maxVectorGapMs: 120,
    minVectorDistance: 0.0015,
    minActiveVectors: 80,
    minUniqueVectorRatio: 0.22,
    maxCollinearStableRatio: 0.86,
    collinearSine: 0.035,
    maxSpeedChangeRatio: 0.08,
  },
  gestureTemplate: {
    windowMs: 420,
    minSamples: 6,
    bins: 9,
    maxRmsDistance: 0.014,
    repeatThreshold: 3,
    historySize: 24,
    score: 42,
    cooldownMs: 2500,
  },
};

const sockets = new Set();

const server = createServer(async (request, response) => {
  if (!request.url) {
    response.writeHead(400).end("Bad request");
    return;
  }

  const url = new URL(request.url, `http://${request.headers.host}`);
  if (url.pathname === "/api/healthz") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(
      JSON.stringify({
        ok: true,
        sockets: sockets.size,
        space67Keyboard: SPACE_67_KEYBOARD,
        antiCheatEnabled: !DISABLE_ANTI_CHEAT,
        diagnosticPage: DIAGNOSTIC_PAGE,
        clientSim: CLIENT_SIM,
        winScore: WIN_SCORE,
        verifyScoreThreshold: VERIFY_SCORE_THRESHOLD,
        snapshotChallenges: {
          enabled: SNAPSHOT_CHALLENGES.enabled,
          minRequired: SNAPSHOT_CHALLENGES.minRequired,
          deadlineMs: SNAPSHOT_CHALLENGES.deadlineMs,
        },
        snapshotLandmarks: {
          mode: SNAPSHOT_LANDMARKS.mode,
          configured: Boolean(SNAPSHOT_LANDMARKS.serviceUrl),
          maxAnchorDelta: SNAPSHOT_LANDMARKS.maxAnchorDelta,
        },
        videoVerify: {
          mode: VIDEO_VERIFY.mode,
          minFrames: VIDEO_VERIFY.minFrames,
          minValidFrames: VIDEO_VERIFY.minValidFrames,
          minAverageFps: VIDEO_VERIFY.minAverageFps,
        },
      }),
    );
    return;
  }

  if (url.pathname.startsWith("/api/")) {
    response.writeHead(404, { "content-type": "application/json" });
    response.end(JSON.stringify({ error: "Not found" }));
    return;
  }

  await serveFrontend(url.pathname, response);
});

async function serveFrontend(pathname, response) {
  const requestedPath = resolveStaticPath(pathname);
  if (!requestedPath) {
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" }).end("Not found");
    return;
  }

  try {
    const fileStat = await stat(requestedPath);
    if (!fileStat.isFile()) {
      response.writeHead(404, { "content-type": "text/plain; charset=utf-8" }).end("Not found");
      return;
    }

    response.writeHead(200, {
      "content-type": MIME_TYPES.get(extname(requestedPath)) || "application/octet-stream",
      "cache-control": "no-store",
    });
    createReadStream(requestedPath).pipe(response);
  } catch {
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" }).end("Not found");
  }
}

function resolveStaticPath(pathname) {
  if (pathname.startsWith("/shared/")) {
    const sharedRelativePath = normalize(decodeURIComponent(pathname.slice("/shared/".length))).replace(
      /^(\.\.(\/|\\|$))+/,
      "",
    );
    const sharedAbsolutePath = resolve(join(SHARED_ROOT, sharedRelativePath));
    if (!sharedAbsolutePath.startsWith(SHARED_ROOT)) {
      return null;
    }
    const sharedBasename = sharedRelativePath.split(/[/\\]/).pop();
    if (!PUBLIC_SHARED_MODULES.has(sharedBasename)) {
      return null;
    }
    return sharedAbsolutePath;
  }

  let requestedPath = pathname;
  if (requestedPath === "/") {
    requestedPath = "/index.html";
  } else if ((requestedPath === "/diagnostics" || requestedPath === "/diagnostics/") && DIAGNOSTIC_PAGE) {
    requestedPath = "/diagnostics.html";
  } else if (requestedPath === "/diagnostics" || requestedPath === "/diagnostics/" || requestedPath === "/diagnostics.html") {
    return null;
  }

  const normalized = normalize(decodeURIComponent(requestedPath)).replace(/^(\.\.(\/|\\|$))+/, "");
  const absolutePath = resolve(join(FRONTEND_ROOT, normalized));
  if (!absolutePath.startsWith(FRONTEND_ROOT)) {
    return null;
  }

  return absolutePath;
}

server.on("upgrade", (request, socket) => {
  if (request.url && new URL(request.url, `http://${request.headers.host}`).pathname !== "/ws") {
    socket.destroy();
    return;
  }

  const key = request.headers["sec-websocket-key"];
  if (!key || request.headers.upgrade?.toLowerCase() !== "websocket") {
    socket.destroy();
    return;
  }

  const accept = createHash("sha1")
    .update(`${key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`)
    .digest("base64");

  socket.write(
    [
      "HTTP/1.1 101 Switching Protocols",
      "Upgrade: websocket",
      "Connection: Upgrade",
      `Sec-WebSocket-Accept: ${accept}`,
      "",
      "",
    ].join("\r\n"),
  );

  const client = new GameSocket(socket);
  sockets.add(client);
});

server.listen(PORT, HOST, () => {
  console.log(`67 Flight backend listening on http://${HOST}:${PORT}`);
  console.log(`SPACE_67_KEYBOARD=${SPACE_67_KEYBOARD}`);
  console.log(`DISABLE_ANTI_CHEAT=${DISABLE_ANTI_CHEAT}`);
  console.log(`CLIENT_SIM=${CLIENT_SIM}`);
  console.log(`WIN_SCORE=${WIN_SCORE}`);
  console.log(`VERIFY_SCORE_THRESHOLD=${VERIFY_SCORE_THRESHOLD}`);
  console.log(`DIAGNOSTIC_PAGE=${DIAGNOSTIC_PAGE}${DIAGNOSTIC_PAGE ? " (/diagnostics enabled)" : ""}`);
});

setInterval(() => {
  const now = performance.now();
  for (const client of sockets) {
    client.tick(TICK_SECONDS, now);
  }
}, TICK_SECONDS * 1000);

class GameSocket {
  constructor(socket) {
    this.id = randomUUID();
    this.socket = socket;
    this.buffer = Buffer.alloc(0);
    this.closed = false;
    this.lastStateSent = 0;
    this.sessionStartWall = Date.now();
    this.sessionStartPerf = performance.now();
    this.rttMs = 0;
    this.oneWayLagMs = 0;
    this.clockOffsetMs = 0;
    this.game = new GameSession(this.id);
    this.clientSim = CLIENT_SIM;
    this.runLog = [];
    this.runStartPerf = performance.now();
    this.snapshotChallengeSeq = 0;
    this.pendingSnapshotChallenges = new Map();
    this.nextSnapshotChallengeAt = Infinity;
    this.runHasHandSamples = false;
    this.videoFrameSeq = 0;
    this.pendingVideoFrameTasks = new Set();

    socket.on("data", (chunk) => this.receive(chunk));
    socket.on("close", () => this.close());
    socket.on("error", () => this.close());

    this.send({
      type: "welcome",
      id: this.id,
      constants: {
        ...GAME_CONSTANTS,
      },
      config: {
        space67Keyboard: SPACE_67_KEYBOARD,
        antiCheatEnabled: !DISABLE_ANTI_CHEAT,
        clientSim: CLIENT_SIM,
        winScore: WIN_SCORE,
        verifyScoreThreshold: VERIFY_SCORE_THRESHOLD,
        gesture: GESTURE_CONFIG,
        snapshotChallenges: {
          enabled: SNAPSHOT_CHALLENGES.enabled,
          minRequired: SNAPSHOT_CHALLENGES.minRequired,
          deadlineMs: SNAPSHOT_CHALLENGES.deadlineMs,
        },
        snapshotLandmarks: {
          mode: SNAPSHOT_LANDMARKS.mode,
          configured: Boolean(SNAPSHOT_LANDMARKS.serviceUrl),
          maxAnchorDelta: SNAPSHOT_LANDMARKS.maxAnchorDelta,
        },
        videoVerify: {
          mode: VIDEO_VERIFY.mode,
          minFrames: VIDEO_VERIFY.minFrames,
          minValidFrames: VIDEO_VERIFY.minValidFrames,
          minAverageFps: VIDEO_VERIFY.minAverageFps,
        },
      },
      session: {
        best: this.game.best,
      },
    });
    if (this.clientSim) {
      this.beginRunLog();
      this.game.log("Client-sim session started. Inputs are logged for replay verification.", "info");
    } else {
      this.game.log("Server-authoritative room started.", "info");
      this.sendState(performance.now(), true);
    }
  }

  receive(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);

    while (this.buffer.length >= 2) {
      const frame = parseFrame(this.buffer);
      if (!frame) {
        return;
      }
      this.buffer = this.buffer.subarray(frame.bytes);

      if (frame.opcode === 0x8) {
        this.close();
        return;
      }
      if (frame.opcode === 0x9) {
        this.writeFrame(frame.payload, 0xA);
        continue;
      }
      if (frame.opcode !== 0x1) {
        continue;
      }

      try {
        const message = JSON.parse(frame.payload.toString("utf8"));
        this.handleMessage(message);
      } catch {
        this.game.log("Malformed client message ignored.", "warn");
      }
    }
  }

  handleMessage(message) {
    if (!message || typeof message.type !== "string") {
      return;
    }

    if (message.type === "ping") {
      this.handlePing(message);
      return;
    }

    if (message.type === "sync") {
      this.updateLatency(message);
      return;
    }

    if (message.type === "flap") {
      if (this.clientSim) {
        this.recordRunEvent(message);
        return;
      }
      const actionTime = this.clientPerfTime(message.clientTime);
      this.game.flap(message.source === "gesture" ? "67 gesture" : "manual input", actionTime);
      this.sendState(performance.now(), true);
      if (this.game.disconnectReason) {
        this.close(1008, this.game.disconnectReason);
      }
      return;
    }

    if (message.type === "hands") {
      if (this.clientSim) {
        this.recordRunEvent(message);
        return;
      }
      const sampleTime = this.clientPerfTime(message.clientTime);
      const triggered = this.game.processHandSample(message, sampleTime);
      if (triggered) {
        this.sendState(performance.now(), true);
        if (this.game.disconnectReason) {
          this.close(1008, this.game.disconnectReason);
        }
      }
      return;
    }

    if (message.type === "restart") {
      this.game.reset();
      if (this.clientSim) {
        this.beginRunLog();
        this.game.log("Run reset by client.", "info");
        return;
      }
      this.game.log("Run reset by client.", "info");
      this.sendState(performance.now(), true);
      return;
    }

    if (message.type === "snapshot") {
      if (this.clientSim) {
        this.recordSnapshotResponse(message);
      }
      return;
    }

    if (message.type === "video_frame") {
      if (this.clientSim) {
        this.recordVideoFrame(message);
      }
      return;
    }

    if (message.type === "finish") {
      this.handleFinish(message).catch((error) => {
        this.send({
          type: "verified",
          verified: true,
          valid: false,
          score: 0,
          claimedScore: clampInteger(message.score, 0, WIN_SCORE),
          won: false,
          flag: "",
          message: `Verification failed: ${error.message}`,
          hint: FLAG_SCORE_HINT,
          antiCheat: GameSession.failedAntiCheatSnapshot({
            key: "verify-error",
            message: error.message,
            blocked: true,
          }),
        });
      });
    }
  }

  beginRunLog() {
    this.runStartPerf = performance.now();
    this.runLog = [{ type: "restart", atMs: 0, receivedAtMs: 0 }];
    this.snapshotChallengeSeq = 0;
    this.pendingSnapshotChallenges = new Map();
    this.nextSnapshotChallengeAt = Infinity;
    this.runHasHandSamples = false;
    this.videoFrameSeq = 0;
    this.pendingVideoFrameTasks = new Set();
  }

  /** Append a replayable input event while CLIENT_SIM is active. */
  recordRunEvent(message) {
    const receivedAtMs = performance.now() - this.runStartPerf;
    const atMs = Number.isFinite(message.traceAtMs)
      ? clamp(message.traceAtMs, 0, 600000)
      : receivedAtMs;
    const entry = { type: message.type, atMs, receivedAtMs };
    if (message.type === "hands") {
      entry.leftY = message.leftY;
      entry.rightY = message.rightY;
      entry.handCount = message.handCount;
      if (!this.runHasHandSamples) {
        this.runHasHandSamples = true;
        this.nextSnapshotChallengeAt =
          performance.now() + SNAPSHOT_CHALLENGES.startDelayMs;
      }
    } else if (message.type === "flap") {
      entry.source = message.source;
    }
    this.runLog.push(entry);
  }

  recordSnapshotResponse(message) {
    const receivedAtMs = performance.now() - this.runStartPerf;
    const atMs = Number.isFinite(message.traceAtMs)
      ? clamp(message.traceAtMs, 0, 600000)
      : receivedAtMs;
    const challengeId = typeof message.challengeId === "string" ? message.challengeId : "";
    const challenge = this.pendingSnapshotChallenges.get(challengeId);
    const imageAudit = auditSnapshotImage(message.image);
    const entry = {
      type: "snapshot",
      id: challengeId,
      atMs,
      receivedAtMs,
      issuedAtMs: challenge?.issuedAtMs ?? null,
      deadlineAtMs: challenge?.deadlineAtMs ?? null,
      responseLatencyMs: challenge ? receivedAtMs - challenge.issuedAtMs : null,
      leftY: normalizedOrNull(message.leftY),
      rightY: normalizedOrNull(message.rightY),
      handCount: clampInteger(message.handCount, 0, 2),
      image: imageAudit,
      error: typeof message.error === "string" ? message.error.slice(0, 120) : "",
    };

    this.runLog.push(entry);
    if (challenge) {
      this.pendingSnapshotChallenges.delete(challengeId);
      this.scheduleNextSnapshotChallenge(performance.now());
    }

    this.send({
      type: "snapshot_result",
      challengeId,
      accepted: Boolean(challenge) && imageAudit.valid,
      message: Boolean(challenge) && imageAudit.valid ? imageAudit.message : PUBLIC_SNAPSHOT_FAILURE,
    });
  }

  recordVideoFrame(message) {
    const receivedAtMs = performance.now() - this.runStartPerf;
    const atMs = Number.isFinite(message.traceAtMs)
      ? clamp(message.traceAtMs, 0, VIDEO_VERIFY.maxFrameMs)
      : receivedAtMs;
    const imageAudit = auditSnapshotImage(message.image);
    const entry = {
      type: "video_frame",
      id: `${this.id}:video:${++this.videoFrameSeq}`,
      sequence: Number.isFinite(message.sequence)
        ? clampInteger(message.sequence, 0, 10000000)
        : this.videoFrameSeq,
      atMs,
      receivedAtMs,
      leftY: normalizedOrNull(message.leftY),
      rightY: normalizedOrNull(message.rightY),
      handCount: clampInteger(message.handCount, 0, 2),
      image: imageAudit,
      landmarkOk: false,
      landmarkPending: false,
      landmarkMessage: imageAudit.valid ? "pending" : imageAudit.message,
    };

    this.runLog.push(entry);
    if (!imageAudit.valid || SNAPSHOT_LANDMARKS.mode === "off" || !SNAPSHOT_LANDMARKS.serviceUrl) {
      return;
    }

    entry.landmarkPending = true;
    const task = extractSnapshotLandmarks(entry)
      .then((extracted) => {
        entry.landmarkPending = false;
        entry.landmarkOk =
          extracted.ok &&
          extracted.handCount >= 2 &&
          Number.isFinite(extracted.leftY) &&
          Number.isFinite(extracted.rightY);
        entry.landmarkMessage = extracted.ok
          ? "server video landmarks extracted."
          : extracted.message;
        if (entry.landmarkOk) {
          entry.serverLeftY = extracted.leftY;
          entry.serverRightY = extracted.rightY;
          entry.serverHandCount = extracted.handCount;
        }
      })
      .catch((error) => {
        entry.landmarkPending = false;
        entry.landmarkOk = false;
        entry.landmarkMessage = error?.message || "server video landmark extraction failed.";
      })
      .finally(() => {
        this.pendingVideoFrameTasks.delete(task);
      });
    this.pendingVideoFrameTasks.add(task);
  }

  async waitForVideoFrameExtractions() {
    if (this.pendingVideoFrameTasks.size === 0) {
      return;
    }
    await Promise.allSettled([...this.pendingVideoFrameTasks]);
  }

  maybeIssueSnapshotChallenge(now = performance.now()) {
    if (
      !SNAPSHOT_CHALLENGES.enabled ||
      !this.clientSim ||
      !this.runHasHandSamples ||
      this.closed
    ) {
      return;
    }

    for (const [challengeId, challenge] of this.pendingSnapshotChallenges) {
      if (now - this.runStartPerf > challenge.deadlineAtMs) {
        this.pendingSnapshotChallenges.delete(challengeId);
        this.scheduleNextSnapshotChallenge(now);
      }
    }

    if (
      this.pendingSnapshotChallenges.size >= SNAPSHOT_CHALLENGES.maxOutstanding ||
      now < this.nextSnapshotChallengeAt
    ) {
      return;
    }

    const issuedAtMs = now - this.runStartPerf;
    const challengeId = `${this.id}:${++this.snapshotChallengeSeq}`;
    const challenge = {
      id: challengeId,
      issuedAtMs,
      deadlineAtMs: issuedAtMs + SNAPSHOT_CHALLENGES.deadlineMs,
    };
    this.pendingSnapshotChallenges.set(challengeId, challenge);
    this.runLog.push({
      type: "snapshot_challenge",
      id: challengeId,
      atMs: issuedAtMs,
      issuedAtMs,
      deadlineAtMs: challenge.deadlineAtMs,
    });
    this.send({
      type: "snapshot_challenge",
      challengeId,
      serverTime: Date.now(),
      traceAtMs: Math.round(issuedAtMs),
      deadlineMs: SNAPSHOT_CHALLENGES.deadlineMs,
    });
  }

  scheduleNextSnapshotChallenge(now = performance.now()) {
    const min = Math.max(0, Math.round(SNAPSHOT_CHALLENGES.minIntervalMs));
    const max = Math.max(min + 1, Math.round(SNAPSHOT_CHALLENGES.maxIntervalMs));
    this.nextSnapshotChallengeAt = now + randomInt(min, max + 1);
  }

  /** Replay the session log when claimed score exceeds VERIFY_SCORE_THRESHOLD. */
  async handleFinish(message) {
    const claimedScore = clampInteger(message.score, 0, WIN_SCORE);
    if (claimedScore <= VERIFY_SCORE_THRESHOLD) {
      this.send({
        type: "verified",
        valid: true,
        verified: false,
        score: claimedScore,
        claimedScore,
        won: claimedScore >= WIN_SCORE,
        flag: "",
        message: "",
        antiCheat: GameSession.disabledAntiCheatSnapshot(),
      });
      return;
    }

    await this.waitForVideoFrameExtractions();
    const result = await GameSession.verifyRecordedRun(this.runLog, claimedScore);
    if (result.valid) {
      this.game.best = Math.max(this.game.best, result.score);
    }

    if (result.blocked) {
      this.game.log(
        `Verification blocked: ${result.detail || result.message || "anti-cheat failure"}`,
        "warn",
      );
      this.close(1008, result.message || PUBLIC_ANTI_CHEAT_FAILURE);
      return;
    }

    this.send({
      type: "verified",
      verified: true,
      valid: result.valid,
      score: result.score,
      claimedScore,
      won: result.won,
      flag: result.flag,
      message: result.message,
      detail: result.detail || "",
      failureCode: result.failureCode || "",
      hint: FLAG_SCORE_HINT,
      antiCheat: result.antiCheat,
    });
  }

  handlePing(message) {
    const serverRecv = Date.now();
    this.send({
      type: "pong",
      clientTime: message.clientTime,
      serverRecv,
      serverTime: Date.now(),
    });
  }

  updateLatency(message) {
    if (Number.isFinite(message.rttMs)) {
      this.rttMs = clamp(message.rttMs, 0, 2000);
      this.oneWayLagMs = Math.min(this.rttMs / 2, MAX_LAG_COMPENSATION_MS);
    }

    if (Number.isFinite(message.clockOffsetMs)) {
      this.clockOffsetMs = clamp(message.clockOffsetMs, -5000, 5000);
    }
  }

  clientPerfTime(clientTime) {
    const now = performance.now();
    if (!Number.isFinite(clientTime)) {
      return now - this.oneWayLagMs;
    }

    if (this.rttMs === 0) {
      return now;
    }

    const clientAsServerWall = clientTime + this.clockOffsetMs;
    const elapsedWall = clientAsServerWall - this.sessionStartWall;
    return this.sessionStartPerf + elapsedWall - this.oneWayLagMs;
  }

  tick(dt, now) {
    if (this.closed) {
      return;
    }

    if (this.clientSim) {
      this.maybeIssueSnapshotChallenge(now);
      return;
    }
    this.game.tick(dt, now);
    if (now - this.lastStateSent >= STATE_SEND_MS) {
      this.sendState(now);
    }
  }

  sendState(now, force = false) {
    if (!force && now - this.lastStateSent < STATE_SEND_MS) {
      return;
    }
    this.lastStateSent = now;
    this.send({ type: "state", state: this.game.snapshot(), serverTime: Date.now() });
  }

  send(message) {
    if (this.closed) {
      return;
    }
    this.writeFrame(Buffer.from(JSON.stringify(message), "utf8"));
  }

  writeFrame(payload, opcode = 0x1) {
    if (this.closed) {
      return;
    }

    const length = payload.length;
    let header;
    if (length < 126) {
      header = Buffer.from([0x80 | opcode, length]);
    } else if (length < 65536) {
      header = Buffer.alloc(4);
      header[0] = 0x80 | opcode;
      header[1] = 126;
      header.writeUInt16BE(length, 2);
    } else {
      header = Buffer.alloc(10);
      header[0] = 0x80 | opcode;
      header[1] = 127;
      header.writeBigUInt64BE(BigInt(length), 2);
    }
    this.socket.write(Buffer.concat([header, payload]));
  }

  close(code = 1000, reason = "closed") {
    if (this.closed) {
      return;
    }
    sockets.delete(this);

    if (!this.socket.destroyed) {
      const payload = Buffer.alloc(2 + Buffer.byteLength(reason));
      payload.writeUInt16BE(code, 0);
      payload.write(reason, 2);
      this.writeFrame(payload, 0x8);
      this.socket.end();
    }
    this.closed = true;
  }
}

class GameSession {
  constructor(playerId) {
    this.playerId = playerId;
    this.best = 0;
    this.gesture = new ServerGestureInterpreter({
      onFlap: (event) => {
        const triggerAtMs =
          typeof event === "object" && event !== null ? event.triggerAtMs : event;
        this.flap("67 gesture", triggerAtMs);
      },
      config: GESTURE_CONFIG,
    });
    this.history = [];
    this.reset();
  }

  reset() {
    Object.assign(this, createGameState());
    this.disconnectReason = "";
    this.flapTimes = [];
    this.acceptedFlapCount = 0;
    this.handSamples = [];
    this.activeRawHands = [];
    this.antiCheatScore = 0;
    this.antiCheatLastUpdateAt = performance.now();
    this.antiCheatCooldowns = {};
    this.lastSuspicionDetail = "";
    this.lastSuspicionAt = 0;
    this.lastSuspicionKey = "";
    this.gestureSignatures = [];
    if (!this.verifyReplay) {
      this.claimedScore = 0;
    }
    this.history = [];
    this.replaying = false;
    this.gesture.reset();
  }

  antiCheatApplies() {
    if (DISABLE_ANTI_CHEAT || SPACE_67_KEYBOARD) {
      return false;
    }

    return this.score > VERIFY_SCORE_THRESHOLD;
  }

  flap(source, actionTimeMs = performance.now()) {
    if (this.verifyReplay) {
      const verdict = this.auditFlap(source, actionTimeMs);
      if (verdict.blocked) {
        this.gameOver = true;
        this.disconnectReason = verdict.message;
        return;
      }
      if (verdict.message) {
        this.log(verdict.message, verdict.level);
      }
      applyCoreFlap(this, GAME_CONSTANTS);
      this.flapTimes.push(actionTimeMs);
      this.flapTimes = this.flapTimes.slice(-12);
      this.acceptedFlapCount += 1;
      return;
    }

    let preservedHandSamples = null;
    if (this.gameOver) {
      preservedHandSamples = this.handSamples.map((sample) => ({ ...sample }));
      this.reset();
      if (source === "67 gesture" && preservedHandSamples.length > 0) {
        this.handSamples = preservedHandSamples;
      }
      this.log("Run restarted by flap.", "info");
    }

    const now = performance.now();
    const maxReplayMs = source === "67 gesture" ? MAX_GESTURE_REPLAY_MS : MAX_LAG_COMPENSATION_MS;
    const effectiveTime = clamp(
      Number.isFinite(actionTimeMs) ? actionTimeMs : now,
      now - maxReplayMs,
      now,
    );

    if (effectiveTime < now - 1) {
      this.replayTo(effectiveTime, () => this.applyFlapEffect(source, effectiveTime), now);
      return;
    }

    this.applyFlapEffect(source, effectiveTime);
  }

  applyFlapEffect(source, auditTime) {
    const verdict = this.auditFlap(source, auditTime);
    if (verdict.blocked) {
      this.gameOver = true;
      this.disconnectReason = verdict.message;
      this.log(verdict.message, "danger");
      return;
    }

    if (verdict.message) {
      this.log(verdict.message, verdict.level);
    }

    applyCoreFlap(this, GAME_CONSTANTS);
    this.flapTimes.push(auditTime);
    this.flapTimes = this.flapTimes.slice(-12);
    this.acceptedFlapCount += 1;
    this.log(`Accepted flap from ${source}.`, "info");
  }

  processHandSample(message, sampleTime = performance.now()) {
    const sample = {
      leftY: normalizedOrNull(message.leftY),
      rightY: normalizedOrNull(message.rightY),
      handCount: clampInteger(message.handCount, 0, 2),
    };
    const telemetry = this.gesture.process(sample, sampleTime);
    this.recordHandSampleFromTelemetry(telemetry, sampleTime);

    if (
      sample.handCount >= 2 &&
      sample.leftY !== null &&
      sample.rightY !== null &&
      telemetry.tracking === "active"
    ) {
      this.recordActiveRawHandSample(sample.leftY, sample.rightY, sampleTime);
      const verdict = this.auditFrozenHands(sampleTime);
      if (verdict?.blocked) {
        this.gameOver = true;
        this.disconnectReason = verdict.message;
      } else if (verdict?.message) {
        this.log(verdict.message, verdict.level ?? "warn");
      }
    }

    return telemetry.triggered;
  }

  recordHandSampleFromTelemetry(telemetry, now) {
    let leftHeight = telemetry.leftHeight;
    let rightHeight = telemetry.rightHeight;
    let delta = telemetry.delta;

    if (!Number.isFinite(delta) && Number.isFinite(leftHeight) && Number.isFinite(rightHeight)) {
      delta = leftHeight - rightHeight;
    }

    if (
      !Number.isFinite(leftHeight) ||
      !Number.isFinite(rightHeight) ||
      !Number.isFinite(delta)
    ) {
      leftHeight = this.gesture.heights[0];
      rightHeight = this.gesture.heights[1];
      if (Number.isFinite(leftHeight) && Number.isFinite(rightHeight)) {
        delta = leftHeight - rightHeight;
      } else {
        return;
      }
    }

    this.handSamples.push({
      t: now,
      leftHeight,
      rightHeight,
      delta,
    });
    if (this.handSamples.length > HAND_SAMPLE_HISTORY_CAPACITY) {
      this.handSamples.shift();
    }
  }

  recordActiveRawHandSample(leftY, rightY, now) {
    this.activeRawHands.push({ t: now, leftY, rightY });
    const windowStart = now - ANTI_CHEAT.frozenHands.windowMs;
    while (this.activeRawHands.length > 0 && this.activeRawHands[0].t < windowStart) {
      this.activeRawHands.shift();
    }
  }

  auditFrozenHands(now) {
    if (!this.antiCheatApplies()) {
      return null;
    }

    this.decayAntiCheatScore(now);

    const windowStart = now - ANTI_CHEAT.frozenHands.windowMs;
    const recent = this.activeRawHands.filter((sample) => sample.t >= windowStart);
    if (recent.length < ANTI_CHEAT.frozenHands.minSamples) {
      return null;
    }

    const spanMs = recent.at(-1).t - recent[0].t;
    if (spanMs < ANTI_CHEAT.frozenHands.minSpanMs) {
      return null;
    }

    const leftValues = recent.map((sample) => sample.leftY);
    const rightValues = recent.map((sample) => sample.rightY);
    const leftRange = Math.max(...leftValues) - Math.min(...leftValues);
    const rightRange = Math.max(...rightValues) - Math.min(...rightValues);
    if (
      leftRange <= ANTI_CHEAT.frozenHands.maxRange &&
      rightRange <= ANTI_CHEAT.frozenHands.maxRange
    ) {
      return this.addSuspicion(
        ANTI_CHEAT.frozenHands.score,
        "frozen",
        "dual-hand tracking stayed perfectly still for too long.",
        now,
        ANTI_CHEAT.frozenHands.cooldownMs,
      );
    }

    return null;
  }

  recordHistory(now) {
    if (this.replaying) {
      return;
    }

    this.history.push(this.captureSnapshot(now));
    if (this.history.length > HISTORY_CAPACITY) {
      this.history.shift();
    }
  }

  captureSnapshot(now) {
    return {
      t: now,
      birdY: this.birdY,
      velocity: this.velocity,
      elapsed: this.elapsed,
      spawnTimer: this.spawnTimer,
      score: this.score,
      best: this.best,
      gameOver: this.gameOver,
      awaitingStart: this.awaitingStart,
      flapTimes: [...this.flapTimes],
      handSamples: this.handSamples.map((sample) => ({ ...sample })),
      antiCheatScore: this.antiCheatScore,
      antiCheatLastUpdateAt: this.antiCheatLastUpdateAt,
      antiCheatCooldowns: { ...this.antiCheatCooldowns },
      gestureSignatures: this.gestureSignatures.map((signature) => ({ ...signature })),
      nextPipeId: this.nextPipeId,
      pipes: this.pipes.map((pipe) => ({ ...pipe })),
    };
  }

  restoreSnapshot(snapshot) {
    this.birdY = snapshot.birdY;
    this.velocity = snapshot.velocity;
    this.elapsed = snapshot.elapsed;
    this.spawnTimer = snapshot.spawnTimer;
    this.score = snapshot.score;
    this.best = snapshot.best;
    this.gameOver = snapshot.gameOver;
    this.awaitingStart = snapshot.awaitingStart;
    this.flapTimes = [...snapshot.flapTimes];
    this.handSamples = snapshot.handSamples.map((sample) => ({ ...sample }));
    this.antiCheatScore = snapshot.antiCheatScore;
    this.antiCheatLastUpdateAt = snapshot.antiCheatLastUpdateAt;
    this.antiCheatCooldowns = { ...snapshot.antiCheatCooldowns };
    this.gestureSignatures = (snapshot.gestureSignatures || []).map((signature) => ({ ...signature }));
    this.nextPipeId = snapshot.nextPipeId;
    this.pipes = snapshot.pipes.map((pipe) => ({ ...pipe }));
  }

  findSnapshotAtOrBefore(targetMs) {
    let best = null;
    for (const snapshot of this.history) {
      if (snapshot.t <= targetMs && (!best || snapshot.t > best.t)) {
        best = snapshot;
      }
    }
    return best;
  }

  replayTo(targetMs, applyAction, endMs) {
    const snapshot = this.findSnapshotAtOrBefore(targetMs);
    if (!snapshot) {
      applyAction();
      return;
    }

    this.replaying = true;
    try {
      this.restoreSnapshot(snapshot);
      let t = snapshot.t;

      while (t + TICK_MS <= targetMs && !this.gameOver) {
        this.tick(TICK_SECONDS, t + TICK_MS);
        t += TICK_MS;
      }

      if (!this.gameOver) {
        applyAction();
      }

      while (t + TICK_MS <= endMs && !this.gameOver) {
        this.tick(TICK_SECONDS, t + TICK_MS);
        t += TICK_MS;
      }

      const remainingMs = endMs - t;
      if (remainingMs > 0.5 && !this.gameOver) {
        this.tick(remainingMs / 1000, endMs);
      }
    } finally {
      this.replaying = false;
      this.history = [];
    }
  }

  auditFlap(source, now) {
    if (this.verifyReplay && source !== "67 gesture") {
      return {
        blocked: true,
        message:
          "Verification failed: explicit manual flaps are not valid camera-gesture evidence.",
      };
    }

    if (!this.antiCheatApplies()) {
      return { blocked: false };
    }

    this.decayAntiCheatScore(now);

    const recent = this.flapTimes.filter((time) => now - time < 1000);
    if (recent.length >= ANTI_CHEAT.maxFlapsPerSecond) {
      return {
        blocked: true,
        message: "Disconnected: biological speed limit exceeded.",
      };
    }

    if (this.flapTimes.length >= ANTI_CHEAT.cadenceAudit.minSamples) {
      const sample = [...this.flapTimes.slice(-9), now];
      const deltas = sample.slice(1).map((time, index) => time - sample[index]);
      const meanDelta = average(deltas);
      const deviation = standardDeviation(deltas);
      const coefficient = coefficientOfVariation(deltas);
      if (
        meanDelta >= ANTI_CHEAT.cadenceAudit.minMeanMs &&
        deviation <= ANTI_CHEAT.cadenceAudit.maxStdDevMs &&
        coefficient <= ANTI_CHEAT.cadenceAudit.maxCv
      ) {
        const verdict = this.addSuspicion(
          ANTI_CHEAT.cadenceAudit.score,
          "cadence",
          "perfect timing quantization detected.",
          now,
          ANTI_CHEAT.cadenceAudit.cooldownMs,
        );
        if (verdict) {
          return verdict;
        }
      }
    }

    if (source === "67 gesture") {
      const verdict = this.auditGestureLeadup(now);
      if (verdict) {
        return verdict;
      }
    }

    return { blocked: false };
  }

  decayAntiCheatScore(now) {
    if (!Number.isFinite(this.antiCheatLastUpdateAt)) {
      this.antiCheatLastUpdateAt = now;
      return;
    }

    const elapsedMs = Math.max(0, now - this.antiCheatLastUpdateAt);
    this.antiCheatLastUpdateAt = now;
    const decay = (elapsedMs / 1000) * ANTI_CHEAT.scoreDecayPerSecond;
    this.antiCheatScore = Math.max(0, this.antiCheatScore - decay);
  }

  addSuspicion(score, key, detail, now, cooldownMs) {
    const lastHit = this.antiCheatCooldowns[key] ?? -Infinity;
    if (now - lastHit < cooldownMs) {
      return null;
    }

    this.antiCheatCooldowns[key] = now;
    this.antiCheatScore += score;
    this.lastSuspicionDetail = detail;
    this.lastSuspicionAt = now;
    this.lastSuspicionKey = key;
    this.log(`Anti-cheat suspicion +${score}: ${detail} (score=${this.antiCheatScore.toFixed(1)}).`, "warn");
    if (this.antiCheatScore >= ANTI_CHEAT.blockScore) {
      return {
        blocked: true,
        message: "Disconnected: anti-cheat heuristics flagged scripted inputs.",
      };
    }
    return {
      blocked: false,
      warned: true,
      level: "warn",
      message: `Suspicious input detected: ${detail}`,
    };
  }

  static disabledAntiCheatSnapshot() {
    return {
      enabled: false,
      score: 0,
      blockScore: ANTI_CHEAT.blockScore,
      level: "disabled",
      message: "",
      lastHeuristic: "",
    };
  }

  static failedAntiCheatSnapshot({
    key = "",
    message = "",
    blocked = false,
    failureCode = "",
  } = {}) {
    return {
      enabled: !DISABLE_ANTI_CHEAT,
      score: blocked ? ANTI_CHEAT.blockScore : 0,
      blockScore: ANTI_CHEAT.blockScore,
      level: blocked ? "blocked" : "warning",
      message: blocked ? message || PUBLIC_ANTI_CHEAT_FAILURE : message,
      lastHeuristic: blocked ? failureCode || key || "anti-cheat" : key,
    };
  }

  antiCheatSnapshot() {
    if (DISABLE_ANTI_CHEAT) {
      return GameSession.disabledAntiCheatSnapshot();
    }

    if (!this.antiCheatApplies()) {
      return GameSession.disabledAntiCheatSnapshot();
    }

    const score = this.antiCheatScore;
    const blockScore = ANTI_CHEAT.blockScore;
    let level = "none";
    if (this.disconnectReason) {
      level = "blocked";
    } else if (score >= blockScore * 0.7) {
      level = "critical";
    } else if (score >= blockScore * 0.25) {
      level = "warning";
    }

    return {
      enabled: true,
      score: Math.round(score * 10) / 10,
      blockScore,
      level,
      message: this.disconnectReason || (score > 0 ? this.lastSuspicionDetail : "") || "",
      lastHeuristic: this.lastSuspicionKey || "",
    };
  }

  auditGestureLeadup(now) {
    const recentTrackingMs = now - this.gesture.lastSeenAt;
    const windowStart = now - ANTI_CHEAT.gestureLeadup.windowMs;
    const recent = this.handSamples.filter((sample) => sample.t >= windowStart && sample.t <= now);
    const lastSample = recent.at(-1);
    const motionGapMs = lastSample ? now - lastSample.t : Infinity;
    const hadRecentHandTracking = recentTrackingMs <= GESTURE_CONFIG.trackingGraceMs;
    const sparseSamples =
      recent.length < ANTI_CHEAT.gestureLeadup.minSamples ||
      !lastSample ||
      motionGapMs > ANTI_CHEAT.gestureLeadup.maxSampleGapMs;

    if (sparseSamples && !hadRecentHandTracking) {
      return this.addSuspicion(
        ANTI_CHEAT.gestureLeadup.missingEvidenceScore,
        "leadup",
        "gesture flap arrived with sparse recent hand-motion evidence.",
        now,
        ANTI_CHEAT.gestureLeadup.cooldownMs,
      );
    }

    if (recent.length < 2) {
      return null;
    }

    const templateVerdict = this.auditGestureTemplate(recent, now);
    if (templateVerdict) {
      return templateVerdict;
    }

    const excursionAmplitudes = recent
      .map((sample) => Math.abs(sample.delta))
      .filter((amplitude) => amplitude >= GESTURE_CONFIG.crossThreshold * 1.25);
    const excursionSamples = recent.filter(
      (sample) => Math.abs(sample.delta) >= GESTURE_CONFIG.crossThreshold * 1.25,
    );
    if (excursionSamples.length >= ANTI_CHEAT.jitterBurst.minSamples) {
      const spanMs = excursionSamples.at(-1).t - excursionSamples[0].t;
      const meanAmplitude = average(excursionSamples.map((sample) => Math.abs(sample.delta)));
      if (
        spanMs <= ANTI_CHEAT.jitterBurst.maxSpanMs &&
        meanAmplitude >= ANTI_CHEAT.jitterBurst.minMean
      ) {
        const verdict = this.addSuspicion(
          ANTI_CHEAT.jitterBurst.score,
          "jitter",
          "mechanical hand jitter burst before gesture flap.",
          now,
          ANTI_CHEAT.jitterBurst.cooldownMs,
        );
        if (verdict) {
          return verdict;
        }
      }
    }
    if (excursionAmplitudes.length >= ANTI_CHEAT.repeatedAmplitude.minSamples) {
      const meanAmplitude = average(excursionAmplitudes);
      const amplitudeCv = coefficientOfVariation(excursionAmplitudes);
      if (
        meanAmplitude >= ANTI_CHEAT.repeatedAmplitude.minMean &&
        amplitudeCv <= ANTI_CHEAT.repeatedAmplitude.maxCv
      ) {
        const verdict = this.addSuspicion(
          ANTI_CHEAT.repeatedAmplitude.score,
          "amplitude",
          "repeated near-identical gesture amplitudes.",
          now,
          ANTI_CHEAT.repeatedAmplitude.cooldownMs,
        );
        if (verdict) {
          return verdict;
        }
      }
    }

    const velocityFeatures = deltaVelocityFeatures(recent);
    if (
      velocityFeatures.count >= ANTI_CHEAT.constantVelocity.minSamples &&
      velocityFeatures.meanAbs >= ANTI_CHEAT.constantVelocity.minAbsVelocity &&
      velocityFeatures.directionChanges >= ANTI_CHEAT.constantVelocity.minDirectionChanges &&
      velocityFeatures.cv <= ANTI_CHEAT.constantVelocity.maxCv
    ) {
      const verdict = this.addSuspicion(
        ANTI_CHEAT.constantVelocity.score,
        "velocity",
        "hand deltas oscillated at near-constant speed.",
        now,
        ANTI_CHEAT.constantVelocity.cooldownMs,
      );
      if (verdict) {
        return verdict;
      }
    }

    return null;
  }

  auditGestureTemplate(recent, now) {
    const signature = gestureLeadupSignature(
      recent,
      now,
      ANTI_CHEAT.gestureTemplate.windowMs,
      ANTI_CHEAT.gestureTemplate.bins,
      ANTI_CHEAT.gestureTemplate.minSamples,
    );
    if (!signature) {
      return null;
    }

    const closeMatches = this.gestureSignatures.filter(
      (previous) =>
        gestureSignatureDistance(previous.values, signature.values) <=
        ANTI_CHEAT.gestureTemplate.maxRmsDistance,
    ).length;

    this.gestureSignatures.push(signature);
    this.gestureSignatures = this.gestureSignatures.slice(-ANTI_CHEAT.gestureTemplate.historySize);

    if (closeMatches >= ANTI_CHEAT.gestureTemplate.repeatThreshold) {
      return this.addSuspicion(
        ANTI_CHEAT.gestureTemplate.score,
        "template",
        "gesture leadup repeats the same movement template too closely.",
        now,
        ANTI_CHEAT.gestureTemplate.cooldownMs,
      );
    }

    return null;
  }

  tick(dt, now) {
    if (this.gameOver || this.awaitingStart) {
      return;
    }

    const previousScore = this.score;
    const wasGameOver = this.gameOver;
    stepGameState(this, dt, GAME_CONSTANTS);
    if (this.score > previousScore) {
      this.best = Math.max(this.best, this.score);
    }

    if (!wasGameOver && this.gameOver) {
      this.log("Collision.", "danger");
    }

    this.recordHistory(now);
  }
  snapshot() {
    return {
      birdY: this.birdY,
      velocity: this.velocity,
      score: this.score,
      best: this.best,
      won: this.score >= WIN_SCORE,
      flag: this.score >= WIN_SCORE ? FINAL_FLAG : "",
      acceptedFlapCount: this.acceptedFlapCount,
      elapsed: this.elapsed,
      spawnTimer: this.spawnTimer,
      nextPipeId: this.nextPipeId,
      gameOver: this.gameOver,
      awaitingStart: this.awaitingStart,
      gesture: this.gesture.snapshot(),
      antiCheat: this.antiCheatSnapshot(),
      pipes: this.pipes.map((pipe) => ({
        id: pipe.id,
        x: pipe.x,
        gapY: pipe.gapY,
        scored: pipe.scored,
      })),
    };
  }

  log(message, level = "info") {
    console.log(`[${level}] ${this.playerId}: ${message}`);
  }

  static auditServerVideoStream(events) {
    if (DISABLE_ANTI_CHEAT || SPACE_67_KEYBOARD || VIDEO_VERIFY.mode === "off") {
      return null;
    }

    if (!SNAPSHOT_LANDMARKS.serviceUrl && VIDEO_VERIFY.mode === "required") {
      return cameraTraceBlocked("video", "server-side video landmark extractor is not configured.");
    }

    const frames = events
      .filter((event) => event.type === "video_frame")
      .sort((left, right) => left.atMs - right.atMs);
    if (frames.length < VIDEO_VERIFY.minFrames) {
      return cameraTraceBlocked("video", "server video stream has too few frames for verification.");
    }

    const firstFrame = frames[0];
    const lastFrame = frames.at(-1);
    const durationMs = Math.max(0, lastFrame.atMs - firstFrame.atMs);
    const requiredFrames = Math.max(
      VIDEO_VERIFY.minFrames,
      Math.floor((durationMs / 1000) * VIDEO_VERIFY.minAverageFps),
    );
    if (frames.length < requiredFrames) {
      return cameraTraceBlocked("video", "server video stream is too sparse for a live run.");
    }

    const frameGaps = positiveDeltas(frames.map((frame) => frame.atMs));
    if (frameGaps.length > 0) {
      if (percentile(frameGaps, 0.5) > VIDEO_VERIFY.maxMedianFrameGapMs) {
        return cameraTraceBlocked("video", "server video stream has poor median frame cadence.");
      }
      if (percentile(frameGaps, 0.9) > VIDEO_VERIFY.maxP90FrameGapMs) {
        return cameraTraceBlocked("video", "server video stream has repeated long frame gaps.");
      }
      if (percentile(frameGaps, 0.99) > VIDEO_VERIFY.maxP99FrameGapMs) {
        return cameraTraceBlocked("video", "server video stream has a cut or large missing-frame gap.");
      }
    }

    const imageFrames = frames.filter((frame) => frame.image?.valid);
    if (imageFrames.length < VIDEO_VERIFY.minValidFrames) {
      return cameraTraceBlocked("video", "server video stream has too few valid camera images.");
    }

    const hashes = imageFrames.map((frame) => frame.image.hash).filter(Boolean);
    const uniqueHashes = new Set(hashes).size;
    const duplicateRatio = hashes.length > 0 ? 1 - uniqueHashes / hashes.length : 1;
    const uniqueHashRatio = hashes.length > 0 ? uniqueHashes / hashes.length : 0;
    if (
      duplicateRatio > VIDEO_VERIFY.maxDuplicateHashRatio ||
      uniqueHashRatio < VIDEO_VERIFY.minUniqueHashRatio
    ) {
      return cameraTraceBlocked("video", "server video frames repeat too often for live camera input.");
    }

    const serverHands = GameSession.serverVideoHandFrames(events);
    if (serverHands.length < VIDEO_VERIFY.minValidFrames) {
      return cameraTraceBlocked("video", "server video landmark extraction did not find enough two-hand frames.");
    }

    const cutVerdict = GameSession.auditServerVideoContinuity(serverHands);
    if (cutVerdict) {
      return cutVerdict;
    }

    return null;
  }

  static serverVideoHandFrames(events) {
    return events
      .filter(
        (event) =>
          event.type === "video_frame" &&
          event.landmarkOk &&
          event.serverHandCount >= 2 &&
          Number.isFinite(event.serverLeftY) &&
          Number.isFinite(event.serverRightY),
      )
      .map((event) => ({
        type: "hands",
        atMs: event.atMs,
        receivedAtMs: event.receivedAtMs,
        leftY: event.serverLeftY,
        rightY: event.serverRightY,
        handCount: 2,
        source: "server-video",
      }))
      .sort((left, right) => left.atMs - right.atMs);
  }

  static canonicalizeEventsFromServerVideo(events) {
    return events;
  }

  static auditVideoClientAnchorAgreement(events, serverHands) {
    const clientHands = events
      .filter(
        (event) =>
          event.type === "hands" &&
          event.handCount >= 2 &&
          Number.isFinite(event.leftY) &&
          Number.isFinite(event.rightY),
      )
      .sort((left, right) => left.atMs - right.atMs);

    if (clientHands.length === 0) {
      return null;
    }

    let compared = 0;
    let mismatches = 0;
    for (const frame of serverHands) {
      const sample = nearestHandSampleAt(clientHands, frame.atMs, VIDEO_VERIFY.maxClientFrameOffsetMs);
      if (!sample) {
        continue;
      }
      compared += 1;
      if (
        Math.abs(sample.leftY - frame.leftY) > VIDEO_VERIFY.maxClientAnchorDelta ||
        Math.abs(sample.rightY - frame.rightY) > VIDEO_VERIFY.maxClientAnchorDelta
      ) {
        mismatches += 1;
      }
    }

    if (compared >= Math.min(20, serverHands.length) && mismatches / compared > 0.18) {
      return cameraTraceBlocked("video", "client hand trace does not match server-extracted video landmarks.");
    }
    return null;
  }

  static auditServerVideoContinuity(serverHands) {
    const leftValues = serverHands.map((frame) => frame.leftY);
    const rightValues = serverHands.map((frame) => frame.rightY);
    const motionRange =
      Math.max(...leftValues) - Math.min(...leftValues) +
      Math.max(...rightValues) - Math.min(...rightValues);
    if (motionRange < VIDEO_VERIFY.minMotionRange) {
      return cameraTraceBlocked("video", "server video landmarks are too static for a human 67 run.");
    }

    let compared = 0;
    let moving = 0;
    for (let index = 1; index < serverHands.length; index += 1) {
      const previous = serverHands[index - 1];
      const current = serverHands[index];
      const dt = current.atMs - previous.atMs;
      if (dt <= 0) {
        continue;
      }
      const distance = Math.hypot(
        current.leftY - previous.leftY,
        current.rightY - previous.rightY,
      );
      compared += 1;
      if (distance >= VIDEO_VERIFY.motionEpsilon) {
        moving += 1;
      }
      if (dt <= VIDEO_VERIFY.shortGapJumpMs && distance > VIDEO_VERIFY.maxShortGapJump) {
        return cameraTraceBlocked("video", "server video landmarks contain an implausible cut-frame jump.");
      }
    }

    if (compared > 0 && moving / compared < VIDEO_VERIFY.minMovingFrameRatio) {
      return cameraTraceBlocked("video", "server video landmarks look like still or nearly-still hand images.");
    }

    return auditHumanMotionTexture(serverHands);
  }

  static async auditSnapshotChallenges(events) {
    if (!SNAPSHOT_CHALLENGES.enabled || DISABLE_ANTI_CHEAT || SPACE_67_KEYBOARD) {
      return null;
    }

    const challenges = events.filter((event) => event.type === "snapshot_challenge");
    const snapshots = events.filter((event) => event.type === "snapshot");
    if (challenges.length < SNAPSHOT_CHALLENGES.minRequired) {
      return cameraTraceBlocked("snapshot", "not enough live camera snapshot challenges were completed.");
    }

    const snapshotsById = new Map(snapshots.map((snapshot) => [snapshot.id, snapshot]));
    const seenHashes = new Set();
    let acceptedLandmarkSnapshots = 0;
    let lastLandmarkVerdict = null;
    for (const challenge of challenges) {
      const snapshot = snapshotsById.get(challenge.id);
      if (!snapshot) {
        return cameraTraceBlocked("snapshot", "live camera snapshot challenge was missed.");
      }

      if (
        Number.isFinite(snapshot.responseLatencyMs) &&
        snapshot.responseLatencyMs > SNAPSHOT_CHALLENGES.deadlineMs
      ) {
        return cameraTraceBlocked("snapshot", "live camera snapshot arrived after the challenge deadline.");
      }
      if (
        Number.isFinite(snapshot.receivedAtMs) &&
        Number.isFinite(challenge.deadlineAtMs) &&
        snapshot.receivedAtMs > challenge.deadlineAtMs
      ) {
        return cameraTraceBlocked("snapshot", "live camera snapshot arrived after the challenge deadline.");
      }

      if (!snapshot.image?.valid) {
        return cameraTraceBlocked(
          "snapshot",
          snapshot.image?.message || "live camera snapshot image failed validation.",
        );
      }

      const landmarkVerdict = await auditSnapshotLandmarks(snapshot);
      if (landmarkVerdict) {
        lastLandmarkVerdict = landmarkVerdict;
      } else {
        acceptedLandmarkSnapshots += 1;
      }

      if (seenHashes.has(snapshot.image.hash)) {
        return cameraTraceBlocked("snapshot", "live camera snapshot image was reused.");
      }
      seenHashes.add(snapshot.image.hash);

      if (
        snapshot.handCount < 2 ||
        !Number.isFinite(snapshot.leftY) ||
        !Number.isFinite(snapshot.rightY)
      ) {
        return cameraTraceBlocked("snapshot", "live camera snapshot did not include two tracked hands.");
      }

    }

    if (
      SNAPSHOT_LANDMARKS.mode === "required" &&
      SNAPSHOT_LANDMARKS.serviceUrl &&
      acceptedLandmarkSnapshots < SNAPSHOT_CHALLENGES.minRequired
    ) {
      return (
        lastLandmarkVerdict ||
        cameraTraceBlocked("landmark", "not enough live camera snapshots produced two-hand landmarks.")
      );
    }

    return null;
  }

  static auditRecordedCameraTrace(events) {
    const gameplayEvents = events.filter((event) => event.type !== "restart");
    const explicitFlap = gameplayEvents.find((event) => event.type === "flap");
    if (explicitFlap && !SPACE_67_KEYBOARD) {
      return {
        blocked: false,
        key: "explicit-flap",
        message:
          "Verification failed: camera runs must derive flaps from hand samples; explicit flap events are not trusted.",
      };
    }

    if (DISABLE_ANTI_CHEAT || SPACE_67_KEYBOARD) {
      return null;
    }

    const hands = gameplayEvents
      .filter((event) => event.type === "hands")
      .sort((left, right) => left.atMs - right.atMs);
    if (hands.length < ANTI_CHEAT.cameraTrace.minSamples) {
      return cameraTraceBlocked("coverage", "camera trace has too few hand samples for a verified run.");
    }

    const firstHand = hands[0];
    const lastHand = hands.at(-1);
    const durationMs = Math.max(0, lastHand.atMs - firstHand.atMs);
    const requiredSamples = Math.max(
      ANTI_CHEAT.cameraTrace.minSamples,
      Math.floor((durationMs / 1000) * ANTI_CHEAT.cameraTrace.minAverageSampleHz),
    );
    if (hands.length < requiredSamples) {
      return cameraTraceBlocked("coverage", "camera trace is too sparse for a human-paced run.");
    }

    const timestampBurst = maxSameTimestampRun(hands);
    if (timestampBurst > ANTI_CHEAT.cameraTrace.maxSameTimestampSamples) {
      return cameraTraceBlocked("timestamps", "too many hand samples share the same replay timestamp.");
    }

    const sampleGaps = positiveDeltas(hands.map((event) => event.atMs));
    if (sampleGaps.length > 0) {
      const medianGap = percentile(sampleGaps, 0.5);
      const p90Gap = percentile(sampleGaps, 0.9);
      const p99Gap = percentile(sampleGaps, 0.99);
      if (medianGap > ANTI_CHEAT.cameraTrace.maxMedianSampleGapMs) {
        return cameraTraceBlocked("cadence", "camera samples are not continuous enough for verification.");
      }
      if (p90Gap > ANTI_CHEAT.cameraTrace.maxP90SampleGapMs) {
        return cameraTraceBlocked("cadence", "camera trace has repeated long gaps between hand samples.");
      }
      if (p99Gap > ANTI_CHEAT.cameraTrace.maxP99SampleGapMs) {
        return cameraTraceBlocked("cadence", "camera trace has implausibly large hand-sample gaps.");
      }
    }

    const pairedHands = hands.filter(
      (event) =>
        event.handCount >= 2 &&
        Number.isFinite(event.leftY) &&
        Number.isFinite(event.rightY),
    );
    if (pairedHands.length >= ANTI_CHEAT.cameraTrace.minVariabilitySamples) {
      const uniquePairs = new Set(
        pairedHands.map((event) => `${event.leftY.toFixed(4)}:${event.rightY.toFixed(4)}`),
      ).size;
      const uniqueRatio = uniquePairs / pairedHands.length;
      if (
        uniquePairs < ANTI_CHEAT.cameraTrace.minUniquePairs ||
        uniqueRatio < ANTI_CHEAT.cameraTrace.minUniquePairRatio
      ) {
        return cameraTraceBlocked("variability", "hand positions repeat too exactly for live camera input.");
      }
    }

    const motionTextureVerdict = auditHumanMotionTexture(pairedHands);
    if (motionTextureVerdict) {
      return motionTextureVerdict;
    }

    const timedHands = hands.filter(
      (event) => Number.isFinite(event.receivedAtMs) && Number.isFinite(event.atMs),
    );
    if (timedHands.length >= 2) {
      const firstTimed = timedHands[0];
      const lastTimed = timedHands.at(-1);
      const traceElapsedMs = lastTimed.atMs - firstTimed.atMs;
      const wallElapsedMs = lastTimed.receivedAtMs - firstTimed.receivedAtMs;
      if (
        traceElapsedMs >= ANTI_CHEAT.cameraTrace.minWallAuditDurationMs &&
        wallElapsedMs + ANTI_CHEAT.cameraTrace.maxWallClockLeadMs <
        traceElapsedMs * ANTI_CHEAT.cameraTrace.minWallClockRatio
      ) {
        return cameraTraceBlocked("wall-clock", "camera trace was replayed faster than live human input.");
      }
    }

    return null;
  }

  /** Deterministic replay of a client-sim input log for score + anti-cheat validation. */
  static async verifyRecordedRun(runLog, claimedScore) {
    const rawEvents = [...runLog].sort((left, right) => left.atMs - right.atMs);
    const videoVerdict = GameSession.auditServerVideoStream(rawEvents);
    if (videoVerdict) {
      return {
        valid: false,
        blocked: videoVerdict.blocked,
        score: 0,
        won: false,
        flag: "",
        message: publicVerdictMessage(videoVerdict),
        detail: detailedVerdictMessage(videoVerdict),
        failureCode: videoVerdict.failureCode || "",
        antiCheat: GameSession.failedAntiCheatSnapshot(videoVerdict),
      };
    }

    const events = GameSession.canonicalizeEventsFromServerVideo(rawEvents);
    const snapshotVerdict = await GameSession.auditSnapshotChallenges(events);
    if (snapshotVerdict) {
      return {
        valid: false,
        blocked: snapshotVerdict.blocked,
        score: 0,
        won: false,
        flag: "",
        message: publicVerdictMessage(snapshotVerdict),
        detail: detailedVerdictMessage(snapshotVerdict),
        failureCode: snapshotVerdict.failureCode || "",
        antiCheat: GameSession.failedAntiCheatSnapshot(snapshotVerdict),
      };
    }

    const traceVerdict = GameSession.auditRecordedCameraTrace(events);
    if (traceVerdict) {
      return {
        valid: false,
        blocked: traceVerdict.blocked,
        score: 0,
        won: false,
        flag: "",
        message: publicVerdictMessage(traceVerdict),
        detail: detailedVerdictMessage(traceVerdict),
        failureCode: traceVerdict.failureCode || "",
        antiCheat: GameSession.failedAntiCheatSnapshot(traceVerdict),
      };
    }

    const replay = new GameSession("verify");
    replay.reset();
    replay.verifyReplay = true;
    replay.claimedScore = claimedScore;
    const pendingGestureFlaps = [];
    replay.gesture.onFlap = (event) => {
      pendingGestureFlaps.push(event);
    };

    let simMs = 0;

    const advanceTo = (targetMs) => {
      while (simMs + TICK_MS <= targetMs && !replay.gameOver) {
        if (!replay.awaitingStart) {
          replay.tick(TICK_SECONDS, simMs + TICK_MS);
        }
        simMs += TICK_MS;
      }

      const remainingMs = targetMs - simMs;
      if (remainingMs > 0.5 && !replay.gameOver && !replay.awaitingStart) {
        replay.tick(remainingMs / 1000, targetMs);
        simMs = targetMs;
      }
    };

    for (const event of events) {
      if (event.type === "restart") {
        replay.reset();
        replay.gesture.onFlap = (flapEvent) => {
          pendingGestureFlaps.push(flapEvent);
        };
        pendingGestureFlaps.length = 0;
        simMs = event.atMs;
        continue;
      }

      if (event.type === "hands") {
        replay.processHandSample(
          {
            leftY: event.leftY,
            rightY: event.rightY,
            handCount: event.handCount,
          },
          event.atMs,
        );
        while (pendingGestureFlaps.length > 0) {
          const flapEvent = pendingGestureFlaps.shift();
          advanceTo(flapEvent.triggerAtMs);
          replay.flap("67 gesture", flapEvent.triggerAtMs);
          if (replay.disconnectReason || replay.gameOver) {
            break;
          }
        }
        if (replay.disconnectReason) {
          break;
        }
        continue;
      }

      if (event.type === "flap") {
        if (!SPACE_67_KEYBOARD) {
          replay.disconnectReason =
            "Verification failed: explicit flap events are not valid camera input.";
          break;
        }
        advanceTo(event.atMs);
        replay.flap(event.source === "gesture" ? "67 gesture" : "manual input", event.atMs);
        if (replay.disconnectReason) {
          break;
        }
      }
    }

    const lastEventAtMs = events.at(-1)?.atMs;
    if (!replay.gameOver && Number.isFinite(lastEventAtMs)) {
      advanceTo(lastEventAtMs);
    }

    const score = replay.score;
    const won = score >= WIN_SCORE;
    const valid = score === claimedScore && !replay.disconnectReason;
    let message = "";
    if (replay.disconnectReason) {
      message = replay.disconnectReason;
    } else if (!valid) {
      message = `Verification failed: replay score ${score} does not match claimed ${claimedScore}.`;
    }

    return {
      valid,
      blocked: replay.disconnectReason.startsWith("Disconnected:"),
      score,
      won,
      flag: won ? FINAL_FLAG : "",
      message,
      antiCheat: replay.antiCheatSnapshot(),
    };
  }
}

class ServerGestureInterpreter {
  constructor({ onFlap = () => { }, config = {} } = {}) {
    this.config = { ...GESTURE_CONFIG, ...config };
    this.onFlap = onFlap;
    this.reset();
  }

  reset() {
    this.previousState = "NEUTRAL";
    this.crossedLevelBand = false;
    this.crossCount = 0;
    this.sequenceStartedAt = null;
    this.lastJumpAt = -Infinity;
    this.lastCrossAt = -Infinity;
    this.levelEnteredAt = null;
    this.lastSeenAt = 0;
    this.heights = [null, null];
    this.heightVelocities = [0, 0];
    this.lastHeightTimes = [null, null];
    this.telemetry = {
      status: "NEUTRAL",
      handCount: 0,
      tracking: "reset",
      delta: null,
      triggered: false,
    };
  }

  process(sample, now = performance.now()) {
    const resolved = this.resolveSample(sample, now);
    if (!resolved) {
      return this.holdOrReset(now, sample.handCount);
    }

    const { leftHeight, rightHeight, tracking } = resolved;
    if (sample.handCount >= 2) {
      this.lastSeenAt = now;
    }

    const delta = leftHeight - rightHeight;
    const currentState = this.deltaState(delta);
    if (currentState === "LEVEL") {
      if (this.levelEnteredAt === null) {
        this.levelEnteredAt = now;
      }
      if (this.previousState !== "NEUTRAL") {
        this.crossedLevelBand = true;
        if (this.crossCount === 0 && this.sequenceStartedAt === null) {
          this.sequenceStartedAt = now;
        }
      }
      const levelElapsedMs = now - this.levelEnteredAt;
      if (levelElapsedMs > this.config.levelResetMs) {
        this.previousState = "NEUTRAL";
        this.crossedLevelBand = false;
        this.crossCount = 0;
        this.sequenceStartedAt = null;
      }
      return this.emit({
        status: `LEVEL ${this.crossCount}/${this.config.minCrossesPerFlap}`,
        handCount: sample.handCount,
        tracking,
        leftHeight,
        rightHeight,
        delta,
        currentState,
        triggered: false,
        levelElapsedMs,
      });
    }

    this.levelEnteredAt = null;
    let triggered = false;
    if (
      this.previousState !== "NEUTRAL" &&
      currentState !== this.previousState &&
      this.crossedLevelBand
    ) {
      this.lastCrossAt = now;
      if (this.jumpDebounceRemaining(now) <= 0) {
        this.crossCount += 1;
      } else {
        this.crossCount = 0;
        this.sequenceStartedAt = null;
      }

      if (this.crossCount >= this.config.minCrossesPerFlap) {
        this.onFlap({
          triggerAtMs: now,
          auditAtMs: this.sequenceStartedAt ?? this.lastCrossAt ?? now,
        });
        this.lastJumpAt = now;
        this.crossCount = 0;
        this.sequenceStartedAt = null;
        triggered = true;
      }
    }
    this.crossedLevelBand = false;
    this.previousState = currentState;

    return this.emit({
      status: `${currentState} ${this.crossCount}/${this.config.minCrossesPerFlap}`,
      handCount: sample.handCount,
      tracking,
      leftHeight,
      rightHeight,
      delta,
      currentState,
      triggered,
    });
  }

  resolveSample(sample, now) {
    if (sample.handCount >= 2 && sample.leftY !== null && sample.rightY !== null) {
      const leftHeight = this.smoothHeight(0, handHeight(sample.leftY), now);
      const rightHeight = this.smoothHeight(1, handHeight(sample.rightY), now);
      return { leftHeight, rightHeight, tracking: "active" };
    }

    if (now - this.lastSeenAt > this.config.trackingGraceMs) {
      return null;
    }

    if (sample.handCount === 0) {
      return this.predictedSample(now, "predicted");
    }

    if (sample.handCount !== 1) {
      return null;
    }

    if (sample.leftY !== null) {
      this.smoothHeight(0, handHeight(sample.leftY), now);
    }
    if (sample.rightY !== null) {
      this.smoothHeight(1, handHeight(sample.rightY), now);
    }

    const leftHeight = sample.leftY !== null ? this.heights[0] : this.predictHeight(0, now);
    const rightHeight = sample.rightY !== null ? this.heights[1] : this.predictHeight(1, now);
    if (leftHeight === null || rightHeight === null) {
      return null;
    }

    return { leftHeight, rightHeight, tracking: "bridged" };
  }

  predictedSample(now, tracking) {
    const leftHeight = this.predictHeight(0, now);
    const rightHeight = this.predictHeight(1, now);
    if (leftHeight === null || rightHeight === null) {
      return null;
    }

    return { leftHeight, rightHeight, tracking };
  }

  smoothHeight(index, height, now) {
    const previous = this.heights[index];
    if (previous === null) {
      this.heights[index] = height;
      this.heightVelocities[index] = 0;
      this.lastHeightTimes[index] = now;
      return height;
    }

    const movement = Math.abs(height - previous);
    const smoothing =
      movement >= this.config.fastMovementThreshold
        ? Math.max(this.config.anchorSmoothing, this.config.fastAnchorSmoothing)
        : this.config.anchorSmoothing;
    const smoothed = previous + (height - previous) * smoothing;
    const previousTime = this.lastHeightTimes[index];
    const elapsedMs = previousTime === null ? 0 : now - previousTime;
    if (elapsedMs > 0) {
      this.heightVelocities[index] = (smoothed - previous) / elapsedMs;
    }
    this.lastHeightTimes[index] = now;
    this.heights[index] = smoothed;
    return smoothed;
  }

  predictHeight(index, now) {
    const height = this.heights[index];
    const lastHeightTime = this.lastHeightTimes[index];
    if (height === null || lastHeightTime === null) {
      return null;
    }

    const elapsedMs = now - lastHeightTime;
    if (elapsedMs < 0 || elapsedMs > this.config.trackingGraceMs) {
      return null;
    }

    return clamp(height + this.heightVelocities[index] * elapsedMs, 0, 1);
  }

  holdOrReset(now, handCount = 0) {
    if (now - this.lastSeenAt <= this.config.trackingGraceMs) {
      const leftHeight = this.heights[0];
      const rightHeight = this.heights[1];
      if (leftHeight !== null && rightHeight !== null) {
        const delta = leftHeight - rightHeight;
        return this.emit({
          status: "TRACKING HOLD",
          handCount,
          tracking: "hold",
          leftHeight,
          rightHeight,
          delta,
          currentState: this.deltaState(delta),
          triggered: false,
        });
      }

      return this.emit({
        status: "TRACKING HOLD",
        handCount,
        tracking: "hold",
        delta: null,
        triggered: false,
      });
    }

    this.previousState = "NEUTRAL";
    this.crossedLevelBand = false;
    this.crossCount = 0;
    this.sequenceStartedAt = null;
    this.lastJumpAt = -Infinity;
    this.lastCrossAt = -Infinity;
    this.levelEnteredAt = null;
    this.heights = [null, null];
    this.heightVelocities = [0, 0];
    this.lastHeightTimes = [null, null];
    return this.emit({
      status: "NEUTRAL",
      handCount,
      tracking: "missing",
      delta: null,
      triggered: false,
    });
  }

  deltaState(delta) {
    if (delta > this.config.crossThreshold) {
      return "LEFT_HIGH";
    }

    if (delta < -this.config.crossThreshold) {
      return "RIGHT_HIGH";
    }

    return "LEVEL";
  }

  emit(event) {
    this.telemetry = {
      previousState: this.previousState,
      crossedLevelBand: this.crossedLevelBand,
      crossCount: this.crossCount,
      crossThreshold: this.config.crossThreshold,
      minCrossesPerFlap: this.config.minCrossesPerFlap,
      levelResetMs: this.config.levelResetMs,
      jumpDebounceRemainingMs: this.jumpDebounceRemaining(performance.now()),
      ...event,
    };
    return this.telemetry;
  }

  jumpDebounceRemaining(now) {
    return Math.max(0, this.config.jumpDebounceMs - (now - this.lastJumpAt));
  }

  snapshot() {
    return this.telemetry;
  }
}

function parseFrame(buffer) {
  const first = buffer[0];
  const second = buffer[1];
  const opcode = first & 0x0f;
  const masked = (second & 0x80) === 0x80;
  let length = second & 0x7f;
  let offset = 2;

  if (length === 126) {
    if (buffer.length < offset + 2) {
      return null;
    }
    length = buffer.readUInt16BE(offset);
    offset += 2;
  } else if (length === 127) {
    if (buffer.length < offset + 8) {
      return null;
    }
    const bigLength = buffer.readBigUInt64BE(offset);
    if (bigLength > BigInt(Number.MAX_SAFE_INTEGER)) {
      throw new Error("Frame too large");
    }
    length = Number(bigLength);
    offset += 8;
  }

  let maskingKey;
  if (masked) {
    if (buffer.length < offset + 4) {
      return null;
    }
    maskingKey = buffer.subarray(offset, offset + 4);
    offset += 4;
  }

  if (buffer.length < offset + length) {
    return null;
  }

  const payload = Buffer.from(buffer.subarray(offset, offset + length));
  if (masked && maskingKey) {
    for (let index = 0; index < payload.length; index += 1) {
      payload[index] ^= maskingKey[index % 4];
    }
  }

  return {
    opcode,
    payload,
    bytes: offset + length,
  };
}

function standardDeviation(values) {
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / values.length;
  return Math.sqrt(variance);
}

function average(values) {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function median(values) {
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle];
}

function coefficientOfVariation(values) {
  const mean = average(values);
  if (mean === 0) {
    return Infinity;
  }
  return standardDeviation(values) / Math.abs(mean);
}

function percentile(values, p) {
  if (values.length === 0) {
    return 0;
  }
  const sorted = [...values].sort((left, right) => left - right);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.floor((sorted.length - 1) * p)));
  return sorted[index];
}

function positiveDeltas(values) {
  const deltas = [];
  for (let index = 1; index < values.length; index += 1) {
    const delta = values[index] - values[index - 1];
    if (delta > 0) {
      deltas.push(delta);
    }
  }
  return deltas;
}

function maxSameTimestampRun(events) {
  let maxRun = 0;
  let currentRun = 0;
  let previousAtMs = null;

  for (const event of events) {
    const atMs = Math.round(event.atMs);
    if (atMs === previousAtMs) {
      currentRun += 1;
    } else {
      currentRun = 1;
      previousAtMs = atMs;
    }
    maxRun = Math.max(maxRun, currentRun);
  }

  return maxRun;
}

function cameraTraceBlocked(key, detail) {
  return {
    blocked: true,
    key,
    message: verificationPublicMessage(key, detail),
    detail: `Disconnected: ${detail}`,
    failureCode: verificationFailureCode(key, detail),
  };
}

function publicVerdictMessage(verdict) {
  return verdict?.message || "";
}

function detailedVerdictMessage(verdict) {
  return verdict?.detail || verdict?.message || "";
}

function auditSnapshotImage(image) {
  if (typeof image !== "string" || image.length === 0) {
    return {
      valid: false,
      message: "live camera snapshot image is missing.",
    };
  }

  const match = image.match(/^data:image\/(jpeg|jpg|png);base64,([A-Za-z0-9+/=]+)$/);
  if (!match) {
    return {
      valid: false,
      message: "live camera snapshot image format is unsupported.",
    };
  }

  let bytes;
  try {
    bytes = Buffer.from(match[2], "base64");
  } catch {
    return {
      valid: false,
      message: "live camera snapshot image could not be decoded.",
    };
  }

  if (bytes.length < SNAPSHOT_CHALLENGES.minBytes) {
    return {
      valid: false,
      bytes: bytes.length,
      message: "live camera snapshot image is too small.",
    };
  }
  if (bytes.length > SNAPSHOT_CHALLENGES.maxBytes) {
    return {
      valid: false,
      bytes: bytes.length,
      message: "live camera snapshot image is too large.",
    };
  }

  const mime = match[1] === "jpg" ? "jpeg" : match[1];
  const dimensions =
    mime === "png" ? pngDimensions(bytes) : jpegDimensions(bytes);
  if (!dimensions) {
    return {
      valid: false,
      bytes: bytes.length,
      message: "live camera snapshot image dimensions are invalid.",
    };
  }

  if (
    dimensions.width < SNAPSHOT_CHALLENGES.minWidth ||
    dimensions.height < SNAPSHOT_CHALLENGES.minHeight
  ) {
    return {
      valid: false,
      bytes: bytes.length,
      ...dimensions,
      message: "live camera snapshot image resolution is too low.",
    };
  }

  const stats = compressedByteStats(bytes);
  if (
    stats.entropy < SNAPSHOT_CHALLENGES.minEntropy ||
    stats.uniqueBytes < SNAPSHOT_CHALLENGES.minUniqueBytes
  ) {
    return {
      valid: false,
      bytes: bytes.length,
      ...dimensions,
      ...stats,
      message: "live camera snapshot image lacks enough visual detail.",
    };
  }

  return {
    valid: true,
    message: "snapshot accepted.",
    mime,
    dataUrl: image,
    bytes: bytes.length,
    ...dimensions,
    ...stats,
    hash: createHash("sha256").update(bytes).digest("hex"),
  };
}

function jpegDimensions(bytes) {
  if (bytes.length < 4 || bytes[0] !== 0xff || bytes[1] !== 0xd8) {
    return null;
  }

  let offset = 2;
  while (offset + 9 < bytes.length) {
    if (bytes[offset] !== 0xff) {
      offset += 1;
      continue;
    }

    const marker = bytes[offset + 1];
    offset += 2;
    if (marker === 0xd9 || marker === 0xda) {
      break;
    }
    if (offset + 2 > bytes.length) {
      return null;
    }
    const segmentLength = bytes.readUInt16BE(offset);
    if (segmentLength < 2 || offset + segmentLength > bytes.length) {
      return null;
    }

    if (
      (marker >= 0xc0 && marker <= 0xc3) ||
      (marker >= 0xc5 && marker <= 0xc7) ||
      (marker >= 0xc9 && marker <= 0xcb) ||
      (marker >= 0xcd && marker <= 0xcf)
    ) {
      if (segmentLength < 7) {
        return null;
      }
      return {
        height: bytes.readUInt16BE(offset + 3),
        width: bytes.readUInt16BE(offset + 5),
      };
    }

    offset += segmentLength;
  }

  return null;
}

function pngDimensions(bytes) {
  const signature = "89504e470d0a1a0a";
  if (bytes.length < 24 || bytes.subarray(0, 8).toString("hex") !== signature) {
    return null;
  }
  return {
    width: bytes.readUInt32BE(16),
    height: bytes.readUInt32BE(20),
  };
}

function compressedByteStats(bytes) {
  const counts = new Array(256).fill(0);
  for (const byte of bytes) {
    counts[byte] += 1;
  }

  let entropy = 0;
  let uniqueBytes = 0;
  for (const count of counts) {
    if (count === 0) {
      continue;
    }
    uniqueBytes += 1;
    const probability = count / bytes.length;
    entropy -= probability * Math.log2(probability);
  }

  return {
    entropy: Math.round(entropy * 100) / 100,
    uniqueBytes,
  };
}

function nearestHandSampleAt(events, atMs, maxOffsetMs = SNAPSHOT_CHALLENGES.maxHandSampleOffsetMs) {
  let best = null;
  let bestDelta = Infinity;
  for (const event of events) {
    if (
      event.type !== "hands" ||
      event.handCount < 2 ||
      !Number.isFinite(event.leftY) ||
      !Number.isFinite(event.rightY)
    ) {
      continue;
    }

    const delta = Math.abs(event.atMs - atMs);
    if (delta < bestDelta) {
      best = event;
      bestDelta = delta;
    }
  }

  return bestDelta <= maxOffsetMs ? best : null;
}

async function auditSnapshotLandmarks(snapshot) {
  if (SNAPSHOT_LANDMARKS.mode === "off") {
    return null;
  }

  if (!SNAPSHOT_LANDMARKS.serviceUrl) {
    if (SNAPSHOT_LANDMARKS.mode === "required") {
      return cameraTraceBlocked("landmark", "server-side hand landmark extractor is not configured.");
    }
    return null;
  }

  const extracted = await extractSnapshotLandmarks(snapshot);
  if (!extracted.ok) {
    if (SNAPSHOT_LANDMARKS.mode === "required") {
      return cameraTraceBlocked("landmark", extracted.message);
    }
    return null;
  }

  if (
    extracted.handCount < 2 ||
    !Number.isFinite(extracted.leftY) ||
    !Number.isFinite(extracted.rightY)
  ) {
    return cameraTraceBlocked("landmark", "server-side landmark extraction did not find two hands.");
  }

  return null;
}

async function extractSnapshotLandmarks(snapshot) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), SNAPSHOT_LANDMARKS.timeoutMs);
  try {
    const response = await fetch(SNAPSHOT_LANDMARKS.serviceUrl, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        challengeId: snapshot.id,
        image: snapshot.image.dataUrl,
        width: snapshot.image.width,
        height: snapshot.image.height,
      }),
      signal: controller.signal,
    });
    if (!response.ok) {
      return {
        ok: false,
        message: `server-side landmark extractor returned HTTP ${response.status}.`,
      };
    }

    const payload = await response.json();
    const normalized = normalizeExtractedLandmarks(payload);
    if (!normalized) {
      return {
        ok: false,
        message: "server-side landmark extractor returned no usable hand anchors.",
      };
    }

    return {
      ok: true,
      ...normalized,
    };
  } catch (error) {
    return {
      ok: false,
      message:
        error.name === "AbortError"
          ? "server-side landmark extractor timed out."
          : "server-side landmark extractor failed.",
    };
  } finally {
    clearTimeout(timeout);
  }
}

function normalizeExtractedLandmarks(payload) {
  if (!payload || typeof payload !== "object") {
    return null;
  }

  if (Number.isFinite(payload.leftY) && Number.isFinite(payload.rightY)) {
    return {
      handCount: clampInteger(payload.handCount ?? 2, 0, 2),
      leftY: clamp(payload.leftY, 0, 1),
      rightY: clamp(payload.rightY, 0, 1),
    };
  }

  const rawHands = Array.isArray(payload.hands) ? payload.hands : [];
  const bySide = [null, null];
  for (const hand of rawHands) {
    const landmarks = Array.isArray(hand) ? hand : hand?.landmarks;
    const anchor = handAnchorFromLandmarks(landmarks);
    if (!anchor) {
      continue;
    }
    const side = anchor.x >= 0.5 ? 0 : 1;
    bySide[side] = anchor;
  }

  const [leftAnchor, rightAnchor] = bySide;
  if (!leftAnchor || !rightAnchor) {
    return null;
  }

  return {
    handCount: 2,
    leftY: clamp(leftAnchor.y, 0, 1),
    rightY: clamp(rightAnchor.y, 0, 1),
  };
}

function handAnchorFromLandmarks(landmarks) {
  if (!Array.isArray(landmarks)) {
    return null;
  }

  const points = landmarks.filter(
    (landmark) =>
      landmark &&
      Number.isFinite(landmark.x) &&
      Number.isFinite(landmark.y),
  );
  if (!points.length) {
    return null;
  }

  return {
    x: median(points.map((point) => point.x)),
    y: median(points.map((point) => point.y)),
  };
}

function auditHumanMotionTexture(samples) {
  const vectors = [];
  for (let index = 1; index < samples.length; index += 1) {
    const previous = samples[index - 1];
    const current = samples[index];
    const dt = current.atMs - previous.atMs;
    if (dt <= 0 || dt > ANTI_CHEAT.motionTexture.maxVectorGapMs) {
      continue;
    }

    const leftDelta = current.leftY - previous.leftY;
    const rightDelta = current.rightY - previous.rightY;
    const distance = Math.hypot(leftDelta, rightDelta);
    if (distance < ANTI_CHEAT.motionTexture.minVectorDistance) {
      continue;
    }

    vectors.push({
      leftDelta,
      rightDelta,
      distance,
      speed: distance / dt,
      leftVelocity: leftDelta / dt,
      rightVelocity: rightDelta / dt,
    });
  }

  if (vectors.length < ANTI_CHEAT.motionTexture.minActiveVectors) {
    return null;
  }

  const uniqueVectors = new Set(
    vectors.map(
      (vector) =>
        `${vector.leftVelocity.toFixed(5)}:${vector.rightVelocity.toFixed(5)}:${vector.speed.toFixed(5)}`,
    ),
  ).size;
  const uniqueVectorRatio = uniqueVectors / vectors.length;
  if (uniqueVectorRatio < ANTI_CHEAT.motionTexture.minUniqueVectorRatio) {
    return cameraTraceBlocked("motion", "hand movement steps repeat too exactly for live camera input.");
  }

  let compared = 0;
  let collinearStable = 0;
  for (let index = 1; index < vectors.length; index += 1) {
    const previous = vectors[index - 1];
    const current = vectors[index];
    const denominator = previous.distance * current.distance;
    const meanSpeed = (previous.speed + current.speed) / 2;
    if (denominator <= 0 || meanSpeed <= 0) {
      continue;
    }

    const crossMagnitude = Math.abs(
      previous.leftDelta * current.rightDelta - previous.rightDelta * current.leftDelta,
    );
    const collinearity = crossMagnitude / denominator;
    const speedChange = Math.abs(current.speed - previous.speed) / meanSpeed;
    compared += 1;
    if (
      collinearity <= ANTI_CHEAT.motionTexture.collinearSine &&
      speedChange <= ANTI_CHEAT.motionTexture.maxSpeedChangeRatio
    ) {
      collinearStable += 1;
    }
  }

  if (
    compared >= ANTI_CHEAT.motionTexture.minActiveVectors / 2 &&
    collinearStable / compared >= ANTI_CHEAT.motionTexture.maxCollinearStableRatio
  ) {
    return cameraTraceBlocked(
      "motion",
      "hand movement follows too many straight constant-speed segments.",
    );
  }

  return null;
}

function gestureLeadupSignature(samples, now, windowMs, bins, minSamples) {
  const windowStart = now - windowMs;
  const windowSamples = samples
    .filter((sample) => sample.t >= windowStart && sample.t <= now)
    .sort((left, right) => left.t - right.t);
  if (windowSamples.length < minSamples || bins < 2) {
    return null;
  }

  const values = [];
  for (let index = 0; index < bins; index += 1) {
    const targetTime = windowStart + (windowMs * index) / (bins - 1);
    const delta = interpolatedDeltaAt(windowSamples, targetTime);
    if (!Number.isFinite(delta)) {
      return null;
    }
    values.push(delta);
  }

  return { t: now, values };
}

function interpolatedDeltaAt(samples, targetTime) {
  if (samples.length === 0) {
    return null;
  }

  if (targetTime <= samples[0].t) {
    return samples[0].delta;
  }

  const lastSample = samples.at(-1);
  if (targetTime >= lastSample.t) {
    return lastSample.delta;
  }

  for (let index = 0; index < samples.length - 1; index += 1) {
    const left = samples[index];
    const right = samples[index + 1];
    if (left.t <= targetTime && right.t >= targetTime) {
      const span = right.t - left.t || 1;
      const amount = (targetTime - left.t) / span;
      return left.delta + (right.delta - left.delta) * amount;
    }
  }

  return null;
}

function gestureSignatureDistance(left, right) {
  const length = Math.min(left.length, right.length);
  if (length === 0) {
    return Infinity;
  }

  let sum = 0;
  for (let index = 0; index < length; index += 1) {
    sum += (left[index] - right[index]) ** 2;
  }
  return Math.sqrt(sum / length);
}

function deltaVelocityFeatures(samples) {
  const velocities = [];
  for (let index = 1; index < samples.length; index += 1) {
    const dt = samples[index].t - samples[index - 1].t;
    if (dt <= 0) {
      continue;
    }
    velocities.push((samples[index].delta - samples[index - 1].delta) / dt);
  }

  const active = velocities.filter((velocity) => Math.abs(velocity) > 0.0004);
  if (active.length === 0) {
    return { count: 0, meanAbs: 0, cv: Infinity, directionChanges: 0 };
  }

  let directionChanges = 0;
  let previousSign = Math.sign(active[0]);
  for (let index = 1; index < active.length; index += 1) {
    const sign = Math.sign(active[index]);
    if (sign !== 0 && previousSign !== 0 && sign !== previousSign) {
      directionChanges += 1;
    }
    if (sign !== 0) {
      previousSign = sign;
    }
  }

  const absVelocities = active.map((velocity) => Math.abs(velocity));
  return {
    count: active.length,
    meanAbs: average(absVelocities),
    cv: coefficientOfVariation(absVelocities),
    directionChanges,
  };
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function clampInteger(value, min, max) {
  if (!Number.isFinite(value)) {
    return min;
  }
  return Math.round(clamp(value, min, max));
}

function normalizedOrNull(value) {
  return Number.isFinite(value) ? clamp(value, 0, 1) : null;
}

function handHeight(y) {
  return 1 - y;
}

function parseBoolean(value, fallback) {
  if (value === undefined) {
    return fallback;
  }
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}
