import { SAMPLE_INTERVAL_MS, clamp } from "./trace-utils.mjs";

export function createSeededRandom(seed = 1) {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

/** Human-like alternating hands with slow drift (anti-cheat friendly). */
export function createHumanLikeSampleFactory(options = {}) {
  const random = createSeededRandom(options.seed ?? 42);
  const sampleIntervalMs = options.sampleIntervalMs ?? SAMPLE_INTERVAL_MS;
  let phase = random();
  let periodMs = options.periodMs ?? 360;
  let amplitude = options.amplitude ?? 0.2;
  let nextPeriodChangeAt = 0;
  const centerHeight = options.centerHeight ?? 0.56;

  return (elapsedMs) => {
    if (elapsedMs >= nextPeriodChangeAt) {
      periodMs = (options.periodMs ?? 340) + random() * 160;
      amplitude = (options.amplitude ?? 0.18) + random() * 0.06;
      nextPeriodChangeAt = elapsedMs + 900 + random() * 1200;
    }

    phase += sampleIntervalMs / periodMs;
    const triangle = phase % 2 < 1 ? (phase % 1) * 2 - 1 : 3 - (phase % 1) * 2;
    const noise = (random() - 0.5) * 0.04;
    const offset = amplitude * triangle + noise;
    const leftHeight = clamp(centerHeight + offset, 0.08, 0.92);
    const rightHeight = clamp(centerHeight - offset, 0.08, 0.92);

    return {
      leftY: 1 - leftHeight,
      rightY: 1 - rightHeight,
      handCount: 2,
    };
  };
}

/** Build a seamless loop where the last sample matches the first. */
export function recordHandLoop(loopMs, options = {}) {
  const sampleFor = createHumanLikeSampleFactory(options);
  const events = [];
  const totalMs = Math.max(SAMPLE_INTERVAL_MS, loopMs);
  let atMs = 0;

  while (atMs <= totalMs) {
    const sample = sampleFor(atMs);
    events.push({
      atMs,
      message: {
        type: "hands",
        leftY: sample.leftY,
        rightY: sample.rightY,
        handCount: sample.handCount,
      },
    });
    atMs += SAMPLE_INTERVAL_MS;
  }

  const first = events[0].message;
  const last = events.at(-1).message;
  last.leftY = first.leftY;
  last.rightY = first.rightY;
  last.handCount = first.handCount;

  return events;
}

/** Motion that stays below gesture crossThreshold (0.08) — camouflage without extra flaps. */
export function camouflageHandMessage(elapsedMs, options = {}) {
  const random = createSeededRandom(options.seed ?? 67);
  const midY = options.midY ?? 0.46;
  const wiggle = (options.wiggle ?? 0.018) * Math.sin(elapsedMs / (options.wigglePeriodMs ?? 240));
  const noise = (random() - 0.5) * 0.006;
  const leftY = midY + wiggle + noise;
  const rightY = midY - wiggle * 0.85 - noise;
  return {
    type: "hands",
    leftY: clamp(leftY, 0.12, 0.88),
    rightY: clamp(rightY, 0.12, 0.88),
    handCount: 2,
  };
}

export function handMessageAt(elapsedMs, options = {}) {
  if (options.camouflage) {
    return camouflageHandMessage(elapsedMs, options);
  }

  const sampleFor = createHumanLikeSampleFactory(options);
  const sample = sampleFor(elapsedMs);
  return {
    type: "hands",
    leftY: sample.leftY,
    rightY: sample.rightY,
    handCount: sample.handCount,
  };
}
