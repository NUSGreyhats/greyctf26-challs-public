/**
 * Seamless hand loop: stable (LEVEL) → one 67 cross sequence → long stable hold.
 * Tuned for ~1 gesture flap per loop so local sim does not climb endlessly.
 *
 * delta = (1-leftY) - (1-rightY) = rightY - leftY  (via handHeight: left - right)
 * LEFT_HIGH: left height > right height + threshold
 */

export const SAMPLE_INTERVAL_MS = 1000 / 60;

/** Full loop period — start and end poses match for seamless tiling. */
export const GESTURE_LOOP_DURATION_MS = 2800;

const STABLE = { leftY: 0.47, rightY: 0.48 };

/** Strong asymmetry so smoothed heights still cross threshold. */
const LEFT_HIGH = { leftY: 0.36, rightY: 0.58 };
const RIGHT_HIGH = { leftY: 0.58, rightY: 0.36 };

/**
 * One 67 burst then hold stable for the rest of the loop (no second burst).
 * Plateaus at extremes; quick step into crosses, linear blend only on return to stable.
 */
const LOOP_KEYFRAMES = [
  { atMs: 0, ...STABLE },
  { atMs: 100, ...STABLE },
  { atMs: 160, ...LEFT_HIGH },
  { atMs: 240, ...LEFT_HIGH },
  { atMs: 300, ...STABLE },
  { atMs: 360, ...RIGHT_HIGH },
  { atMs: 440, ...RIGHT_HIGH },
  { atMs: 500, ...STABLE },
  { atMs: 560, ...LEFT_HIGH },
  { atMs: 640, ...LEFT_HIGH },
  { atMs: 720, ...STABLE },
  { atMs: 900, ...STABLE },
  { atMs: GESTURE_LOOP_DURATION_MS, ...STABLE },
];

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function posesEqual(a, b) {
  return a.leftY === b.leftY && a.rightY === b.rightY;
}

function isStable(pose) {
  return posesEqual(pose, STABLE);
}

/** Linear on stable holds; snap into extremes; ease out back to stable. */
function interpolateSegment(left, right, t) {
  if (posesEqual(left, right)) {
    return { leftY: left.leftY, rightY: left.rightY };
  }

  if (isStable(left) && !isStable(right)) {
    const snap = t < 0.35 ? 0 : (t - 0.35) / 0.65;
    return {
      leftY: lerp(left.leftY, right.leftY, snap),
      rightY: lerp(left.rightY, right.rightY, snap),
    };
  }

  if (!isStable(left) && isStable(right)) {
    const eased = 1 - Math.pow(1 - t, 2);
    return {
      leftY: lerp(left.leftY, right.leftY, eased),
      rightY: lerp(left.rightY, right.rightY, eased),
    };
  }

  return {
    leftY: lerp(left.leftY, right.leftY, t),
    rightY: lerp(left.rightY, right.rightY, t),
  };
}

function interpolateKeyframes(atMs) {
  const frames = LOOP_KEYFRAMES;
  if (atMs <= frames[0].atMs) {
    return { leftY: frames[0].leftY, rightY: frames[0].rightY };
  }

  for (let index = 0; index < frames.length - 1; index += 1) {
    const left = frames[index];
    const right = frames[index + 1];
    if (atMs >= left.atMs && atMs <= right.atMs) {
      const span = right.atMs - left.atMs || 1;
      const t = (atMs - left.atMs) / span;
      return interpolateSegment(left, right, t);
    }
  }

  const last = frames.at(-1);
  return { leftY: last.leftY, rightY: last.rightY };
}

/** Hand message at position in the seamless gesture loop. */
export function sampleGestureLoopAt(elapsedMs) {
  const loopMs = ((elapsedMs % GESTURE_LOOP_DURATION_MS) + GESTURE_LOOP_DURATION_MS) % GESTURE_LOOP_DURATION_MS;
  const { leftY, rightY } = interpolateKeyframes(loopMs);
  return {
    type: "hands",
    leftY,
    rightY,
    handCount: 2,
  };
}

/** Mock landmark hands for client GestureInterpreter.process(). */
export function mockHandsFromSample(sample) {
  const anchor = (x, y) => ({ x, y, z: 0 });
  return [
    [anchor(0.25, sample.leftY), anchor(0.26, sample.leftY), anchor(0.24, sample.leftY)],
    [anchor(0.75, sample.rightY), anchor(0.76, sample.rightY), anchor(0.74, sample.rightY)],
  ];
}

/** One period of loop samples as trace events. */
export function buildGestureLoopEvents(loopMs = GESTURE_LOOP_DURATION_MS) {
  const events = [];
  for (let atMs = 0; atMs <= loopMs; atMs += SAMPLE_INTERVAL_MS) {
    events.push({
      atMs,
      message: sampleGestureLoopAt(atMs),
    });
  }

  const first = events[0].message;
  const last = events.at(-1).message;
  last.leftY = first.leftY;
  last.rightY = first.rightY;
  return events;
}

/** Tile gesture loop for a longer run. */
export function tileGestureLoopEvents(durationMs) {
  const period = buildGestureLoopEvents();
  const periodMs = period.at(-1)?.atMs || GESTURE_LOOP_DURATION_MS;
  const tiled = [];

  for (let offset = 0; offset < durationMs; offset += periodMs) {
    for (const event of period) {
      const atMs = offset + event.atMs;
      if (atMs > durationMs) {
        break;
      }
      tiled.push({
        atMs,
        message: { ...event.message },
      });
    }
  }

  return tiled;
}
