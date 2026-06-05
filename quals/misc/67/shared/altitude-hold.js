/**
 * Hysteresis altitude hold for local / scripted play.
 * Flap when the bird falls below a band, re-arm after it rises back into range.
 *
 * Coordinates: higher birdY = lower on screen (floorY ≈ 492).
 */
import {
  WIN_SCORE,
  applyFlap,
  createGameState,
  stepGameState,
  GAME_CONSTANTS,
} from "./game-core.js";
import {
  SAMPLE_INTERVAL_MS,
  TICK_SECONDS,
  gapCenterY,
  replayScoreFromFlapEvents,
  upcomingPipe,
} from "./flap-solver.js";
import { flapMessage, handsMessage, normalizeTraceEvents } from "./frontend-client.js";

export const DEFAULT_ALTITUDE_HOLD = {
  /** Desired hover height (px). */
  targetY: 268,
  /** Flap once bird falls this far below target (birdY > target + flapBelow). */
  flapBelow: 30,
  /** Re-arm after bird rises to target - resetAbove (birdY < target - resetAbove). */
  resetAbove: 18,
  /** Do not flap when bird center is above target - tooHigh (near sky ceiling). */
  tooHigh: 55,
  /** Do not flap when bird would be too close to floor after impulse. */
  floorGuard: 40,
  /** Do not flap again until this long after the last flap. */
  minFlapIntervalMs: 360,
  /** When false, flap on position only (smoother hold). */
  requireFalling: false,
  fallingVelocity: 60,
  /** Clamp target and block ceiling flaps using frame limits. */
  respectFrameBounds: false,
};

/** Safe hover band inside floor/ceiling (bird center Y). */
export function computeFrameHoldBand(constants = GAME_CONSTANTS) {
  const radius = constants.birdRadius;
  const minY = radius + 12;
  const maxY = constants.floorY - radius - 12;
  const targetY = clamp(DEFAULT_ALTITUDE_HOLD.targetY, minY + 50, maxY - 50);
  return { minY, maxY, targetY };
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export function createAltitudeHoldController(options = {}) {
  const constants = options.constants || GAME_CONSTANTS;
  const frameBand = options.frameBand || computeFrameHoldBand(constants);
  const config = {
    ...DEFAULT_ALTITUDE_HOLD,
    ...options,
    constants,
    frameBand,
  };
  let lastFlapAt = -Infinity;
  let armed = true;

  return {
    config,
    frameBand,
    reset() {
      lastFlapAt = -Infinity;
      armed = true;
    },
    resolveTargetY(state) {
      const raw =
        typeof config.getTargetY === "function" ? config.getTargetY(state) : config.targetY;
      if (!config.respectFrameBounds) {
        return raw;
      }
      return clamp(raw, frameBand.minY, frameBand.maxY);
    },
    shouldFlap(state, now = performance.now()) {
      if (!state || state.awaitingStart || state.gameOver) {
        return false;
      }

      if (now - lastFlapAt < config.minFlapIntervalMs) {
        return false;
      }

      const { birdY, velocity } = state;
      const { flapBelow, resetAbove, tooHigh, floorGuard, requireFalling, fallingVelocity } =
        config;
      const targetY = this.resolveTargetY(state);

      if (config.respectFrameBounds && birdY < frameBand.minY) {
        return false;
      }

      if (!armed && birdY < targetY - resetAbove) {
        armed = true;
      }

      if (birdY < targetY - tooHigh) {
        return false;
      }

      const fellTooLow = birdY > targetY + flapBelow;
      const nearFloor = config.respectFrameBounds && birdY > frameBand.maxY - floorGuard;
      const falling = !requireFalling || velocity > fallingVelocity;

      if (armed && fellTooLow && !nearFloor && falling) {
        lastFlapAt = now;
        armed = false;
        return true;
      }

      return false;
    },
  };
}

/** Offline tune: returns flap count and birdY min/max over a run. */
export function simulateAltitudeHold({
  durationMs = 15000,
  constants = GAME_CONSTANTS,
  holdOptions = {},
  tickSeconds = 1 / 60,
} = {}) {
  const hold = createAltitudeHoldController(holdOptions);
  const state = createGameState();
  const flapTimes = [];
  let simMs = 0;
  let minY = Infinity;
  let maxY = -Infinity;

  applyFlap(state, constants);
  flapTimes.push(0);

  while (!state.gameOver && simMs < durationMs) {
    if (hold.shouldFlap(state, simMs)) {
      applyFlap(state, constants);
      flapTimes.push(simMs);
    }

    stepGameState(state, tickSeconds, constants);
    simMs += tickSeconds * 1000;
    minY = Math.min(minY, state.birdY);
    maxY = Math.max(maxY, state.birdY);
  }

  return {
    flapCount: flapTimes.length,
    minY,
    maxY,
    span: maxY - minY,
    finalY: state.birdY,
    score: state.score,
  };
}

/**
 * Record a full trace using altitude hold until targetScore or maxSimMs.
 * @param {object} options
 * @param {boolean} [options.passPipeGap] - pass through gap only; still hit pipe caps
 * @param {boolean} [options.skipCollisions] - pass through all pipe solids
 * @param {boolean} [options.skipBounds] - ignore floor/ceiling
 */
export function buildAltitudeHoldTrace({
  targetScore = WIN_SCORE,
  maxSimMs = 120000,
  holdOptions = {},
  passPipeGap = false,
  skipCollisions = false,
  skipBounds = false,
  constants = GAME_CONSTANTS,
  handAtMs = (simMs) =>
    handsMessage({
      leftY: 0.45 + 0.02 * Math.sin(simMs / 280),
      rightY: 0.55 - 0.02 * Math.sin(simMs / 280),
      handCount: 2,
    }),
} = {}) {
  const stepOptions = {
    passPipeGap: passPipeGap === true,
    skipCollisions: skipCollisions === true,
    skipBounds: skipBounds === true,
  };
  const holdOptionsResolved = { ...holdOptions };
  if (passPipeGap && !holdOptionsResolved.getTargetY) {
    holdOptionsResolved.getTargetY = (simState) => {
      const pipe = upcomingPipe(simState, constants);
      return pipe ? gapCenterY(pipe, constants) : DEFAULT_ALTITUDE_HOLD.targetY;
    };
  }

  const hold = createAltitudeHoldController({
    ...holdOptionsResolved,
    respectFrameBounds: !stepOptions.skipBounds,
    constants,
  });
  const state = createGameState({}, constants);
  const events = [];
  let simMs = 0;

  events.push({ atMs: 0, message: flapMessage("manual") });
  applyFlap(state, constants);

  while (!state.gameOver && state.score < targetScore && simMs < maxSimMs) {
    events.push({ atMs: simMs, message: handAtMs(simMs) });

    if (hold.shouldFlap(state, simMs)) {
      events.push({ atMs: simMs, message: flapMessage("manual") });
      applyFlap(state, constants);
    }

    stepGameState(state, TICK_SECONDS, constants, stepOptions);
    simMs += SAMPLE_INTERVAL_MS;
  }

  const sorted = normalizeTraceEvents(events);
  const replayScore = replayScoreFromFlapEvents(sorted, constants);

  return {
    events: sorted,
    score: state.score,
    claimScore: targetScore,
    replayScore,
    localOnly: true,
    stepOptions,
    simMs,
    holdConfig: hold.config,
    note: describeNoCollisionNote(stepOptions),
  };
}

function describeNoCollisionNote(stepOptions) {
  if (stepOptions.skipCollisions && stepOptions.skipBounds) {
    return "Local god-mode: no pipe or frame collision. Server verify uses real physics.";
  }
  if (stepOptions.skipCollisions && !stepOptions.skipBounds) {
    return "Local: pass through all pipe solids (incl. caps); floor/ceiling still kill. Altitude hold band.";
  }
  if (stepOptions.passPipeGap) {
    return "Local: pass through pipe gaps only; pipe caps still kill.";
  }
  return "Altitude hold trace.";
}

export function buildNoCollisionPipesTrace(options = {}) {
  return buildAltitudeHoldTrace({
    ...options,
    passPipeGap: false,
    skipCollisions: true,
    skipBounds: false,
  });
}

export function buildNoCollisionPipesFrameTrace(options = {}) {
  return buildAltitudeHoldTrace({
    ...options,
    skipCollisions: true,
    skipBounds: true,
  });
}

export function localSimOptionsForMode(modeId) {
  if (modeId === "no-collision-pipes") {
    return { skipCollisions: true, skipBounds: false, passPipeGap: false };
  }
  if (modeId === "no-collision-pipes-frame" || modeId === "no-collision") {
    return { skipCollisions: true, skipBounds: true, passPipeGap: false };
  }
  return null;
}
