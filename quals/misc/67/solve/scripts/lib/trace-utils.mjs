import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

export const SAMPLE_INTERVAL_MS = 1000 / 60;

export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export function loadTrace(path) {
  const trace = JSON.parse(readFileSync(resolve(path), "utf8"));
  if (!trace?.events?.length) {
    throw new Error(`Trace at ${path} has no events.`);
  }
  return trace;
}

export function writeTrace(path, trace) {
  writeFileSync(resolve(path), `${JSON.stringify(trace, null, 2)}\n`, "utf8");
}

export function summarizeTrace(trace) {
  const handEvents = trace.events.filter((event) => event.message?.type === "hands");
  const dualHands = handEvents.filter(
    (event) =>
      Number.isFinite(event.message.leftY) && Number.isFinite(event.message.rightY),
  ).length;
  const durationMs = trace.events.at(-1)?.atMs || 0;
  return {
    events: trace.events.length,
    handEvents: handEvents.length,
    dualHands,
    flaps: trace.flaps || trace.events.filter((event) => event.message?.type === "flap").length,
    durationMs,
  };
}

export function normalizeTraceEvents(trace) {
  return trace.events
    .filter((event) => event?.message?.type && event.message.type !== "restart")
    .map((event) => ({
      atMs: event.atMs,
      message: structuredClone(event.message),
    }))
    .sort((left, right) => left.atMs - right.atMs);
}

export function scaleTraceEvents(events, scale) {
  if (!Number.isFinite(scale) || scale <= 0) {
    throw new Error(`Invalid --scale value: ${scale}`);
  }

  return events.map((event) => ({
    ...event,
    atMs: Math.round(event.atMs * scale),
  }));
}

export function filterHandsOnly(events) {
  return events.filter((event) => event.message.type === "hands");
}

export function extractHandLoop(events) {
  const hands = filterHandsOnly(events);
  if (!hands.length) {
    throw new Error("No hand samples to extract as a loop.");
  }

  return hands.map((event) => ({
    atMs: event.atMs,
    message: {
      type: "hands",
      leftY: event.message.leftY,
      rightY: event.message.rightY,
      handCount: event.message.handCount ?? 2,
    },
  }));
}

export function tileHandLoop(loopEvents, durationMs) {
  if (!loopEvents.length) {
    throw new Error("Cannot tile an empty loop.");
  }

  const loopDurationMs = loopEvents.at(-1).atMs || SAMPLE_INTERVAL_MS;
  const tiled = [];

  for (let offset = 0; offset < durationMs; offset += loopDurationMs) {
    for (const event of loopEvents) {
      const atMs = offset + event.atMs;
      if (atMs > durationMs) {
        break;
      }
      tiled.push({
        atMs,
        message: structuredClone(event.message),
      });
    }
  }

  return tiled;
}

export function mergeTraceEvents(baseEvents, overlayEvents) {
  return [...baseEvents, ...overlayEvents].sort((left, right) => left.atMs - right.atMs);
}

export function buildTraceDocument(events, meta = {}) {
  const handSamples = events.filter((event) => event.message.type === "hands").length;
  const flaps = events.filter((event) => event.message.type === "flap").length;
  const durationMs = events.at(-1)?.atMs || 0;

  return {
    version: 1,
    createdAt: new Date().toISOString(),
    target: meta.target || "ws://127.0.0.1:8787/ws",
    startedAt: null,
    completedAt: meta.completedAt || new Date().toISOString(),
    result: meta.result || "built",
    score: meta.score ?? 0,
    claimScore: meta.claimScore ?? meta.score ?? 0,
    handSamples,
    flaps,
    events,
  };
}

export function parseArgs(argv) {
  const positional = [];
  const flags = {};

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--scale") {
      flags.scale = Number(argv[index + 1]);
      index += 1;
      continue;
    }
    if (token === "--tile") {
      flags.tile = argv[index + 1];
      index += 1;
      continue;
    }
    if (token === "--duration") {
      flags.duration = Number(argv[index + 1]);
      index += 1;
      continue;
    }
    if (token === "--hands-only") {
      flags.handsOnly = true;
      continue;
    }
    if (token === "--manual") {
      flags.manual = true;
      continue;
    }
    if (token === "--forward") {
      flags.forward = true;
      continue;
    }
    if (token === "--motion") {
      flags.motion = argv[index + 1];
      index += 1;
      continue;
    }
    if (token === "--strategy") {
      flags.strategy = argv[index + 1];
      index += 1;
      continue;
    }
    if (token === "--direction") {
      flags.direction = argv[index + 1];
      index += 1;
      continue;
    }
    if (token === "--unit-speeds") {
      flags.unitSpeeds = argv[index + 1];
      index += 1;
      continue;
    }
    if (token === "--output" || token === "-o") {
      flags.output = argv[index + 1];
      index += 1;
      continue;
    }
    if (token === "--loop-ms") {
      flags.loopMs = Number(argv[index + 1]);
      index += 1;
      continue;
    }
    if (token === "--period") {
      flags.period = Number(argv[index + 1]);
      index += 1;
      continue;
    }
    if (token === "--seed") {
      flags.seed = Number(argv[index + 1]);
      index += 1;
      continue;
    }
    if (token.startsWith("--")) {
      throw new Error(`Unknown flag: ${token}`);
    }
    positional.push(token);
  }

  return { positional, flags };
}
