/**
 * Deterministic flappy solver using the same pipe RNG as shared/game-core.js.
 * Precomputes manual flap times from simulated physics + gap targeting.
 */
import {
  GAME_CONSTANTS,
  WIN_SCORE,
  applyFlap,
  createGameState,
  stepGameState,
} from "../../shared/game-core.js";

export const SAMPLE_INTERVAL_MS = 1000 / 60;
export const TICK_SECONDS = 1 / 60;
export const MIN_FLAP_INTERVAL_MS = 300;

export function gapCenterY(pipe, constants = GAME_CONSTANTS) {
  return pipe.gapY + constants.pipeGap * 0.5;
}

/** Pipes the bird is approaching (deterministic from current sim state). */
export function upcomingPipe(state, constants = GAME_CONSTANTS, lookaheadX = 240) {
  const birdX = constants.birdX;
  return (
    state.pipes
      .filter((pipe) => pipe.x + constants.pipeWidth > birdX - 5 && pipe.x < birdX + lookaheadX)
      .sort((left, right) => left.x - right.x)[0] || null
  );
}

const FLAP_STRATEGIES = {
  greedy(state, constants) {
    const target = upcomingPipe(state, constants);
    if (!target) {
      return state.birdY > constants.floorY - 150;
    }

    const center = gapCenterY(target, constants);
    if (state.birdY < center - 35) {
      return false;
    }

    return state.birdY > center + 25;
  },

  late(state, constants) {
    const target = upcomingPipe(state, constants);
    if (!target) {
      return state.birdY > constants.floorY - 120;
    }

    const center = gapCenterY(target, constants);
    return state.birdY > center + 38;
  },

  lookahead(state, constants) {
    if (!FLAP_STRATEGIES.greedy(state, constants)) {
      return false;
    }

    const target = upcomingPipe(state, constants);
    if (!target) {
      return true;
    }

    const center = gapCenterY(target, constants);
    const frames = 6;
    const dt = TICK_SECONDS;

    const simulate = (withFlap) => {
      const probe = {
        birdY: state.birdY,
        velocity: state.velocity,
        score: state.score,
        elapsed: state.elapsed,
        spawnTimer: state.spawnTimer,
        gameOver: false,
        awaitingStart: false,
        pipes: state.pipes.map((pipe) => ({ ...pipe })),
        nextPipeId: state.nextPipeId,
      };

      if (withFlap) {
        applyFlap(probe, constants);
      }

      for (let step = 0; step < frames; step += 1) {
        stepGameState(probe, dt, constants, { skipCollisions: true, skipBounds: true });
      }

      return probe;
    };

    const baseline = simulate(false);
    const withFlap = simulate(true);

    if (withFlap.birdY < state.birdY - 120) {
      return false;
    }

    return (
      Math.abs(withFlap.birdY - center) <=
      Math.abs(baseline.birdY - center) + 20
    );
  },
};

/** Heuristic flap decision from bird Y, velocity, and next gap. */
export function shouldFlap(state, constants = GAME_CONSTANTS, strategy = "greedy") {
  if (state.awaitingStart || state.gameOver) {
    return false;
  }

  const decide = FLAP_STRATEGIES[strategy] || FLAP_STRATEGIES.greedy;
  return decide(state, constants);
}

export function mechanicalHandMessage(elapsedMs, options = {}) {
  const periodMs = options.periodMs ?? 300;
  const amplitude = options.amplitude ?? 0.024;
  const midY = options.midY ?? 0.46;
  const phase = (elapsedMs / periodMs) * Math.PI * 2;
  const wiggle = amplitude * Math.sin(phase);
  const drift = amplitude * 0.4 * Math.sin(phase * 0.37 + 1.2);
  return {
    type: "hands",
    leftY: clamp(midY + wiggle + drift, 0.12, 0.88),
    rightY: clamp(midY - wiggle * 0.9, 0.12, 0.88),
    handCount: 2,
  };
}

/** Slow human-like drift without importing script-only helpers. */
export function humanLikeHandMessage(elapsedMs, seed = 67) {
  const random = seededRandom(seed);
  const periodMs = 340 + random() * 120;
  const amplitude = 0.17 + random() * 0.05;
  const phase = (elapsedMs / periodMs) * 2;
  const triangle = phase % 2 < 1 ? (phase % 1) * 2 - 1 : 3 - (phase % 1) * 2;
  const center = 0.56;
  const leftHeight = clamp(center + amplitude * triangle, 0.1, 0.9);
  const rightHeight = clamp(center - amplitude * triangle * 0.85, 0.1, 0.9);
  return {
    type: "hands",
    leftY: 1 - leftHeight,
    rightY: 1 - rightHeight,
    handCount: 2,
  };
}

export function camouflageHandMessage(elapsedMs, options = {}) {
  const midY = options.midY ?? 0.46;
  const wiggle = (options.wiggle ?? 0.018) * Math.sin(elapsedMs / (options.wigglePeriodMs ?? 240));
  const leftY = clamp(midY + wiggle, 0.12, 0.88);
  const rightY = clamp(midY - wiggle * 0.85, 0.12, 0.88);
  return {
    type: "hands",
    leftY,
    rightY,
    handCount: 2,
  };
}

export function sussyHandMessage(elapsedMs) {
  return sussyMechanicalHandMessage(elapsedMs, -Infinity);
}

export function sussyMechanicalHandMessage(elapsedMs, lastFlapAt = -Infinity) {
  const stableY = 0.48;
  const elapsedSinceFlap = elapsedMs - lastFlapAt;
  const pulseMs = 360;
  const pulse =
    elapsedSinceFlap >= 0 && elapsedSinceFlap <= pulseMs
      ? Math.sin((elapsedSinceFlap / pulseMs) * Math.PI)
      : 0;
  const stroke = -0.16 * pulse;
  return {
    type: "hands",
    leftY: clamp(stableY + stroke, 0.12, 0.88),
    rightY: clamp(stableY + stroke + 0.01, 0.12, 0.88),
    handCount: 2,
  };
}

export function straightJitterHandMessage(elapsedMs, lastFlapAt = -Infinity) {
  const stableY = 0.48;
  const elapsedSinceFlap = elapsedMs - lastFlapAt;
  const pulseMs = 420;
  const pulse =
    elapsedSinceFlap >= 0 && elapsedSinceFlap <= pulseMs
      ? Math.sin((elapsedSinceFlap / pulseMs) * Math.PI)
      : 0;
  const jitter = 0.012 * Math.sin(elapsedMs / 34) + 0.007 * Math.sin(elapsedMs / 17);
  const stroke = -0.13 * pulse + jitter;
  return {
    type: "hands",
    leftY: clamp(stableY + stroke, 0.12, 0.88),
    rightY: clamp(stableY + stroke, 0.12, 0.88),
    handCount: 2,
  };
}

export function exact67HandMessage(relativeMs) {
  const stable = { leftY: 0.47, rightY: 0.48 };
  const leftHigh = { leftY: 0.34, rightY: 0.6 };
  const rightHigh = { leftY: 0.6, rightY: 0.34 };
  const frames = [
    { atMs: -330, ...stable },
    { atMs: -280, ...leftHigh },
    { atMs: -220, ...leftHigh },
    { atMs: -170, ...stable },
    { atMs: -120, ...rightHigh },
    { atMs: -60, ...rightHigh },
    { atMs: -20, ...stable },
    { atMs: 0, ...stable },
  ];

  if (relativeMs <= frames[0].atMs) {
    return { type: "hands", ...stable, handCount: 2 };
  }

  for (let index = 0; index < frames.length - 1; index += 1) {
    const left = frames[index];
    const right = frames[index + 1];
    if (relativeMs >= left.atMs && relativeMs <= right.atMs) {
      const span = right.atMs - left.atMs || 1;
      const t = (relativeMs - left.atMs) / span;
      return {
        type: "hands",
        leftY: lerp(left.leftY, right.leftY, t),
        rightY: lerp(left.rightY, right.rightY, t),
        handCount: 2,
      };
    }
  }

  return { type: "hands", ...stable, handCount: 2 };
}

export function exact67JitterHandMessage(index) {
  const leftHigh = { leftY: 0.34, rightY: 0.6 };
  const rightHigh = { leftY: 0.6, rightY: 0.34 };
  const frame = index % 2 === 0 ? leftHigh : rightHigh;
  return {
    type: "hands",
    ...frame,
    handCount: 2,
  };
}

function handMessageAt(elapsedMs, motion, loopDurationMs, lastFlapAt = -Infinity) {
  if (motion === "sussy") {
    return sussyMechanicalHandMessage(elapsedMs, lastFlapAt);
  }
  if (motion === "straight-jitter") {
    return straightJitterHandMessage(elapsedMs, lastFlapAt);
  }
  if (motion === "mechanical") {
    return mechanicalHandMessage(elapsedMs, { periodMs: loopDurationMs });
  }
  if (motion === "human") {
    return humanLikeHandMessage(elapsedMs);
  }
  return camouflageHandMessage(elapsedMs, { wigglePeriodMs: loopDurationMs / 2 });
}

/**
 * Forward-simulate: record hands + manual flaps until targetScore or game over.
 * Returns events sorted by atMs and final state (pipes/score are deterministic).
 */
export function simulateWinningRun({
  targetScore = WIN_SCORE,
  maxSimMs = 130000,
  motion = "camouflage",
  strategy = "greedy",
  loopDurationMs = 240,
  flapJitterMs = 80,
  seed = 67,
} = {}) {
  const constants = GAME_CONSTANTS;
  const state = createGameState();
  const events = [];
  let simMs = 0;
  let lastFlapAt = -Infinity;
  let flapIndex = 0;
  const flapSchedule = [];

  events.push({ atMs: 0, message: { type: "flap", source: "manual" } });
  applyFlap(state, constants);
  lastFlapAt = 0;
  flapSchedule.push({ atMs: 0, birdY: state.birdY, score: state.score });

  const random = seededRandom(seed);

  while (!state.gameOver && state.score < targetScore && simMs < maxSimMs) {
    events.push({
      atMs: simMs,
      message: handMessageAt(simMs, motion, loopDurationMs, lastFlapAt),
    });

    const flapGap = MIN_FLAP_INTERVAL_MS + (random() - 0.5) * flapJitterMs;
    if (shouldFlap(state, constants, strategy) && simMs - lastFlapAt >= flapGap) {
      events.push({
        atMs: simMs,
        message: { type: "flap", source: "manual" },
      });
      applyFlap(state, constants);
      lastFlapAt = simMs;
      flapIndex += 1;
      const pipe = upcomingPipe(state, constants);
      flapSchedule.push({
        atMs: simMs,
        birdY: state.birdY,
        score: state.score,
        gapY: pipe?.gapY ?? null,
        gapCenter: pipe ? gapCenterY(pipe, constants) : null,
      });
    }

    stepGameState(state, TICK_SECONDS, constants);
    simMs += SAMPLE_INTERVAL_MS;
  }

  return {
    state,
    events: events.sort((left, right) => left.atMs - right.atMs),
    simMs,
    flapSchedule,
    pipes: state.pipes.map((pipe) => ({ ...pipe })),
  };
}

/** Replay-style score check (flaps only, matches server verify physics). */
export function replayScoreFromFlapEvents(events, constants = GAME_CONSTANTS) {
  const state = createGameState();
  const tickMs = TICK_SECONDS * 1000;
  let simMs = 0;
  const sorted = [...events].sort((left, right) => left.atMs - right.atMs);

  applyFlap(state, constants);

  for (const event of sorted) {
    if (event.message?.type !== "flap" && event.type !== "flap") {
      continue;
    }

    const atMs = event.atMs;
    while (simMs + tickMs <= atMs && !state.gameOver) {
      if (!state.awaitingStart) {
        stepGameState(state, TICK_SECONDS, constants);
      }
      simMs += tickMs;
    }

    const remainingMs = atMs - simMs;
    if (remainingMs > 0.5 && !state.gameOver && !state.awaitingStart) {
      stepGameState(state, remainingMs / 1000, constants);
      simMs = atMs;
    }

    applyFlap(state, constants);
  }

  return state.score;
}

export function buildSolveTrace(options = {}) {
  const targetScore = options.targetScore ?? WIN_SCORE;
  const overshoot = options.overshoot ?? 1;
  const buildTarget = targetScore + overshoot;
  const result = simulateWinningRun({
    ...options,
    targetScore: buildTarget,
  });
  const replayScore = replayScoreFromFlapEvents(result.events);

  return {
    events: result.events,
    score: result.state.score,
    claimScore: targetScore,
    replayScore,
    flapSchedule: result.flapSchedule,
    simMs: result.simMs,
    won: result.state.score >= targetScore,
    strategy: options.strategy || "greedy",
    motion: options.motion || "camouflage",
  };
}

export function buildExact67GestureTrace(options = {}) {
  const targetScore = options.targetScore ?? WIN_SCORE;
  const planned = simulateWinningRun({
    ...options,
    targetScore,
    motion: "camouflage",
    strategy: "greedy",
  });
  const events = [];
  const samplesPerFlap = 12;

  for (const flap of planned.flapSchedule) {
    const atMs = Math.round(flap.atMs);
    for (let index = 0; index < samplesPerFlap; index += 1) {
      events.push({
        atMs,
        message: exact67JitterHandMessage(index),
      });
    }
    events.push({
      atMs,
      message: { type: "flap", source: "gesture" },
    });
  }

  events.push({
    atMs: Math.round(planned.simMs + 800),
    message: exact67HandMessage(-330),
  });

  const sorted = events.sort((left, right) => left.atMs - right.atMs);
  const replayScore = replayScoreFromTimedEvents(sorted);

  return {
    events: sorted,
    score: replayScore,
    claimScore: targetScore,
    replayScore,
    simMs: planned.simMs,
    flapSchedule: planned.flapSchedule,
    won: replayScore >= targetScore,
    note:
      "Exact repeated alternating 67-hand bursts with gesture-source flaps; expected to trip anti-cheat jitter checks.",
  };
}

export function replayScoreFromTimedEvents(events, constants = GAME_CONSTANTS) {
  const state = createGameState();
  const tickMs = TICK_SECONDS * 1000;
  let simMs = 0;

  for (const event of events) {
    const atMs = event.atMs;
    while (simMs + tickMs <= atMs && !state.gameOver) {
      if (!state.awaitingStart) {
        stepGameState(state, TICK_SECONDS, constants);
      }
      simMs += tickMs;
    }

    const remainingMs = atMs - simMs;
    if (remainingMs > 0.5 && !state.gameOver && !state.awaitingStart) {
      stepGameState(state, remainingMs / 1000, constants);
      simMs = atMs;
    }

    if (event.message?.type === "flap") {
      applyFlap(state, constants);
    }
  }

  return state.score;
}

function seededRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function lerp(left, right, t) {
  return left + (right - left) * t;
}
