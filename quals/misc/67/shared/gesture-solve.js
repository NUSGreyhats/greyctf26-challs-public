import {
  WIN_SCORE,
  applyFlap,
  createGameState,
  stepGameState,
} from "./game-core.js";
import {
  SAMPLE_INTERVAL_MS,
  TICK_SECONDS,
  simulateWinningRun,
} from "./flap-solver.js";
import { normalizeTraceEvents } from "./frontend-client.js";

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

const DEFAULT_SPEED_PATTERN = [3.05, 3.28, 3.46, 3.18, 3.38, 3.12, 3.52];
const DEFAULT_STABLE = { leftY: 0.47, rightY: 0.48, handCount: 2 };
const LEADUP_SAMPLE_OFFSETS_MS = [3, 2, 1];

export function buildGestureSolvePack({
  loopTrace,
  targetScore = WIN_SCORE,
  overshoot = 1,
  maxSimMs = 130000,
  reverse = true,
  speedPattern = DEFAULT_SPEED_PATTERN,
  startDelayMs = 900,
  finalTailMs = 1200,
  stableIntervalMs = 180,
  strategy = "lookahead",
} = {}) {
  if (!loopTrace) {
    throw new Error("A stable -> 67 -> stable gesture trace is required.");
  }

  const planned = simulateWinningRun({
    targetScore: targetScore + overshoot,
    maxSimMs,
    motion: "camouflage",
    strategy,
  });

  if (planned.state.score < targetScore + overshoot) {
    throw new Error(
      `Mechanical planner stopped at score ${planned.state.score}; expected at least ${targetScore + overshoot}.`,
    );
  }

  const clip = prepareGestureClip(normalizeTraceEvents(loopTrace.events || loopTrace), { reverse });
  const desiredFlaps = planned.flapSchedule.map((entry) => entry.atMs + startDelayMs);
  const totalDurationMs = planned.simMs + startDelayMs + finalTailMs;
  const events = buildContinuousGestureTrace({
    clip,
    desiredFlaps,
    totalDurationMs,
    speedPattern,
    stableIntervalMs,
  });
  const replay = replayScoreFromGestureEvents(events);

  return {
    trace: buildTraceDocument(events, {
      result: replay.score >= targetScore ? "won" : "game-over",
      score: replay.score,
      claimScore: targetScore,
    }),
    planned,
    replay,
    clip,
    speedPattern,
    desiredFlaps,
  };
}

export function prepareGestureClip(
  events,
  { reverse = true, preTriggerHoldMs = 620, postTriggerHoldMs = 230 } = {},
) {
  const source = extractHandLoop(events);
  const durationMs = source.at(-1)?.atMs ?? 0;
  if (durationMs <= 0) {
    throw new Error("Gesture clip duration must be greater than 0.");
  }

  const oriented = reverse
    ? source
        .map((event) => ({
          atMs: durationMs - event.atMs,
          message: { ...event.message },
        }))
        .sort((left, right) => left.atMs - right.atMs)
    : source.map((event) => ({ atMs: event.atMs, message: { ...event.message } }));

  const firstPass = simulateGestureFlaps(oriented);
  if (firstPass.length !== 1) {
    throw new Error(
      `Gesture clip must produce exactly one gesture flap; observed ${firstPass.length}.`,
    );
  }

  const triggerAtMs = firstPass[0].triggerAtMs;
  const clipStartMs = Math.max(0, triggerAtMs - preTriggerHoldMs);
  const clipEndMs = Math.min(durationMs, triggerAtMs + postTriggerHoldMs);
  const trimmed = oriented
    .filter((event) => event.atMs >= clipStartMs && event.atMs <= clipEndMs)
    .map((event) => ({
      atMs: event.atMs - clipStartMs,
      message: { ...event.message },
    }));
  const last = trimmed.at(-1)?.message ?? DEFAULT_STABLE;
  if (clipEndMs - (trimmed.at(-1)?.atMs ?? 0) > SAMPLE_INTERVAL_MS * 0.5) {
    trimmed.push({
      atMs: clipEndMs - clipStartMs,
      message: {
        type: "hands",
        leftY: last.leftY,
        rightY: last.rightY,
        handCount: last.handCount ?? 2,
      },
    });
  }

  const trimmedPass = simulateGestureFlaps(trimmed);
  if (trimmedPass.length !== 1) {
    throw new Error(
      `Trimmed gesture clip must produce exactly one gesture flap; observed ${trimmedPass.length}.`,
    );
  }

  return {
    events: trimmed,
    durationMs: trimmed.at(-1)?.atMs ?? clipEndMs - clipStartMs,
    triggerAtMs: trimmedPass[0].triggerAtMs,
    auditAtMs: trimmedPass[0].auditAtMs,
    reversed: reverse,
  };
}

export function buildContinuousGestureTrace({
  clip,
  desiredFlaps,
  totalDurationMs,
  speedPattern = DEFAULT_SPEED_PATTERN,
  stableIntervalMs = 180,
} = {}) {
  const events = [];
  events.push({ atMs: 0, message: stableHandsAt(0) });
  events.push({ atMs: Math.round(totalDurationMs), message: stableHandsAt(totalDurationMs) });

  desiredFlaps.forEach((flapAtMs, index) => {
    const speed = speedForJump(index, speedPattern);
    const scaledClip = scaledGestureClip(clip, speed);
    const triggerAtMs = simulateGestureFlaps(scaledClip)[0]?.triggerAtMs;
    if (!Number.isFinite(triggerAtMs)) {
      throw new Error(`Scaled gesture clip at speed ${speed} did not trigger a flap.`);
    }
    for (const offsetMs of LEADUP_SAMPLE_OFFSETS_MS) {
      const sample = attenuateGestureSample(
        sampleClipAt(scaledClip, Math.max(0, triggerAtMs - offsetMs)),
      );
      events.push({
        atMs: Math.round(Math.max(0, flapAtMs - offsetMs)),
        message: {
          type: "hands",
          leftY: sample.leftY,
          rightY: sample.rightY,
          handCount: sample.handCount ?? 2,
        },
      });
    }
    events.push({
      atMs: Math.round(flapAtMs),
      message: { type: "flap", source: "gesture" },
    });
  });

  return events
    .filter((event) => event.atMs >= 0 && event.atMs <= totalDurationMs)
    .sort((left, right) => left.atMs - right.atMs || messagePriority(left) - messagePriority(right));
}

function scaledGestureClip(clip, speed) {
  return clip.events.map((event) => ({
    atMs: event.atMs / speed,
    message: { ...event.message },
  }));
}

function sampleClipAt(clipEvents, atMs) {
  let left = clipEvents[0];
  let right = clipEvents.at(-1);
  for (let index = 0; index < clipEvents.length - 1; index += 1) {
    if (clipEvents[index].atMs <= atMs && clipEvents[index + 1].atMs >= atMs) {
      left = clipEvents[index];
      right = clipEvents[index + 1];
      break;
    }
  }

  const span = Math.max(1, right.atMs - left.atMs);
  const t = clamp((atMs - left.atMs) / span, 0, 1);
  return {
    type: "hands",
    leftY: lerp(left.message.leftY, right.message.leftY, t),
    rightY: lerp(left.message.rightY, right.message.rightY, t),
    handCount: left.message.handCount ?? right.message.handCount ?? 2,
  };
}

function attenuateGestureSample(sample) {
  const leftHeight = 1 - sample.leftY;
  const rightHeight = 1 - sample.rightY;
  const averageHeight = (leftHeight + rightHeight) / 2;
  const delta = clamp((leftHeight - rightHeight) * 0.32, -0.055, 0.055);
  return {
    type: "hands",
    leftY: clamp(1 - (averageHeight + delta / 2), 0.12, 0.88),
    rightY: clamp(1 - (averageHeight - delta / 2), 0.12, 0.88),
    handCount: sample.handCount ?? 2,
  };
}

function lerp(left, right, t) {
  return left + (right - left) * t;
}

export function replayScoreFromGestureEvents(events) {
  const state = createGameState();
  const pendingFlaps = [];
  const interpreter = new ReplayGestureInterpreter({
    onFlap: (flap) => pendingFlaps.push(flap),
  });
  const sorted = [...events].sort((left, right) => left.atMs - right.atMs);
  let simMs = 0;

  const advanceTo = (targetMs) => {
    while (simMs + TICK_SECONDS * 1000 <= targetMs && !state.gameOver) {
      if (!state.awaitingStart) {
        stepGameState(state, TICK_SECONDS);
      }
      simMs += TICK_SECONDS * 1000;
    }

    const remainingMs = targetMs - simMs;
    if (remainingMs > 0.5 && !state.gameOver && !state.awaitingStart) {
      stepGameState(state, remainingMs / 1000);
      simMs = targetMs;
    }
  };

  for (const event of sorted) {
    if (event.message?.type === "hands") {
      interpreter.process(event.message, event.atMs);
      while (pendingFlaps.length > 0) {
        const flap = pendingFlaps.shift();
        advanceTo(flap.triggerAtMs);
        if (!state.gameOver) {
          applyFlap(state);
        }
      }
    }
  }

  const finalAtMs = sorted.at(-1)?.atMs;
  if (Number.isFinite(finalAtMs)) {
    advanceTo(finalAtMs);
  }

  return {
    score: state.score,
    gameOver: state.gameOver,
    flaps: interpreter.flaps,
  };
}

export function simulateGestureFlaps(events) {
  const interpreter = new ReplayGestureInterpreter();
  for (const event of events) {
    if (event.message?.type === "hands") {
      interpreter.process(event.message, event.atMs);
    }
  }
  return interpreter.flaps;
}

function stableHandsAt(atMs) {
  const drift = 0.006 * Math.sin(atMs / 310) + 0.003 * Math.sin(atMs / 97);
  return {
    type: "hands",
    leftY: clamp(DEFAULT_STABLE.leftY + drift, 0.12, 0.88),
    rightY: clamp(DEFAULT_STABLE.rightY + drift * 0.9, 0.12, 0.88),
    handCount: 2,
  };
}

function speedForJump(index, pattern) {
  const value = Number(pattern[index % pattern.length]);
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`Invalid replay speed at index ${index}: ${value}`);
  }
  return value;
}

function messagePriority(event) {
  return event.message?.type === "hands" ? 1 : 0;
}

class ReplayGestureInterpreter {
  constructor({ onFlap = () => {} } = {}) {
    this.onFlap = onFlap;
    this.flaps = [];
    this.reset();
  }

  reset() {
    this.previousState = "NEUTRAL";
    this.crossedLevelBand = false;
    this.crossCount = 0;
    this.sequenceStartedAt = null;
    this.lastJumpAt = -Infinity;
    this.levelEnteredAt = null;
    this.lastSeenAt = 0;
    this.heights = [null, null];
    this.heightVelocities = [0, 0];
    this.lastHeightTimes = [null, null];
  }

  process(sample, now) {
    if (sample.handCount < 2 || sample.leftY === null || sample.rightY === null) {
      return;
    }

    this.lastSeenAt = now;
    const leftHeight = this.smoothHeight(0, handHeight(sample.leftY), now);
    const rightHeight = this.smoothHeight(1, handHeight(sample.rightY), now);
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
      if (now - this.levelEnteredAt > GESTURE_CONFIG.levelResetMs) {
        this.previousState = "NEUTRAL";
        this.crossedLevelBand = false;
        this.crossCount = 0;
        this.sequenceStartedAt = null;
      }
      return;
    }

    this.levelEnteredAt = null;
    if (
      this.previousState !== "NEUTRAL" &&
      currentState !== this.previousState &&
      this.crossedLevelBand
    ) {
      if (this.jumpDebounceRemaining(now) <= 0) {
        this.crossCount += 1;
      } else {
        this.crossCount = 0;
        this.sequenceStartedAt = null;
      }

      if (this.crossCount >= GESTURE_CONFIG.minCrossesPerFlap) {
        const auditAtMs = this.sequenceStartedAt ?? now;
        this.flaps.push({ triggerAtMs: now, auditAtMs });
        this.onFlap({ triggerAtMs: now, auditAtMs });
        this.lastJumpAt = now;
        this.crossCount = 0;
        this.sequenceStartedAt = null;
      }
    }

    this.crossedLevelBand = false;
    this.previousState = currentState;
  }

  deltaState(delta) {
    if (delta > GESTURE_CONFIG.crossThreshold) {
      return "LEFT_HIGH";
    }
    if (delta < -GESTURE_CONFIG.crossThreshold) {
      return "RIGHT_HIGH";
    }
    return "LEVEL";
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
      movement >= GESTURE_CONFIG.fastMovementThreshold
        ? Math.max(GESTURE_CONFIG.anchorSmoothing, GESTURE_CONFIG.fastAnchorSmoothing)
        : GESTURE_CONFIG.anchorSmoothing;
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

  jumpDebounceRemaining(now) {
    return Math.max(0, GESTURE_CONFIG.jumpDebounceMs - (now - this.lastJumpAt));
  }
}

function handHeight(y) {
  return 1 - y;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function extractHandLoop(events) {
  const hands = events.filter((event) => event.message?.type === "hands");
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

function buildTraceDocument(events, meta = {}) {
  const handSamples = events.filter((event) => event.message.type === "hands").length;
  const flaps = events.filter((event) => event.message.type === "flap").length;

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
