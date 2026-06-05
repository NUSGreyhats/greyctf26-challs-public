import {
  FAST_HAND_LANDMARKER_OPTIONS,
  GestureInterpreter,
  handAnchorPoint,
  handHeight,
  orderedHands,
  screenSideIndex,
} from "./gesture.js";
import {
  GAME_CONSTANTS,
  WIN_SCORE,
  applyFlap as applyCoreFlap,
  createGameState,
  stepGameState,
} from "/shared/game-core.js";
import {
  finishMessage,
  flapMessage,
  handsMessage,
  restartMessage,
  toSocketPayload,
} from "/shared/frontend-client.js";

const canvas = document.querySelector("#game");
const ctx = canvas.getContext("2d");
ctx.imageSmoothingEnabled = false;
const cameraButton = document.querySelector("#cameraButton");
const cameraFrame = document.querySelector(".camera-frame");
const restartButton = document.querySelector("#restartButton");
const video = document.querySelector("#cameraPreview");
const handOverlay = document.querySelector("#handOverlay");
const handCtx = handOverlay.getContext("2d");
const statusText = document.querySelector("#status");
const scoreText = document.querySelector("#score");
const bestText = document.querySelector("#best");
const modeText = document.querySelector("#mode");
const flagBanner = document.querySelector("#flagBanner");
const flagText = document.querySelector("#flagText");
const cheatAlert = document.querySelector("#cheatAlert");
const cheatAlertText = document.querySelector("#cheatAlertText");
const gestureStateText = document.querySelector("#gestureState");
const flapPulseText = document.querySelector("#flapPulse");
const leftMeter = document.querySelector("#leftMeter");
const rightMeter = document.querySelector("#rightMeter");

const HAND_ANCHOR_MARKER_RADIUS = 12;
const HAND_SIDE_GUIDE_TOP = 10;
const HAND_SIDE_GUIDE_HEIGHT = 24;
const HAND_OVERLAY_STYLES = [
  { anchor: "#ff3b5c" },
  { anchor: "#42ff87" },
];
const SPRITE_SIZE = 16;
const PIPE_SPRITES = {
  body: { x: 0, y: 0, width: SPRITE_SIZE, height: SPRITE_SIZE },
  topHead: { x: 16, y: 0, width: SPRITE_SIZE, height: SPRITE_SIZE },
  bottomHead: { x: 32, y: 0, width: SPRITE_SIZE, height: SPRITE_SIZE },
};
const BIRD_SPRITE_START_X = 48;
const BIRD_FRAMES = {
  up: 1,
  neutral: 2,
  down: 0,
};
const atlas = new Image();
let atlasCanvas = null;
atlas.addEventListener("load", prepareAtlasTransparency);
atlas.src = "./public/assets/flappy_atlas.png";

let constants = { ...GAME_CONSTANTS };

let config = {
  space67Keyboard: false,
  antiCheatEnabled: true,
  clientSim: true,
  winScore: WIN_SCORE,
  verifyScoreThreshold: 50,
  snapshotChallenges: {
    enabled: true,
    minRequired: 10,
    deadlineMs: 1200,
  },
  videoVerify: {
    mode: "required",
    minFrames: 80,
    minValidFrames: 70,
    minAverageFps: 4,
  },
};

let gameState = createGameState();
let sessionMeta = {
  best: 0,
  won: false,
  flag: "",
};
let finishSubmitted = false;
let verificationPending = false;

let socket = null;
let connected = false;
let cameraStarting = false;
let mediaPipeReady = false;
let visionLoopStarted = false;
let handLandmarker = null;
let lastVideoTime = -1;
let sentFlaps = 0;
let sentHandSamples = 0;
let sentVideoFrames = 0;
let lastVideoFrameSentAt = -Infinity;
let mode = "Connecting";
let synthetic67LeftHigh = false;
let pingTimer = null;
let runTraceAtMs = null;
let latestHandSample = { leftY: null, rightY: null, handCount: 0 };
let snapshotChallengeCount = 0;
let snapshotAcceptedCount = 0;
let syncState = {
  rttMs: 0,
  clockOffsetMs: 0,
};

const PING_INTERVAL_MS = 2000;
const VIDEO_FRAME_INTERVAL_MS = 80;
const VIDEO_FRAME_WIDTH = 360;
const VIDEO_FRAME_QUALITY = 0.58;
const SYNC_SMOOTHING = 0.2;
const MAX_RENDER_DT_SECONDS = 0.05;
let lastDrawAt = performance.now();
const localGesture = new GestureInterpreter({
  onFlap: () => applyLocalFlap(),
  onTelemetry: handleLocalGestureTelemetry,
});

connect();
requestAnimationFrame(draw);

function connect() {
  socket = new WebSocket(backendWebSocketUrl());
  statusText.textContent = "Connecting to authority server.";
  mode = "Connecting";

  socket.addEventListener("open", () => {
    connected = true;
    startPingLoop();
    if (!cameraStarting) {
      statusText.textContent = mediaPipeReady ? "Camera tracking active." : "Server connected.";
    }
    mode = mediaPipeReady ? "Tracking" : "Online";
  });

  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "welcome") {
      constants = { ...GAME_CONSTANTS, ...(message.constants || {}) };
      config = { ...config, ...(message.config || {}) };
      canvas.width = constants.width;
      canvas.height = constants.height;
      sessionMeta.best = message.session?.best ?? sessionMeta.best;
      resetLocalRun();
      applyInputMode();
      if (!cameraStarting) {
        if (config.space67Keyboard) {
          statusText.textContent = "Server connected. Keyboard mode active.";
        } else if (mediaPipeReady) {
          statusText.textContent = "Camera tracking active.";
        } else {
          statusText.textContent = "Starting camera tracking.";
        }
      }
      return;
    }
    if (message.type === "state") {
      if (!config.clientSim) {
        applyServerState(message.state);
      }
      return;
    }
    if (message.type === "verified") {
      applyVerifiedResult(message);
      return;
    }
    if (message.type === "snapshot_challenge") {
      handleSnapshotChallenge(message);
      return;
    }
    if (message.type === "snapshot_result") {
      handleSnapshotResult(message);
      return;
    }
    if (message.type === "pong") {
      handlePong(message);
    }
  });

  socket.addEventListener("close", (event) => {
    connected = false;
    stopPingLoop();
    mode = "Offline";
    const reason = typeof event.reason === "string" ? event.reason.trim() : "";
    if (reason) {
      statusText.textContent = reason;
      showCheatAlert("blocked", reason);
    } else {
      statusText.textContent = "Server disconnected. Restart the Node server and refresh.";
      hideCheatAlert();
    }
  });

  socket.addEventListener("error", () => {
    connected = false;
    mode = "Offline";
    statusText.textContent = "Server connection failed.";
  });
}

function backendWebSocketUrl() {
  const configured = new URLSearchParams(window.location.search).get("backend");
  if (configured) {
    const base = configured
      .replace(/^http:/, "ws:")
      .replace(/^https:/, "wss:")
      .replace(/\/$/, "")
      .replace(/\/ws$/, "");
    return `${base}/ws`;
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws`;
}

function startPingLoop() {
  stopPingLoop();
  sendPing();
  pingTimer = setInterval(sendPing, PING_INTERVAL_MS);
}

function stopPingLoop() {
  if (pingTimer !== null) {
    clearInterval(pingTimer);
    pingTimer = null;
  }
}

function sendPing() {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }

  socket.send(JSON.stringify({ type: "ping", clientTime: Date.now() }));
}

function handlePong(message) {
  if (!Number.isFinite(message.clientTime) || !Number.isFinite(message.serverRecv) || !Number.isFinite(message.serverTime)) {
    return;
  }

  const clientReceived = Date.now();
  const rttSample = clientReceived - message.clientTime;
  const offsetSample = (message.serverRecv - message.clientTime + message.serverTime - clientReceived) / 2;

  syncState.rttMs = smoothSample(syncState.rttMs, rttSample);
  syncState.clockOffsetMs = smoothSample(syncState.clockOffsetMs, offsetSample);
  sendSync();
}

function smoothSample(previous, sample) {
  if (!previous) {
    return sample;
  }

  return previous * (1 - SYNC_SMOOTHING) + sample * SYNC_SMOOTHING;
}

function sendSync() {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }

  socket.send(
    JSON.stringify({
      type: "sync",
      rttMs: Math.round(syncState.rttMs),
      clockOffsetMs: Math.round(syncState.clockOffsetMs),
    }),
  );
}

function currentTraceAtMs() {
  return Number.isFinite(runTraceAtMs) ? performance.now() - runTraceAtMs : undefined;
}

function sendFlap(source, traceAtMs = currentTraceAtMs()) {
  if (!connected || socket.readyState !== WebSocket.OPEN) {
    statusText.textContent = "Flap ignored while server is offline.";
    return;
  }

  applyLocalFlap();
  socket.send(JSON.stringify(toSocketPayload(flapMessage(source), { traceAtMs })));
  sentFlaps += 1;
  updateInputCounters();
  mode = config.space67Keyboard ? "Keyboard" : mediaPipeReady ? "Tracking" : "Online";
}

function keyboardModeEnabled() {
  return config.space67Keyboard;
}

function cameraModeEnabled() {
  return !config.space67Keyboard;
}

function applyInputMode() {
  cameraButton.disabled = keyboardModeEnabled();
  cameraButton.hidden = keyboardModeEnabled();
  cameraFrame.hidden = keyboardModeEnabled();

  if (keyboardModeEnabled()) {
    stopCameraTracking();
    statusText.textContent = connected ? "Keyboard mode active." : "Server offline.";
    mode = connected ? "Keyboard" : "Offline";
    return;
  }

  if (!mediaPipeReady && !cameraStarting) {
    statusText.textContent = "Starting camera tracking.";
    startCamera();
  }
}

function stopCameraTracking() {
  if (video.srcObject) {
    for (const track of video.srcObject.getTracks()) {
      track.stop();
    }
    video.srcObject = null;
  }
  mediaPipeReady = false;
  cameraStarting = false;
  lastVideoTime = -1;
  leftMeter.value = 0.5;
  rightMeter.value = 0.5;
  gestureStateText.textContent = "NEUTRAL";
  localGesture.reset();
  resetLocalRun();
}

function resetLocalRun() {
  gameState = createGameState({}, constants);
  finishSubmitted = false;
  verificationPending = false;
}

function restartRun() {
  sentFlaps = 0;
  sentHandSamples = 0;
  sentVideoFrames = 0;
  lastVideoFrameSentAt = -Infinity;
  snapshotChallengeCount = 0;
  snapshotAcceptedCount = 0;
  flapPulseText.textContent = "0 samples";
  sessionMeta.won = false;
  sessionMeta.flag = "";
  resetLocalRun();
  localGesture.reset();
  hideCheatAlert();
  runTraceAtMs = performance.now();
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(toSocketPayload(restartMessage(), { traceAtMs: 0 })));
  }
}

function signalSynthetic67() {
  synthetic67LeftHigh = !synthetic67LeftHigh;
  const currentState = synthetic67LeftHigh ? "LEFT_HIGH" : "RIGHT_HIGH";
  gestureStateText.textContent = `DEV ${currentState}`;
  leftMeter.value = synthetic67LeftHigh ? 0.82 : 0.24;
  rightMeter.value = synthetic67LeftHigh ? 0.24 : 0.82;
  sendFlap("gesture");
}

function draw() {
  const now = performance.now();
  const dt = Math.min(MAX_RENDER_DT_SECONDS, Math.max(0, (now - lastDrawAt) / 1000));
  lastDrawAt = now;
  advanceLocalSimulation(dt);
  checkRunFinished();

  ctx.imageSmoothingEnabled = false;
  ctx.clearRect(0, 0, constants.width, constants.height);
  drawSky(gameState);
  drawPipes(gameState);
  drawFloor(gameState);
  drawBird(gameState);
  drawOverlay(gameState);

  scoreText.textContent = String(gameState.score);
  bestText.textContent = String(Math.max(sessionMeta.best, gameState.score));
  modeText.textContent = mode;
  updateFlagBanner();

  requestAnimationFrame(draw);
}

function updateFlagBanner() {
  if (!sessionMeta.won) {
    flagBanner.hidden = true;
    flagText.textContent = "";
    return;
  }

  flagBanner.hidden = false;
  flagText.textContent = sessionMeta.flag || "Flag not configured.";
}

function showCheatAlert(level, message) {
  if (!message) {
    hideCheatAlert();
    return;
  }

  cheatAlert.hidden = false;
  cheatAlert.dataset.level = level;
  cheatAlertText.textContent = message;
}

function hideCheatAlert() {
  cheatAlert.hidden = true;
  cheatAlertText.textContent = "";
  delete cheatAlert.dataset.level;
}

function updateCheatAlertFromState(antiCheat) {
  if (!config.antiCheatEnabled || antiCheat?.enabled === false || antiCheat?.level === "disabled") {
    hideCheatAlert();
    return;
  }

  if (!antiCheat || antiCheat.level === "none" || !antiCheat.message) {
    hideCheatAlert();
    return;
  }

  const scoreHint =
    antiCheat.level === "blocked"
      ? ""
      : ` (${Math.round(antiCheat.score)}/${antiCheat.blockScore}${antiCheat.lastHeuristic ? ` · ${antiCheat.lastHeuristic}` : ""})`;
  showCheatAlert(antiCheat.level, `${antiCheat.message}${scoreHint}`);
}

function applyVerifiedResult(message) {
  verificationPending = false;

  if (!message.valid) {
    sessionMeta.won = false;
    sessionMeta.flag = "";
    updateFlagBanner();
    showCheatAlert("blocked", message.message || "Run verification failed.");
    statusText.textContent = message.message || "Run verification failed.";
    return;
  }

  sessionMeta.best = Math.max(sessionMeta.best, message.score ?? gameState.score);
  if (message.won) {
    sessionMeta.won = true;
    sessionMeta.flag = message.flag || "";
  } else {
    sessionMeta.won = false;
    sessionMeta.flag = "";
  }

  updateFlagBanner();
  hideCheatAlert();
  if (message.verified) {
    statusText.textContent = `Run verified: score ${message.score}.`;
  } else if (mediaPipeReady) {
    statusText.textContent = "Camera tracking active.";
  } else {
    statusText.textContent = "Server connected.";
  }

  if (message.antiCheat) {
    updateCheatAlertFromState(message.antiCheat);
  }
}

function applyServerState(serverState) {
  gameState = createGameState(
    {
      birdY: serverState.birdY,
      velocity: serverState.velocity,
      score: serverState.score,
      elapsed: serverState.elapsed,
      spawnTimer: serverState.spawnTimer,
      gameOver: serverState.gameOver,
      awaitingStart: serverState.awaitingStart,
      nextPipeId: serverState.nextPipeId,
      pipes: serverState.pipes || [],
    },
    constants,
  );
  sessionMeta.best = Math.max(sessionMeta.best, serverState.best ?? 0);
  sessionMeta.won = Boolean(serverState.won);
  sessionMeta.flag = serverState.flag || "";
  updateCheatAlertFromState(serverState.antiCheat);
}

function advanceLocalSimulation(dt) {
  if (!gameState.awaitingStart && !gameState.gameOver) {
    stepGameState(gameState, dt, constants);
  }
}

function applyLocalFlap() {
  if (gameState.gameOver) {
    restartRun();
  }
  applyCoreFlap(gameState, constants);
}

function targetWinScore() {
  return constants.winScore ?? config.winScore ?? WIN_SCORE;
}

function verifyScoreThreshold() {
  return config.verifyScoreThreshold ?? 50;
}

function scoreNeedsVerification(score) {
  return config.clientSim && score > verifyScoreThreshold();
}

function hasReachedWinScore(score) {
  return score >= targetWinScore();
}

/** Show the flag banner only when the win does not require server replay. */
function grantLocalWinIfTrusted(score) {
  if (hasReachedWinScore(score) && !scoreNeedsVerification(score)) {
    sessionMeta.won = true;
    updateFlagBanner();
  }
}

function checkRunFinished() {
  if (!gameState.gameOver || finishSubmitted) {
    return;
  }

  finishSubmitted = true;
  sessionMeta.best = Math.max(sessionMeta.best, gameState.score);
  grantLocalWinIfTrusted(gameState.score);

  if (!scoreNeedsVerification(gameState.score)) {
    return;
  }

  submitRunForVerification(gameState.score);
}

function submitRunForVerification(score) {
  if (!connected || socket.readyState !== WebSocket.OPEN) {
    statusText.textContent = "Cannot verify — game socket offline.";
    return;
  }

  finishSubmitted = true;
  verificationPending = true;
  statusText.textContent = "Verifying run with server...";
  socket.send(JSON.stringify(toSocketPayload(finishMessage(score))));
}

function drawSky(sim) {
  const gradient = ctx.createLinearGradient(0, 0, 0, constants.floorY);
  gradient.addColorStop(0, "#78dcf6");
  gradient.addColorStop(0.68, "#5dc7e3");
  gradient.addColorStop(1, "#4ab2d1");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, constants.width, constants.floorY);

  drawCloud(120 - ((sim.elapsed * 18) % 1120), 82, 1.1);
  drawCloud(560 - ((sim.elapsed * 12) % 1120), 148, 0.85);
  drawCloud(880 - ((sim.elapsed * 16) % 1120), 62, 0.7);

  ctx.fillStyle = "#8bd05a";
  for (let x = -80 + ((sim.elapsed * 28) % 160); x < constants.width + 120; x += 160) {
    ctx.beginPath();
    ctx.arc(x, constants.floorY - 34, 72, Math.PI, 0);
    ctx.fill();
    ctx.fillStyle = "#73bf48";
  }
}

function drawPipes(sim) {
  for (const pipe of sim.pipes) {
    const topHeight = pipe.gapY;
    const bottomY = pipe.gapY + constants.pipeGap;
    drawPipe(pipe.x, 0, topHeight, true);
    drawPipe(pipe.x, bottomY, constants.floorY - bottomY, false);
  }
}

function drawFloor(sim) {
  ctx.fillStyle = "#d9a447";
  ctx.fillRect(0, constants.floorY, constants.width, constants.height - constants.floorY);
  ctx.fillStyle = "#f3d269";
  ctx.fillRect(0, constants.floorY, constants.width, 12);
  ctx.fillStyle = "#8b6a2e";
  for (let x = -32 + ((sim.elapsed * constants.pipeSpeed) % 32); x < constants.width; x += 32) {
    ctx.fillRect(x, constants.floorY + 12, 16, 16);
    ctx.fillRect(x + 16, constants.floorY + 28, 16, 16);
  }
}

function drawBird(sim) {
  const tilt = clamp(sim.velocity / 520, -0.55, 0.8);
  ctx.save();
  ctx.translate(constants.birdX, sim.birdY);
  ctx.rotate(tilt);
  const frame = birdSpriteFrame(sim);
  if (atlas.complete && atlas.naturalWidth > 0) {
    ctx.drawImage(
      spriteSource(),
      BIRD_SPRITE_START_X + frame * SPRITE_SIZE + 0.5,
      0.5,
      SPRITE_SIZE - 1,
      SPRITE_SIZE - 1,
      -28,
      -28,
      56,
      56,
    );
  } else {
    ctx.fillStyle = "#f2d047";
    ctx.beginPath();
    ctx.ellipse(0, 0, 22, 17, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

function birdSpriteFrame(sim) {
  if (sim.gameOver && sim.velocity >= -20) {
    return BIRD_FRAMES.neutral;
  }

  if (sim.velocity < 0) {
    return BIRD_FRAMES.down;
  }
  return BIRD_FRAMES.up;
}

function drawPipe(x, y, height, inverted) {
  const capHeight = 38;
  const bodyX = x + 5;
  const bodyWidth = constants.pipeWidth - 10;
  const headFrame = inverted ? PIPE_SPRITES.topHead : PIPE_SPRITES.bottomHead;
  const headY = inverted ? y + height - capHeight : y;
  const bodyStartY = inverted ? y : y + capHeight;
  const bodyEndY = inverted ? headY : y + height;

  if (atlas.complete && atlas.naturalWidth > 0) {
    const sprites = spriteSource();
    const bodyHeight = Math.max(0, bodyEndY - bodyStartY);
    if (bodyHeight > 0) {
      ctx.drawImage(
        sprites,
        PIPE_SPRITES.body.x + 3,
        PIPE_SPRITES.body.y,
        PIPE_SPRITES.body.width - 6,
        PIPE_SPRITES.body.height,
        bodyX,
        bodyStartY,
        bodyWidth,
        bodyHeight,
      );
    }
    ctx.drawImage(
      sprites,
      headFrame.x,
      headFrame.y,
      headFrame.width,
      headFrame.height,
      x - 5,
      headY,
      constants.pipeWidth + 10,
      capHeight,
    );
    return;
  }

  ctx.fillStyle = "#5ec247";
  ctx.fillRect(bodyX, bodyStartY, bodyWidth, Math.max(0, bodyEndY - bodyStartY));
  ctx.fillStyle = "#78d957";
  ctx.fillRect(x - 5, headY, constants.pipeWidth + 10, capHeight);
}

function prepareAtlasTransparency() {
  const prepared = document.createElement("canvas");
  prepared.width = atlas.naturalWidth;
  prepared.height = atlas.naturalHeight;
  const preparedCtx = prepared.getContext("2d", { willReadFrequently: true });
  preparedCtx.imageSmoothingEnabled = false;
  preparedCtx.drawImage(atlas, 0, 0);

  const image = preparedCtx.getImageData(0, 0, prepared.width, prepared.height);
  const visited = new Uint8Array(prepared.width * prepared.height);
  const queue = [];
  for (let x = 0; x < prepared.width; x += 1) {
    queue.push([x, 0], [x, prepared.height - 1]);
  }
  for (let y = 0; y < prepared.height; y += 1) {
    queue.push([0, y], [prepared.width - 1, y]);
  }

  while (queue.length > 0) {
    const [x, y] = queue.pop();
    if (x < 0 || y < 0 || x >= prepared.width || y >= prepared.height) {
      continue;
    }
    const pixelIndex = y * prepared.width + x;
    if (visited[pixelIndex]) {
      continue;
    }
    visited[pixelIndex] = 1;
    const dataIndex = pixelIndex * 4;
    if (!isBackgroundPixel(image.data, dataIndex)) {
      continue;
    }

    image.data[dataIndex + 3] = 0;
    queue.push([x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]);
  }

  preparedCtx.putImageData(image, 0, 0);
  atlasCanvas = prepared;
}

function spriteSource() {
  return atlasCanvas || atlas;
}

function isBackgroundPixel(data, index) {
  return data[index] > 238 && data[index + 1] > 238 && data[index + 2] > 238 && data[index + 3] > 0;
}

function drawCloud(x, y, scale) {
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(scale, scale);
  ctx.fillStyle = "rgba(255, 255, 255, 0.94)";
  ctx.beginPath();
  ctx.arc(0, 18, 22, Math.PI, 0);
  ctx.arc(26, 8, 28, Math.PI, 0);
  ctx.arc(58, 18, 22, Math.PI, 0);
  ctx.rect(-22, 18, 102, 24);
  ctx.fill();
  ctx.fillStyle = "rgba(228, 247, 255, 0.9)";
  ctx.fillRect(-18, 34, 94, 8);
  ctx.restore();
}

function drawOverlay(sim) {
  if (verificationPending) {
    drawMessage("Verifying", "Server is replaying your run...");
    return;
  }

  if (sim.awaitingStart) {
    drawMessage("Ready", readySubtitle());
    return;
  }

  if (sim.gameOver) {
    const subtitle = scoreNeedsVerification(sim.score)
      ? "Run submitted for verification. Press Restart to play again."
      : "Press Restart or flap again.";
    drawMessage("Grounded", subtitle);
  }
}

function readySubtitle() {
  if (!connected) {
    return "Connect to the server to play.";
  }
  if (keyboardModeEnabled()) {
    return "Press Space to start the run.";
  }
  if (cameraStarting) {
    return "Allow camera access to start.";
  }
  if (mediaPipeReady) {
    return "Use the 67 hand gesture to start the run.";
  }
  return "Starting camera tracking.";
}

function drawMessage(title, subtitle) {
  ctx.fillStyle = "rgba(100, 74, 24, 0.22)";
  ctx.fillRect(0, 0, constants.width, constants.height);
  ctx.fillStyle = "#ffffff";
  ctx.textAlign = "center";
  ctx.font = "900 48px Inter, system-ui, sans-serif";
  ctx.lineWidth = 8;
  ctx.strokeStyle = "#5b4a27";
  ctx.strokeText(title, constants.width / 2, constants.height / 2 - 20);
  ctx.fillText(title, constants.width / 2, constants.height / 2 - 20);
  ctx.fillStyle = "#5b4a27";
  ctx.font = "700 18px Inter, system-ui, sans-serif";
  ctx.fillText(subtitle, constants.width / 2, constants.height / 2 + 22);
  ctx.textAlign = "start";
}

async function startCamera() {
  if (!cameraModeEnabled()) {
    statusText.textContent = "Camera is disabled in keyboard mode.";
    return;
  }
  try {
    cameraStarting = true;
    statusText.textContent = "Loading hand model.";
    const { FilesetResolver, HandLandmarker } = await import(
      "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.18"
    );
    const vision = await FilesetResolver.forVisionTasks(
      "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.18/wasm",
    );
    handLandmarker = await HandLandmarker.createFromOptions(vision, {
      baseOptions: {
        modelAssetPath:
          "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
        delegate: "GPU",
      },
      ...FAST_HAND_LANDMARKER_OPTIONS,
    });

    video.srcObject = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 960 },
        height: { ideal: 540 },
        frameRate: { ideal: 60 },
        facingMode: "user",
      },
      audio: false,
    });
    await video.play();
    mediaPipeReady = true;
    cameraStarting = false;
    mode = "Tracking";
    statusText.textContent = connected ? "Camera tracking active." : "Camera ready, server offline.";

    if (!visionLoopStarted) {
      visionLoopStarted = true;
      requestAnimationFrame(trackHands);
    }
  } catch (error) {
    cameraStarting = false;
    mediaPipeReady = false;
    statusText.textContent = `Camera unavailable: ${error.message}`;
  }
}

function trackHands() {
  if (mediaPipeReady && handLandmarker && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
    if (video.currentTime !== lastVideoTime) {
      lastVideoTime = video.currentTime;
      const now = performance.now();
      const result = handLandmarker.detectForVideo(video, now);
      const hands = orderedHands(result);
      localGesture.process(hands, now);
      const sample = handSample(hands);
      sendHandSample(sample);
      maybeSendVideoFrame(sample, now);
      updateHandMeters(sample);
      drawHandOverlay(hands);
      if (hands.length < 2) {
        statusText.textContent = "Show both hands.";
      } else {
        statusText.textContent = "Camera tracking active.";
      }
    }
  }
  requestAnimationFrame(trackHands);
}

function handSample(hands) {
  const sample = {
    leftY: null,
    rightY: null,
    handCount: Math.min(hands.length, 2),
  };

  hands.slice(0, 2).forEach((hand, index) => {
    const anchor = handAnchorPoint(hand);
    if (!anchor) {
      return;
    }

    const side = hands.length >= 2 ? index : screenSideIndex(anchor);
    if (side === 0) {
      sample.leftY = anchor.y;
    } else {
      sample.rightY = anchor.y;
    }
  });

  return sample;
}

function sendHandSample(sample, traceAtMs = currentTraceAtMs()) {
  latestHandSample = {
    leftY: sample.leftY,
    rightY: sample.rightY,
    handCount: sample.handCount,
  };

  if (!connected || socket.readyState !== WebSocket.OPEN) {
    return;
  }

  socket.send(JSON.stringify(toSocketPayload(handsMessage(sample), { traceAtMs })));
  sentHandSamples += 1;
  updateInputCounters();
}

function maybeSendVideoFrame(sample, now = performance.now()) {
  if (config.videoVerify?.mode === "off") {
    return;
  }
  if (!connected || socket.readyState !== WebSocket.OPEN) {
    return;
  }
  if (now - lastVideoFrameSentAt < VIDEO_FRAME_INTERVAL_MS) {
    return;
  }
  if (!mediaPipeReady || sample.handCount < 2) {
    return;
  }

  lastVideoFrameSentAt = now;
  const traceAtMs = currentTraceAtMs();
  const payload = {
    type: "video_frame",
    sequence: sentVideoFrames + 1,
    ...sample,
    clientTime: Date.now(),
    traceAtMs,
  };

  try {
    payload.image = captureCameraSnapshot(VIDEO_FRAME_WIDTH, VIDEO_FRAME_QUALITY);
  } catch (error) {
    payload.image = "";
    payload.error = error.message;
  }

  socket.send(JSON.stringify(payload));
  sentVideoFrames += 1;
  updateInputCounters();
}

function updateInputCounters() {
  flapPulseText.textContent = `${sentHandSamples} samples`;
}

function handleSnapshotChallenge(message) {
  snapshotChallengeCount += 1;
  statusText.textContent = `Snapshot challenge ${snapshotChallengeCount}: keep both hands visible.`;
  sendSnapshotResponse(message);
}

function handleSnapshotResult(message) {
  if (message.accepted) {
    snapshotAcceptedCount += 1;
    statusText.textContent = `Snapshot accepted (${snapshotAcceptedCount}/${snapshotChallengeCount}).`;
    return;
  }

  statusText.textContent = message.message || "Snapshot challenge failed.";
  showCheatAlert("warning", statusText.textContent);
}

function sendSnapshotResponse(challenge) {
  if (!connected || socket.readyState !== WebSocket.OPEN) {
    return;
  }

  const payload = {
    type: "snapshot",
    challengeId: challenge.challengeId,
    ...latestHandSample,
    clientTime: Date.now(),
    traceAtMs: currentTraceAtMs(),
  };

  try {
    payload.image = captureCameraSnapshot();
  } catch (error) {
    payload.image = "";
    payload.error = error.message;
  }

  socket.send(JSON.stringify(payload));
}

function captureCameraSnapshot(targetMaxWidth = 480, quality = 0.68) {
  if (!mediaPipeReady || !video || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
    throw new Error("camera frame unavailable");
  }

  const sourceWidth = video.videoWidth || 0;
  const sourceHeight = video.videoHeight || 0;
  if (sourceWidth < 1 || sourceHeight < 1) {
    throw new Error("camera frame has no dimensions");
  }

  const targetWidth = Math.min(targetMaxWidth, sourceWidth);
  const targetHeight = Math.max(1, Math.round((sourceHeight / sourceWidth) * targetWidth));
  const snapshotCanvas = document.createElement("canvas");
  snapshotCanvas.width = targetWidth;
  snapshotCanvas.height = targetHeight;
  const snapshotCtx = snapshotCanvas.getContext("2d");
  snapshotCtx.drawImage(video, 0, 0, targetWidth, targetHeight);
  return snapshotCanvas.toDataURL("image/jpeg", quality);
}

function updateHandMeters(sample) {
  if (sample.leftY !== null) {
    leftMeter.value = handHeight({ y: sample.leftY });
  }
  if (sample.rightY !== null) {
    rightMeter.value = handHeight({ y: sample.rightY });
  }
}

function drawHandOverlay(hands) {
  const overlaySize = resizeHandOverlay();
  handCtx.clearRect(0, 0, overlaySize.width, overlaySize.height);
  drawHandSideGuide(handCtx, overlaySize);

  hands.slice(0, 2).forEach((hand, index) => {
    const anchor = handAnchorPoint(hand);
    if (!anchor) {
      return;
    }
    const side = hands.length >= 2 ? index : screenSideIndex(anchor);
    const style = HAND_OVERLAY_STYLES[side] || HAND_OVERLAY_STYLES[0];
    const anchorPoint = landmarkToPreviewPoint(anchor, overlaySize);

    handCtx.save();
    handCtx.shadowColor = "rgba(0, 0, 0, 0.72)";
    handCtx.shadowBlur = 5;

    handCtx.beginPath();
    handCtx.arc(anchorPoint.x, anchorPoint.y, HAND_ANCHOR_MARKER_RADIUS, 0, Math.PI * 2);
    handCtx.fillStyle = style.anchor;
    handCtx.fill();
    handCtx.lineWidth = 3;
    handCtx.strokeStyle = "#ffffff";
    handCtx.stroke();

    handCtx.beginPath();
    handCtx.moveTo(anchorPoint.x - HAND_ANCHOR_MARKER_RADIUS - 8, anchorPoint.y);
    handCtx.lineTo(anchorPoint.x + HAND_ANCHOR_MARKER_RADIUS + 8, anchorPoint.y);
    handCtx.moveTo(anchorPoint.x, anchorPoint.y - HAND_ANCHOR_MARKER_RADIUS - 8);
    handCtx.lineTo(anchorPoint.x, anchorPoint.y + HAND_ANCHOR_MARKER_RADIUS + 8);
    handCtx.lineWidth = 3;
    handCtx.strokeStyle = style.anchor;
    handCtx.stroke();

    handCtx.beginPath();
    handCtx.arc(anchorPoint.x, anchorPoint.y, HAND_ANCHOR_MARKER_RADIUS + 10, 0, Math.PI * 2);
    handCtx.lineWidth = 2;
    handCtx.strokeStyle = "rgba(255, 255, 255, 0.95)";
    handCtx.stroke();

    handCtx.restore();
  });
}

function drawHandSideGuide(ctx, overlaySize) {
  const middleX = overlaySize.width / 2;
  const top = HAND_SIDE_GUIDE_TOP;
  const bottom = top + HAND_SIDE_GUIDE_HEIGHT;
  const leftColor = HAND_OVERLAY_STYLES[0].anchor;
  const rightColor = HAND_OVERLAY_STYLES[1].anchor;
  const leftLabelX = middleX / 2;
  const rightLabelX = middleX + middleX / 2;

  ctx.save();
  ctx.shadowColor = "rgba(0, 0, 0, 0.65)";
  ctx.shadowBlur = 4;

  ctx.globalAlpha = 0.92;
  ctx.lineWidth = 2;
  ctx.strokeStyle = "rgba(255, 255, 255, 0.95)";
  ctx.beginPath();
  ctx.moveTo(middleX, 0);
  ctx.lineTo(middleX, overlaySize.height);
  ctx.stroke();

  drawSideBracket(ctx, leftLabelX, top, bottom, leftColor, "left");
  drawSideBracket(ctx, rightLabelX, top, bottom, rightColor, "right");

  ctx.beginPath();
  ctx.moveTo(Math.max(18, leftLabelX - 42), top + HAND_SIDE_GUIDE_HEIGHT / 2);
  ctx.lineTo(middleX - 10, top + HAND_SIDE_GUIDE_HEIGHT / 2);
  ctx.moveTo(middleX + 10, top + HAND_SIDE_GUIDE_HEIGHT / 2);
  ctx.lineTo(Math.min(overlaySize.width - 18, rightLabelX + 42), top + HAND_SIDE_GUIDE_HEIGHT / 2);
  ctx.strokeStyle = "rgba(255, 255, 255, 0.8)";
  ctx.stroke();

  ctx.fillStyle = "#ffffff";
  ctx.font = "800 13px Inter, system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("L", leftLabelX, bottom + 12);
  ctx.fillText("R", rightLabelX, bottom + 12);
  ctx.restore();
}

function drawSideBracket(ctx, centerX, top, bottom, color, direction) {
  const pointX = direction === "left" ? centerX - 18 : centerX + 18;
  const innerX = direction === "left" ? centerX - 4 : centerX + 4;

  ctx.beginPath();
  ctx.moveTo(pointX, top + HAND_SIDE_GUIDE_HEIGHT / 2);
  ctx.lineTo(innerX, top);
  ctx.lineTo(innerX, bottom);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = "rgba(255, 255, 255, 0.95)";
  ctx.stroke();
}

function handleLocalGestureTelemetry(telemetry) {
  if (keyboardModeEnabled()) {
    return;
  }

  gestureStateText.textContent = telemetry.status || "NEUTRAL";
}

function resizeHandOverlay() {
  const rect = handOverlay.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  const pixelRatio = window.devicePixelRatio || 1;
  const canvasWidth = Math.round(width * pixelRatio);
  const canvasHeight = Math.round(height * pixelRatio);
  if (handOverlay.width !== canvasWidth || handOverlay.height !== canvasHeight) {
    handOverlay.width = canvasWidth;
    handOverlay.height = canvasHeight;
  }
  handCtx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  return { width, height };
}

function landmarkToPreviewPoint(landmark, overlaySize) {
  const { width, height } = overlaySize;
  const videoWidth = video.videoWidth || width;
  const videoHeight = video.videoHeight || height;
  const scale = Math.max(width / videoWidth, height / videoHeight);
  const renderedWidth = videoWidth * scale;
  const renderedHeight = videoHeight * scale;
  const offsetX = (width - renderedWidth) / 2;
  const offsetY = (height - renderedHeight) / 2;

  return {
    x: width - (offsetX + landmark.x * renderedWidth),
    y: offsetY + landmark.y * renderedHeight,
  };
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

cameraButton.addEventListener("click", startCamera);
restartButton.addEventListener("click", restartRun);

window.addEventListener("pointerdown", (event) => {
  if (event.target.closest(".controls")) {
    return;
  }
  if (keyboardModeEnabled()) {
    statusText.textContent = "Use Space in keyboard mode.";
    return;
  }
  statusText.textContent = "Pointer input is disabled in camera mode.";
});

window.addEventListener("keydown", (event) => {
  if (event.code === "Space") {
    event.preventDefault();
    if (keyboardModeEnabled()) {
      signalSynthetic67();
    } else {
      statusText.textContent = "Keyboard input is disabled in camera mode.";
    }
  }
});
