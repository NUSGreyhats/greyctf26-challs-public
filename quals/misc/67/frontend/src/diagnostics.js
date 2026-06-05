import {
  DEFAULT_GESTURE_CONFIG,
  FAST_HAND_LANDMARKER_OPTIONS,
  GestureInterpreter,
  handAnchorPoint,
  handHeight,
  orderedHands,
  screenSideIndex,
} from "./gesture.js";

const video = document.querySelector("#diagnosticCamera");
const overlay = document.querySelector("#diagnosticOverlay");
const overlayCtx = overlay.getContext("2d");
const graph = document.querySelector("#signalGraph");
const graphCtx = graph.getContext("2d");
const cameraButton = document.querySelector("#diagnosticCameraButton");
const statusText = document.querySelector("#diagnosticStatus");
const stateText = document.querySelector("#diagnosticState");
const deltaText = document.querySelector("#diagnosticDelta");
const crossesText = document.querySelector("#diagnosticCrosses");
const jumpsText = document.querySelector("#diagnosticJumps");
const serverFlapsText = document.querySelector("#diagnosticServerFlaps");
const thresholdControl = document.querySelector("#thresholdControl");
const thresholdValue = document.querySelector("#thresholdValue");
const crossesControl = document.querySelector("#crossesControl");
const smoothingControl = document.querySelector("#smoothingControl");
const smoothingValue = document.querySelector("#smoothingValue");
const jumpFlash = document.querySelector("#jumpFlash");

const HAND_ANCHOR_MARKER_RADIUS = 12;
const HAND_SIDE_GUIDE_TOP = 10;
const HAND_SIDE_GUIDE_HEIGHT = 24;
const SAMPLE_WINDOW_MS = 10000;
const HAND_OVERLAY_STYLES = [
  { anchor: "#ff3b5c" },
  { anchor: "#42ff87" },
];

let handLandmarker = null;
let lastVideoTime = -1;
let mediaPipeReady = false;
let cameraStarting = false;
let jumpCount = 0;
let lastJumpAt = 0;
let samples = [];
let jumpEvents = [];
let socket = null;
let connected = false;
let serverFlapCount = 0;

const gestures = new GestureInterpreter({
  onFlap: recordJump,
  onTelemetry: recordTelemetry,
});

thresholdControl.value = String(DEFAULT_GESTURE_CONFIG.crossThreshold);
crossesControl.value = String(DEFAULT_GESTURE_CONFIG.minCrossesPerFlap);
smoothingControl.value = String(DEFAULT_GESTURE_CONFIG.anchorSmoothing);

init();
connectServer();
requestAnimationFrame(drawGraph);

function init() {
  applyControlValues();
  bindControls();
  statusText.textContent = "Camera tracking is ready to start.";
  stateText.textContent = "STANDBY";
}

function bindControls() {
  cameraButton.addEventListener("click", startCamera);
  thresholdControl.addEventListener("input", applyControlValues);
  crossesControl.addEventListener("input", applyControlValues);
  smoothingControl.addEventListener("input", applyControlValues);
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

function connectServer() {
  if (socket) {
    socket.close();
  }

  socket = new WebSocket(backendWebSocketUrl());

  socket.addEventListener("open", () => {
    connected = true;
    statusText.textContent = mediaPipeReady
      ? "Camera tracking active. Server connected."
      : "Server connected. Start Camera to stream hand samples.";
  });

  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.type === "state") {
      serverFlapCount = message.state.acceptedFlapCount ?? 0;
      serverFlapsText.textContent = String(serverFlapCount);
    }
  });

  socket.addEventListener("close", (event) => {
    connected = false;
    const reason = typeof event.reason === "string" ? event.reason.trim() : "";
    statusText.textContent = reason
      ? `Server disconnected: ${reason}`
      : "Server disconnected. Refresh to reconnect.";
  });

  socket.addEventListener("error", () => {
    connected = false;
    statusText.textContent = "Server connection failed.";
  });
}

function applyControlValues() {
  const crossThreshold = Number(thresholdControl.value);
  const minCrossesPerFlap = clamp(Math.round(Number(crossesControl.value)), 1, 6);
  const anchorSmoothing = Number(smoothingControl.value);
  gestures.updateConfig({
    crossThreshold,
    minCrossesPerFlap,
    anchorSmoothing,
  });
  thresholdValue.textContent = crossThreshold.toFixed(3);
  smoothingValue.textContent = anchorSmoothing.toFixed(2);
  crossesText.textContent = `${gestures.crossCount}/${minCrossesPerFlap}`;
}

async function startCamera() {
  if (cameraStarting || mediaPipeReady) {
    return;
  }

  try {
    cameraStarting = true;
    cameraButton.disabled = true;
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
    statusText.textContent = connected
      ? "Camera tracking active. Streaming hand samples to server."
      : "Camera active. Waiting for server connection.";
    stateText.textContent = "TRACKING";
    requestAnimationFrame(trackHands);
  } catch (error) {
    cameraStarting = false;
    mediaPipeReady = false;
    cameraButton.disabled = false;
    statusText.textContent = `Camera unavailable: ${error.message}`;
  }
}

function trackHands() {
  if (mediaPipeReady && handLandmarker && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
    if (video.currentTime !== lastVideoTime) {
      lastVideoTime = video.currentTime;
      const result = handLandmarker.detectForVideo(video, performance.now());
      const hands = orderedHands(result);
      gestures.process(hands);
      const sample = handSample(hands);
      sendHandSample(sample);
      drawHandOverlay(hands);
      statusText.textContent = !connected
        ? "Camera active. Server offline — flap counts unavailable."
        : sample.handCount < 2
          ? "Show both hands. Null Y frames are normal during dropouts."
          : "Camera tracking active. Streaming hand samples to server.";
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

function sendHandSample(sample) {
  if (!connected || !socket || socket.readyState !== WebSocket.OPEN) {
    return;
  }

  socket.send(
    JSON.stringify({
      type: "hands",
      leftY: sample.leftY,
      rightY: sample.rightY,
      handCount: sample.handCount,
      clientTime: Date.now(),
    }),
  );
}

function recordTelemetry(telemetry) {
  const timestamp = telemetry.timestamp;
  const left = telemetry.leftAnchor ? handHeight(telemetry.leftAnchor) : null;
  const right = telemetry.rightAnchor ? handHeight(telemetry.rightAnchor) : null;
  samples.push({
    timestamp,
    left,
    right,
    delta: telemetry.delta,
    status: telemetry.status,
    crossThreshold: telemetry.crossThreshold,
    triggered: telemetry.triggered,
  });
  trimTimeline(timestamp);

  stateText.textContent = telemetry.status;
  deltaText.textContent = Number.isFinite(telemetry.delta) ? telemetry.delta.toFixed(3) : "--";
  crossesText.textContent = `${telemetry.crossCount}/${telemetry.minCrossesPerFlap}`;
}

function recordJump() {
  jumpCount += 1;
  lastJumpAt = performance.now();
  jumpEvents.push(lastJumpAt);
  jumpsText.textContent = String(jumpCount);
  jumpFlash.classList.add("is-visible");
  window.setTimeout(() => jumpFlash.classList.remove("is-visible"), 180);
}

function trimTimeline(now) {
  const oldest = now - SAMPLE_WINDOW_MS;
  samples = samples.filter((sample) => sample.timestamp >= oldest);
  jumpEvents = jumpEvents.filter((timestamp) => timestamp >= oldest);
}

function drawGraph() {
  resizeGraph();
  const width = graph.clientWidth;
  const height = graph.clientHeight;
  const pixelRatio = window.devicePixelRatio || 1;
  graphCtx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  graphCtx.clearRect(0, 0, width, height);
  drawGraphBackground(width, height);
  drawDeltaThreshold(width, height);
  drawSignalLine(width, height, "left", "#ff3b5c");
  drawSignalLine(width, height, "right", "#16835b");
  drawDeltaLine(width, height);
  drawJumpMarkers(width, height);

  if (performance.now() - lastJumpAt < 220) {
    graphCtx.fillStyle = "rgba(229, 111, 47, 0.12)";
    graphCtx.fillRect(0, 0, width, height);
  }

  requestAnimationFrame(drawGraph);
}

function resizeGraph() {
  const width = Math.max(1, Math.round(graph.clientWidth));
  const height = Math.max(1, Math.round(graph.clientHeight));
  const pixelRatio = window.devicePixelRatio || 1;
  const canvasWidth = Math.round(width * pixelRatio);
  const canvasHeight = Math.round(height * pixelRatio);
  if (graph.width !== canvasWidth || graph.height !== canvasHeight) {
    graph.width = canvasWidth;
    graph.height = canvasHeight;
  }
}

function drawGraphBackground(width, height) {
  graphCtx.fillStyle = "#fff6cc";
  graphCtx.fillRect(0, 0, width, height);
  graphCtx.strokeStyle = "rgba(91, 74, 39, 0.18)";
  graphCtx.lineWidth = 1;
  for (let row = 1; row < 4; row += 1) {
    const y = (height / 4) * row;
    graphCtx.beginPath();
    graphCtx.moveTo(0, y);
    graphCtx.lineTo(width, y);
    graphCtx.stroke();
  }
  for (let col = 1; col < 10; col += 1) {
    const x = (width / 10) * col;
    graphCtx.beginPath();
    graphCtx.moveTo(x, 0);
    graphCtx.lineTo(x, height);
    graphCtx.stroke();
  }

  graphCtx.fillStyle = "#5b4a27";
  graphCtx.font = "800 12px Inter, system-ui, sans-serif";
  graphCtx.fillText("left height", 12, 20);
  graphCtx.fillStyle = "#16835b";
  graphCtx.fillText("right height", 104, 20);
  graphCtx.fillStyle = "#c64f20";
  graphCtx.fillText("delta / jumps", 210, 20);
}

function drawDeltaThreshold(width, height) {
  const threshold = Number(thresholdControl.value);
  const top = deltaToY(threshold, height);
  const bottom = deltaToY(-threshold, height);
  graphCtx.fillStyle = "rgba(246, 196, 83, 0.18)";
  graphCtx.fillRect(0, top, width, bottom - top);
  graphCtx.strokeStyle = "rgba(155, 107, 20, 0.55)";
  graphCtx.setLineDash([5, 5]);
  graphCtx.beginPath();
  graphCtx.moveTo(0, top);
  graphCtx.lineTo(width, top);
  graphCtx.moveTo(0, bottom);
  graphCtx.lineTo(width, bottom);
  graphCtx.moveTo(0, height / 2);
  graphCtx.lineTo(width, height / 2);
  graphCtx.stroke();
  graphCtx.setLineDash([]);
}

function drawSignalLine(width, height, key, color) {
  const points = samples.filter((sample) => Number.isFinite(sample[key]));
  if (points.length < 2) {
    return;
  }

  graphCtx.strokeStyle = color;
  graphCtx.lineWidth = 2;
  graphCtx.beginPath();
  points.forEach((sample, index) => {
    const point = {
      x: timeToX(sample.timestamp, width),
      y: valueToY(sample[key], height),
    };
    if (index === 0) {
      graphCtx.moveTo(point.x, point.y);
    } else {
      graphCtx.lineTo(point.x, point.y);
    }
  });
  graphCtx.stroke();
}

function drawDeltaLine(width, height) {
  const points = samples.filter((sample) => Number.isFinite(sample.delta));
  if (points.length < 2) {
    return;
  }

  graphCtx.strokeStyle = "#c64f20";
  graphCtx.lineWidth = 2;
  graphCtx.beginPath();
  points.forEach((sample, index) => {
    const point = {
      x: timeToX(sample.timestamp, width),
      y: deltaToY(sample.delta, height),
    };
    if (index === 0) {
      graphCtx.moveTo(point.x, point.y);
    } else {
      graphCtx.lineTo(point.x, point.y);
    }
  });
  graphCtx.stroke();
}

function drawJumpMarkers(width, height) {
  for (const timestamp of jumpEvents) {
    const x = timeToX(timestamp, width);
    graphCtx.strokeStyle = "#d94a38";
    graphCtx.lineWidth = 3;
    graphCtx.beginPath();
    graphCtx.moveTo(x, 0);
    graphCtx.lineTo(x, height);
    graphCtx.stroke();

    graphCtx.fillStyle = "#d94a38";
    graphCtx.fillRect(x - 4, 0, 8, 18);
  }
}

function timeToX(timestamp, width) {
  const now = performance.now();
  return width - ((now - timestamp) / SAMPLE_WINDOW_MS) * width;
}

function valueToY(value, height) {
  return height - clamp(value, 0, 1) * height;
}

function deltaToY(delta, height) {
  return height / 2 - clamp(delta, -0.24, 0.24) * (height / 0.48);
}

function drawHandOverlay(hands) {
  const overlaySize = resizeHandOverlay();
  overlayCtx.clearRect(0, 0, overlaySize.width, overlaySize.height);
  drawHandSideGuide(overlayCtx, overlaySize);

  hands.slice(0, 2).forEach((hand, index) => {
    const anchor = handAnchorPoint(hand);
    if (!anchor) {
      return;
    }
    const side = hands.length >= 2 ? index : screenSideIndex(anchor);
    const style = HAND_OVERLAY_STYLES[side] || HAND_OVERLAY_STYLES[0];
    const anchorPoint = landmarkToPreviewPoint(anchor, overlaySize);

    overlayCtx.save();
    overlayCtx.shadowColor = "rgba(0, 0, 0, 0.72)";
    overlayCtx.shadowBlur = 5;

    overlayCtx.beginPath();
    overlayCtx.arc(anchorPoint.x, anchorPoint.y, HAND_ANCHOR_MARKER_RADIUS, 0, Math.PI * 2);
    overlayCtx.fillStyle = style.anchor;
    overlayCtx.fill();
    overlayCtx.lineWidth = 3;
    overlayCtx.strokeStyle = "#ffffff";
    overlayCtx.stroke();

    overlayCtx.beginPath();
    overlayCtx.moveTo(anchorPoint.x - HAND_ANCHOR_MARKER_RADIUS - 8, anchorPoint.y);
    overlayCtx.lineTo(anchorPoint.x + HAND_ANCHOR_MARKER_RADIUS + 8, anchorPoint.y);
    overlayCtx.moveTo(anchorPoint.x, anchorPoint.y - HAND_ANCHOR_MARKER_RADIUS - 8);
    overlayCtx.lineTo(anchorPoint.x, anchorPoint.y + HAND_ANCHOR_MARKER_RADIUS + 8);
    overlayCtx.lineWidth = 3;
    overlayCtx.strokeStyle = style.anchor;
    overlayCtx.stroke();

    overlayCtx.restore();
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

function resizeHandOverlay() {
  const rect = overlay.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  const pixelRatio = window.devicePixelRatio || 1;
  const canvasWidth = Math.round(width * pixelRatio);
  const canvasHeight = Math.round(height * pixelRatio);
  if (overlay.width !== canvasWidth || overlay.height !== canvasHeight) {
    overlay.width = canvasWidth;
    overlay.height = canvasHeight;
  }
  overlayCtx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
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
