/**
 * Single WebSocket client for solve load tests.
 * Measures ping RTT, per-message-type schedule drift, and hand motion distance.
 */
import { WIN_SCORE } from "../../../shared/game-core.js";
import {
  finishMessage,
  restartMessage,
  toSocketPayload,
} from "../../../shared/frontend-client.js";
import { summarizeSamples } from "./load-test-metrics.mjs";

const PING_INTERVAL_MS = 500;

function readFinishVerifyTimeoutMs() {
  const raw = process.env.LOAD_TEST_FINISH_VERIFY_TIMEOUT_MS;
  if (raw === undefined || raw === "") {
    return null;
  }
  const value = Number(raw);
  return Number.isFinite(value) && value > 0 ? value : null;
}

/** Null means wait indefinitely for `verified`. Set LOAD_TEST_FINISH_VERIFY_TIMEOUT_MS to cap wait. */
export const LOAD_TEST_FINISH_VERIFY_TIMEOUT_MS = readFinishVerifyTimeoutMs();

function createTypeBuckets() {
  return new Map();
}

function recordSample(buckets, type, field, value) {
  if (!Number.isFinite(value)) {
    return;
  }
  if (!buckets.has(type)) {
    buckets.set(type, {});
  }
  const row = buckets.get(type);
  if (!row[field]) {
    row[field] = [];
  }
  row[field].push(value);
}

function bucketsToObject(buckets) {
  const byType = {};
  for (const [type, fields] of buckets.entries()) {
    byType[type] = {};
    for (const [field, samples] of Object.entries(fields)) {
      byType[type][field] = samples;
    }
  }
  return byType;
}

export function formatConnectionError(caught, targetUrl) {
  if (caught instanceof Error && caught.message) {
    return `${caught.message} (${targetUrl})`;
  }

  const event = caught && typeof caught === "object" ? caught : null;
  const nested = event?.error;
  if (nested instanceof Error && nested.message) {
    return `${nested.message} (${targetUrl})`;
  }

  if (event?.message && typeof event.message === "string") {
    return `${event.message} (${targetUrl})`;
  }

  return `WebSocket connection failed (${targetUrl})`;
}

function motionDistance(leftY, rightY, previous) {
  if (!previous) {
    return null;
  }
  const leftDelta = leftY - previous.leftY;
  const rightDelta = rightY - previous.rightY;
  return Math.hypot(leftDelta, rightDelta);
}

export async function openGameSocket(targetUrl) {
  const socket = new WebSocket(targetUrl);
  const connectStarted = performance.now();

  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", (event) => reject(event), { once: true });
  });

  const connectMs = performance.now() - connectStarted;

  const welcome = await new Promise((resolve, reject) => {
    const deadline = setTimeout(() => reject(new Error("welcome timeout")), 8000);
    const onMessage = (event) => {
      const message = JSON.parse(String(event.data));
      if (message.type === "welcome") {
        clearTimeout(deadline);
        socket.removeEventListener("message", onMessage);
        resolve(message);
      }
    };
    socket.addEventListener("message", onMessage);
    socket.addEventListener("error", reject, { once: true });
  });

  return {
    socket,
    connectMs,
    welcomeMs: performance.now() - connectStarted,
    sessionId: welcome.id,
  };
}

function fakeJpegDataUrl(seed) {
  const bytes = Buffer.alloc(9500);
  let offset = 0;
  bytes[offset++] = 0xff;
  bytes[offset++] = 0xd8;
  bytes[offset++] = 0xff;
  bytes[offset++] = 0xc0;
  bytes.writeUInt16BE(17, offset);
  offset += 2;
  bytes[offset++] = 8;
  bytes.writeUInt16BE(240, offset);
  offset += 2;
  bytes.writeUInt16BE(320, offset);
  offset += 2;
  bytes[offset++] = 3;
  bytes[offset++] = 1;
  bytes[offset++] = 0x11;
  bytes[offset++] = 0;
  bytes[offset++] = 2;
  bytes[offset++] = 0x11;
  bytes[offset++] = 0;
  bytes[offset++] = 3;
  bytes[offset++] = 0x11;
  bytes[offset++] = 0;

  let state = seed >>> 0;
  for (; offset < bytes.length - 2; offset += 1) {
    state = (state * 1664525 + 1013904223) >>> 0;
    bytes[offset] = state & 0xff;
  }
  bytes[bytes.length - 2] = 0xff;
  bytes[bytes.length - 1] = 0xd9;
  return `data:image/jpeg;base64,${bytes.toString("base64")}`;
}

function snapshotSample(state) {
  if (state.latestVideoFrame) {
    return {
      leftY: state.latestVideoFrame.leftY,
      rightY: state.latestVideoFrame.rightY,
      handCount: state.latestVideoFrame.handCount ?? 2,
    };
  }
  return state.lastSample || { leftY: 0.48, rightY: 0.49, handCount: 2 };
}

function attachSocketObservers(socket, buckets, pendingPings, observerState) {
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(String(event.data));

    if (message.type === "pong" && Number.isFinite(message.clientTime)) {
      const sentAt = pendingPings.get(message.clientTime);
      if (sentAt !== undefined) {
        const rttMs = performance.now() - sentAt;
        recordSample(buckets, "ping", "pingRttMs", rttMs);
        pendingPings.delete(message.clientTime);
      }
      return;
    }

    if (message.type === "state" && socket._lastSend) {
      const ackMs = performance.now() - socket._lastSend.at;
      recordSample(buckets, socket._lastSend.type, "ackRttMs", ackMs);
      return;
    }

    if (message.type === "snapshot_challenge") {
      const sentAt = performance.now();
      const sample = snapshotSample(observerState);
      const activeFrame = observerState.latestVideoFrame;
      const snapshotIndex = observerState.snapshotsSent + 1;
      observerState.snapshotsSent = snapshotIndex;
      socket._lastSend = { type: "snapshot", at: sentAt };
      socket.send(
        JSON.stringify(
          toSocketPayload(
            {
              type: "snapshot",
              challengeId: message.challengeId,
              image:
                activeFrame?.image ||
                fakeJpegDataUrl(observerState.imageSeedBase + 100000 + snapshotIndex),
              leftY: sample.leftY,
              rightY: sample.rightY,
              handCount: sample.handCount ?? 2,
            },
            { traceAtMs: activeFrame?.atMs ?? message.traceAtMs },
          ),
        ),
      );
      recordSample(buckets, "snapshot", "driftMs", performance.now() - sentAt);
    }
  });
}

function sendPing(socket, pendingPings, buckets) {
  if (socket.readyState !== WebSocket.OPEN) {
    return;
  }
  const clientTime = Date.now();
  const sentAt = performance.now();
  pendingPings.set(clientTime, sentAt);
  socket.send(JSON.stringify({ type: "ping", clientTime }));
}

/**
 * Replay timed solve events and collect drift / ping / motion metrics.
 */
export async function replayEventsWithMetrics(options) {
  const {
    socket,
    events,
    durationMs,
    submitFinish = false,
    claimScore = WIN_SCORE,
    clientId = 0,
  } = options;
  const capped =
    Number.isFinite(durationMs) && durationMs > 0
      ? events.filter((event) => event.atMs <= durationMs)
      : events;

  const sorted = [...capped].sort((left, right) => left.atMs - right.atMs);
  const replayDurationMs = sorted.at(-1)?.atMs || 0;
  const buckets = createTypeBuckets();
  const pendingPings = new Map();
  const motionDistances = [];
  const handsGapMs = [];
  let lastHandsAt = null;
  let lastSample = null;
  let eventsSent = 0;
  let handsSent = 0;
  let videoFramesSent = 0;
  const observerState = {
    imageSeedBase: (clientId + 1) * 1000000,
    lastSample: null,
    latestVideoFrame: null,
    snapshotsSent: 0,
  };

  attachSocketObservers(socket, buckets, pendingPings, observerState);

  const runStarted = performance.now();
  const restartSentAt = performance.now();
  socket.send(JSON.stringify(toSocketPayload(restartMessage(), { traceAtMs: 0 })));
  recordSample(buckets, "restart", "driftMs", restartSentAt - runStarted);

  sendPing(socket, pendingPings, buckets);
  const pingTimer = setInterval(() => sendPing(socket, pendingPings, buckets), PING_INTERVAL_MS);

  await new Promise((resolve) => {
    for (const entry of sorted) {
      setTimeout(() => {
        if (socket.readyState !== WebSocket.OPEN) {
          return;
        }

        const actualMs = performance.now() - runStarted;
        const messageType = entry.message.type || "unknown";
        recordSample(buckets, messageType, "driftMs", actualMs - entry.atMs);

        if (messageType === "hands") {
          handsSent += 1;
          if (lastHandsAt !== null) {
            handsGapMs.push(actualMs - lastHandsAt);
          }
          lastHandsAt = actualMs;

          const leftY = entry.message.leftY;
          const rightY = entry.message.rightY;
          if (Number.isFinite(leftY) && Number.isFinite(rightY)) {
            const distance = motionDistance(leftY, rightY, lastSample);
            if (distance !== null) {
              motionDistances.push(distance);
            }
            lastSample = { leftY, rightY };
            observerState.lastSample = {
              leftY,
              rightY,
              handCount: entry.message.handCount ?? 2,
            };
          }
        }

        let message = entry.message;
        if (messageType === "video_frame") {
          videoFramesSent += 1;
          observerState.lastSample = {
            leftY: entry.message.leftY,
            rightY: entry.message.rightY,
            handCount: entry.message.handCount ?? 2,
          };
          const { sourceAtMs: _sourceAtMs, ...videoMessage } = entry.message;
          message = {
            ...videoMessage,
            image:
              entry.message.image ||
              fakeJpegDataUrl(observerState.imageSeedBase + (entry.message.sequence ?? videoFramesSent)),
          };
          observerState.latestVideoFrame = {
            atMs: entry.atMs,
            image: message.image,
            leftY: message.leftY,
            rightY: message.rightY,
            handCount: message.handCount ?? 2,
          };
        }

        socket._lastSend = { type: messageType, at: performance.now() };
        socket.send(JSON.stringify(toSocketPayload(message, { traceAtMs: entry.atMs })));
        eventsSent += 1;
      }, entry.atMs);
    }

    setTimeout(resolve, replayDurationMs + 400);
  });

  clearInterval(pingTimer);
  sendPing(socket, pendingPings, buckets);
  await new Promise((resolve) => setTimeout(resolve, 120));

  let finish = null;
  if (submitFinish) {
    const finishSentAt = performance.now();
    finish = await new Promise((resolve) => {
      let deadline = null;
      const cleanup = () => {
        if (deadline !== null) {
          clearTimeout(deadline);
          deadline = null;
        }
        socket.removeEventListener("message", onMessage);
        socket.removeEventListener("close", onClose);
        socket.removeEventListener("error", onError);
      };
      const resolveOnce = (value) => {
        cleanup();
        resolve(value);
      };
      if (LOAD_TEST_FINISH_VERIFY_TIMEOUT_MS !== null) {
        deadline = setTimeout(
          () =>
            resolveOnce({
              timeout: true,
              message: "finish verification timeout",
            }),
          LOAD_TEST_FINISH_VERIFY_TIMEOUT_MS,
        );
      }
      const onMessage = (event) => {
        const message = JSON.parse(String(event.data));
        if (message.type === "verified") {
          resolveOnce(message);
        }
      };
      const onClose = (event) =>
        resolveOnce({
          closed: true,
          closeCode: event.code,
          closeReason: event.reason || "",
          message: event.reason || "socket closed before finish verification",
        });
      const onError = () =>
        resolveOnce({
          error: true,
          message: "socket error before finish verification",
        });
      socket.addEventListener("message", onMessage);
      socket.addEventListener("close", onClose, { once: true });
      socket.addEventListener("error", onError, { once: true });
      socket._lastSend = { type: "finish", at: finishSentAt };
      socket.send(JSON.stringify(toSocketPayload(finishMessage(claimScore))));
    });
    recordSample(buckets, "finish", "ackRttMs", performance.now() - finishSentAt);
  }

  const byType = bucketsToObject(buckets);
  const allDrift = Object.values(byType).flatMap((row) => row.driftMs || []);
  const allPing = byType.ping?.pingRttMs || [];

  return {
    eventsPlanned: sorted.length,
    eventsSent,
    handsSent,
    videoFramesSent,
    snapshotsSent: observerState.snapshotsSent,
    replayDurationMs,
    byType,
    pingRttMs: allPing,
    driftMs: summarizeSamples(allDrift),
    handsGapMs: summarizeSamples(handsGapMs),
    motionDistance: summarizeSamples(motionDistances),
    finish: submitFinish
      ? {
          submitted: true,
          valid: finish.valid ?? false,
          verified: finish.verified ?? false,
          score: finish.score ?? null,
          claimedScore: finish.claimedScore ?? claimScore,
          won: finish.won ?? false,
          flag: finish.flag || "",
          timeout: finish.timeout ?? false,
          closed: finish.closed ?? false,
          closeCode: finish.closeCode ?? null,
          closeReason: finish.closeReason || "",
          error: finish.error ?? false,
          message: finish.message || "",
          detail: finish.detail || "",
          failureCode: finish.failureCode || "",
        }
      : null,
  };
}

export async function runLoadTestClient(options) {
  const startedAt = Date.now();
  let connection = null;
  let replay = null;
  let error = null;

  try {
    connection = await openGameSocket(options.targetUrl);
    replay = await replayEventsWithMetrics({
      socket: connection.socket,
      events: options.events,
      durationMs: options.durationMs,
      submitFinish: options.submitFinish,
      claimScore: options.claimScore,
      clientId: options.clientId,
    });
  } catch (caught) {
    error = formatConnectionError(caught, options.targetUrl);
  } finally {
    if (connection?.socket) {
      connection.socket.close();
    }
  }

  return {
    clientId: options.clientId,
    mode: options.mode,
    targetUrl: options.targetUrl,
    startedAt,
    durationMs: Date.now() - startedAt,
    sessionId: connection?.sessionId || "",
    connectMs: connection?.connectMs ?? null,
    welcomeMs: connection?.welcomeMs ?? null,
    error,
    suite: options.suite ?? null,
    ...replay,
  };
}
