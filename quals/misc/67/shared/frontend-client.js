/**
 * Canonical WebSocket payloads for the production game frontend.
 * Solve lab, CLI replay, and camera play must all use these shapes.
 */
import { WIN_SCORE } from "./game-core.js";

export const MESSAGE_TYPES = Object.freeze({
  hands: "hands",
  flap: "flap",
  snapshot: "snapshot",
  snapshotChallenge: "snapshot_challenge",
  snapshotResult: "snapshot_result",
  videoFrame: "video_frame",
  restart: "restart",
  finish: "finish",
  sync: "sync",
});

/** @typedef {{ atMs: number, message: { type: string, [key: string]: unknown } }} TraceEvent */

export function clampScore(score) {
  const value = Math.round(Number(score));
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(WIN_SCORE, Math.max(0, value));
}

export function handsMessage(sample) {
  return {
    type: MESSAGE_TYPES.hands,
    leftY: sample.leftY,
    rightY: sample.rightY,
    handCount: sample.handCount ?? 2,
  };
}

export function flapMessage(source = "manual") {
  return {
    type: MESSAGE_TYPES.flap,
    source: source === "gesture" ? "gesture" : "manual",
  };
}

export function restartMessage() {
  return { type: MESSAGE_TYPES.restart };
}

export function finishMessage(score) {
  return {
    type: MESSAGE_TYPES.finish,
    score: clampScore(score),
  };
}

/**
 * JSON body the production frontend sends on the game socket.
 * Includes traceAtMs when provided so server verify replay matches scripted timing.
 */
export function toSocketPayload(message, { traceAtMs, clientTime = Date.now() } = {}) {
  const payload = {
    ...message,
    clientTime,
  };

  if (Number.isFinite(traceAtMs)) {
    payload.traceAtMs = Math.max(0, Math.round(traceAtMs));
  }

  return payload;
}

export function normalizeTraceEvent(event) {
  const atMs = Number.isFinite(event.atMs) ? event.atMs : 0;
  const raw = event.message ?? event;

  if (raw.type === MESSAGE_TYPES.hands) {
    return {
      atMs,
      message: handsMessage({
        leftY: raw.leftY,
        rightY: raw.rightY,
        handCount: raw.handCount,
      }),
    };
  }

  if (raw.type === MESSAGE_TYPES.flap) {
    return {
      atMs,
      message: flapMessage(raw.source),
    };
  }

  return {
    atMs,
    message: { ...raw },
  };
}

export function normalizeTraceEvents(events) {
  return (events || [])
    .map(normalizeTraceEvent)
    .filter((event) => event.message.type !== MESSAGE_TYPES.restart)
    .sort((left, right) => left.atMs - right.atMs);
}

/**
 * Schedule trace replay using the same timing contract as the production client.
 */
export function createTraceReplayer(events, callbacks = {}, options = {}) {
  const normalized = normalizeTraceEvents(events);
  const timeScale = Number.isFinite(options.timeScale) && options.timeScale > 0 ? options.timeScale : 1;
  const settleMs = options.settleMs ?? 500;

  const controller = {
    stopped: false,
    timers: [],
    events: normalized,
    stop() {
      controller.stopped = true;
      for (const timer of controller.timers) {
        clearTimeout(timer);
      }
      controller.timers = [];
    },
  };

  for (const event of normalized) {
    const timer = setTimeout(() => {
      if (controller.stopped) {
        return;
      }
      dispatchTraceEvent(event, callbacks);
    }, event.atMs / timeScale);
    controller.timers.push(timer);
  }

  const lastAtMs = normalized.at(-1)?.atMs || 0;
  const doneTimer = setTimeout(() => {
    if (controller.stopped) {
      return;
    }
    callbacks.onComplete?.({
      events: normalized,
      durationMs: lastAtMs,
    });
  }, lastAtMs / timeScale + settleMs);
  controller.timers.push(doneTimer);

  return controller;
}

export function dispatchTraceEvent(event, callbacks = {}) {
  const { message } = event;

  if (message.type === MESSAGE_TYPES.hands) {
    callbacks.onHands?.(event);
    return;
  }

  if (message.type === MESSAGE_TYPES.flap) {
    callbacks.onFlap?.(event);
    return;
  }

  callbacks.onMessage?.(event);
}
