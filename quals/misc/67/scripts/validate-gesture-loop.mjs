#!/usr/bin/env node
/** Verify gesture loop triggers ServerGestureInterpreter flaps. */
import {
  GESTURE_LOOP_DURATION_MS,
  buildGestureLoopEvents,
} from "../shared/gesture-loop.js";

const CONFIG = {
  crossThreshold: 0.08,
  minCrossesPerFlap: 2,
  jumpDebounceMs: 150,
  levelResetMs: 360,
  anchorSmoothing: 0.45,
  fastAnchorSmoothing: 0.72,
  fastMovementThreshold: 0.075,
};

function handHeight(y) {
  return 1 - y;
}

function deltaState(delta) {
  if (delta > CONFIG.crossThreshold) return "LEFT_HIGH";
  if (delta < -CONFIG.crossThreshold) return "RIGHT_HIGH";
  return "LEVEL";
}

function simulateGesture(samples) {
  let previousState = "NEUTRAL";
  let crossedLevelBand = false;
  let crossCount = 0;
  let lastJumpAt = -Infinity;
  let levelEnteredAt = null;
  const heights = [null, null];
  const lastHeightTimes = [null, null];
  const flapTimes = [];

  for (const { atMs, leftY, rightY } of samples) {
    const rawLeft = handHeight(leftY);
    const rawRight = handHeight(rightY);
    let smooth = CONFIG.anchorSmoothing;
    if (heights[0] !== null && heights[1] !== null) {
      const dt = 1 / 60;
      const lv = (rawLeft - heights[0]) / dt;
      const rv = (rawRight - heights[1]) / dt;
      if (Math.abs(lv) + Math.abs(rv) > CONFIG.fastMovementThreshold) {
        smooth = CONFIG.fastAnchorSmoothing;
      }
    }

    const leftHeight =
      heights[0] === null ? rawLeft : heights[0] * (1 - smooth) + rawLeft * smooth;
    const rightHeight =
      heights[1] === null ? rawRight : heights[1] * (1 - smooth) + rawRight * smooth;
    heights[0] = leftHeight;
    heights[1] = rightHeight;

    const delta = leftHeight - rightHeight;
    const currentState = deltaState(delta);

    if (currentState === "LEVEL") {
      if (levelEnteredAt === null) levelEnteredAt = atMs;
      if (previousState !== "NEUTRAL") crossedLevelBand = true;
      if (atMs - levelEnteredAt > CONFIG.levelResetMs) {
        previousState = "NEUTRAL";
        crossedLevelBand = false;
        crossCount = 0;
      }
      continue;
    }

    levelEnteredAt = null;
    if (previousState !== "NEUTRAL" && currentState !== previousState && crossedLevelBand) {
      if (atMs - lastJumpAt >= CONFIG.jumpDebounceMs) {
        crossCount += 1;
      } else {
        crossCount = 0;
      }
      if (crossCount >= CONFIG.minCrossesPerFlap) {
        flapTimes.push(atMs);
        lastJumpAt = atMs;
        crossCount = 0;
      }
    }
    crossedLevelBand = false;
    previousState = currentState;
  }

  return flapTimes;
}

const events = buildGestureLoopEvents();
const samples = events.map((e) => ({ atMs: e.atMs, ...e.message }));
const flapTimes = simulateGesture(samples);

console.log(`Loop ${GESTURE_LOOP_DURATION_MS}ms, ${events.length} samples`);
console.log(`Gesture flaps per loop: ${flapTimes.length} at ms [${flapTimes.join(", ")}]`);
if (flapTimes.length < 1) {
  console.error("Loop does not trigger a flap — adjust keyframes.");
  process.exitCode = 1;
} else if (flapTimes.length > 1) {
  console.error(`Loop triggers ${flapTimes.length} flaps per period — expected 1 (bird climbs).`);
  process.exitCode = 1;
} else {
  const firstFlap = flapTimes[0];
  console.log(`First flap at ${firstFlap}ms (${(firstFlap / 1000).toFixed(2)}s into loop)`);
}
