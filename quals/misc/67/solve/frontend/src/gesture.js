export const DEFAULT_GESTURE_CONFIG = {
  crossThreshold: 0.08,
  minCrossesPerFlap: 2,
  trackingGraceMs: 420,
  anchorSmoothing: 0.45,
  fastAnchorSmoothing: 0.72,
  fastMovementThreshold: 0.075,
  jumpDebounceMs: 150,
  levelResetMs: 360,
};

export const FAST_HAND_LANDMARKER_OPTIONS = {
  runningMode: "VIDEO",
  numHands: 2,
  minHandDetectionConfidence: 0.35,
  minHandPresenceConfidence: 0.35,
  minTrackingConfidence: 0.25,
};

export class GestureInterpreter {
  constructor({ onFlap = () => {}, onTelemetry = () => {}, config = {} } = {}) {
    this.config = { ...DEFAULT_GESTURE_CONFIG, ...config };
    this.previousState = "NEUTRAL";
    this.crossedLevelBand = false;
    this.crossCount = 0;
    this.lastJumpAt = -Infinity;
    this.lastCrossAt = -Infinity;
    this.levelEnteredAt = null;
    this.lastSeenAt = 0;
    this.smoothedAnchors = [null, null];
    this.anchorVelocities = [null, null];
    this.lastAnchorTimes = [null, null];
    this.onFlap = onFlap;
    this.onTelemetry = onTelemetry;
  }

  updateConfig(config = {}) {
    this.config = { ...this.config, ...config };
  }

  reset() {
    this.previousState = "NEUTRAL";
    this.crossedLevelBand = false;
    this.crossCount = 0;
    this.lastJumpAt = -Infinity;
    this.lastCrossAt = -Infinity;
    this.levelEnteredAt = null;
    this.lastSeenAt = 0;
    this.smoothedAnchors = [null, null];
    this.anchorVelocities = [null, null];
    this.lastAnchorTimes = [null, null];
    this.emit({
      status: "NEUTRAL",
      handCount: 0,
      tracking: "reset",
      delta: null,
      triggered: false,
    });
  }

  process(hands, now = performance.now()) {
    const resolvedHands = this.resolveHands(hands, now);
    if (!resolvedHands) {
      return this.holdOrReset(now, hands.length);
    }

    const { leftAnchor, rightAnchor, tracking } = resolvedHands;
    if (hands.length >= 2) {
      this.lastSeenAt = now;
    }

    const delta = handHeight(leftAnchor) - handHeight(rightAnchor);
    const currentState = this.deltaState(delta);
    if (currentState === "LEVEL") {
      if (this.levelEnteredAt === null) {
        this.levelEnteredAt = now;
      }
      if (this.previousState !== "NEUTRAL") {
        this.crossedLevelBand = true;
      }
      const levelElapsedMs = now - this.levelEnteredAt;
      if (levelElapsedMs > this.config.levelResetMs) {
        this.previousState = "NEUTRAL";
        this.crossedLevelBand = false;
        this.crossCount = 0;
      }
      return this.emit({
        status: `LEVEL ${this.crossCount}/${this.config.minCrossesPerFlap}`,
        handCount: hands.length,
        tracking,
        leftAnchor,
        rightAnchor,
        delta,
        currentState: "LEVEL",
        triggered: false,
        levelElapsedMs,
      });
    }

    this.levelEnteredAt = null;
    let triggered = false;
    if (
      this.previousState !== "NEUTRAL" &&
      currentState !== this.previousState &&
      this.crossedLevelBand
    ) {
      this.lastCrossAt = now;
      const debounceRemainingMs = this.jumpDebounceRemaining(now);
      if (debounceRemainingMs <= 0) {
        this.crossCount += 1;
      } else {
        this.crossCount = 0;
      }

      if (this.crossCount >= this.config.minCrossesPerFlap) {
        this.onFlap("gesture");
        this.lastJumpAt = now;
        this.crossCount = 0;
        triggered = true;
      }
    }
    this.crossedLevelBand = false;
    this.previousState = currentState;

    return this.emit({
      status: `${currentState} ${this.crossCount}/${this.config.minCrossesPerFlap}`,
      handCount: hands.length,
      tracking,
      leftAnchor,
      rightAnchor,
      delta,
      currentState,
      triggered,
      jumpDebounceRemainingMs: this.jumpDebounceRemaining(now),
    });
  }

  deltaState(delta) {
    if (delta > this.config.crossThreshold) {
      return "LEFT_HIGH";
    }

    if (delta < -this.config.crossThreshold) {
      return "RIGHT_HIGH";
    }

    return "LEVEL";
  }

  resolveHands(hands, now) {
    if (hands.length >= 2) {
      const leftAnchor = this.smoothAnchor(0, handAnchorPoint(hands[0]), now);
      const rightAnchor = this.smoothAnchor(1, handAnchorPoint(hands[1]), now);
      if (!leftAnchor || !rightAnchor) {
        return null;
      }

      return { leftAnchor, rightAnchor, tracking: "active" };
    }

    if (now - this.lastSeenAt > this.config.trackingGraceMs) {
      return null;
    }

    if (hands.length === 0) {
      return this.predictedHands(now, "predicted");
    }

    if (hands.length !== 1) {
      return null;
    }

    const anchor = handAnchorPoint(hands[0]);
    if (!anchor) {
      return null;
    }

    const matchedIndex = this.matchSingleHandSlot(anchor);
    this.smoothAnchor(matchedIndex, anchor, now);
    const missingIndex = matchedIndex === 0 ? 1 : 0;
    const anchors = [...this.smoothedAnchors];
    anchors[missingIndex] = this.predictAnchor(missingIndex, now);
    const [leftAnchor, rightAnchor] = anchors;
    if (!leftAnchor || !rightAnchor) {
      return null;
    }

    return { leftAnchor, rightAnchor, tracking: "bridged" };
  }

  predictedHands(now, tracking) {
    const leftAnchor = this.predictAnchor(0, now);
    const rightAnchor = this.predictAnchor(1, now);
    if (!leftAnchor || !rightAnchor) {
      return null;
    }

    return { leftAnchor, rightAnchor, tracking };
  }

  matchSingleHandSlot(anchor) {
    return screenSideIndex(anchor);
  }

  smoothAnchor(index, anchor, now) {
    if (!anchor) {
      return null;
    }

    const previous = this.smoothedAnchors[index];
    if (!previous) {
      this.smoothedAnchors[index] = anchor;
      this.anchorVelocities[index] = { x: 0, y: 0, z: 0 };
      this.lastAnchorTimes[index] = now;
      return anchor;
    }

    const movement = Math.hypot(anchor.x - previous.x, anchor.y - previous.y);
    const smoothing =
      movement >= this.config.fastMovementThreshold
        ? Math.max(this.config.anchorSmoothing, this.config.fastAnchorSmoothing)
        : this.config.anchorSmoothing;
    const smoothed = {
      x: previous.x + (anchor.x - previous.x) * smoothing,
      y: previous.y + (anchor.y - previous.y) * smoothing,
      z: previous.z + (anchor.z - previous.z) * smoothing,
    };
    const previousTime = this.lastAnchorTimes[index];
    const elapsedMs = previousTime === null ? 0 : now - previousTime;
    if (elapsedMs > 0) {
      this.anchorVelocities[index] = {
        x: (smoothed.x - previous.x) / elapsedMs,
        y: (smoothed.y - previous.y) / elapsedMs,
        z: (smoothed.z - previous.z) / elapsedMs,
      };
    }
    this.lastAnchorTimes[index] = now;
    this.smoothedAnchors[index] = smoothed;
    return smoothed;
  }

  predictAnchor(index, now) {
    const anchor = this.smoothedAnchors[index];
    const velocity = this.anchorVelocities[index];
    const lastAnchorTime = this.lastAnchorTimes[index];
    if (!anchor || !velocity || lastAnchorTime === null) {
      return null;
    }

    const elapsedMs = now - lastAnchorTime;
    if (elapsedMs < 0 || elapsedMs > this.config.trackingGraceMs) {
      return null;
    }

    return {
      x: clamp(anchor.x + velocity.x * elapsedMs, 0, 1),
      y: clamp(anchor.y + velocity.y * elapsedMs, 0, 1),
      z: anchor.z + velocity.z * elapsedMs,
    };
  }

  holdOrReset(now, handCount = 0) {
    if (now - this.lastSeenAt <= this.config.trackingGraceMs) {
      return this.emit({
        status: "TRACKING HOLD",
        handCount,
        tracking: "hold",
        delta: null,
        triggered: false,
      });
    }

    this.previousState = "NEUTRAL";
    this.crossedLevelBand = false;
    this.crossCount = 0;
    this.lastJumpAt = -Infinity;
    this.lastCrossAt = -Infinity;
    this.levelEnteredAt = null;
    this.smoothedAnchors = [null, null];
    this.anchorVelocities = [null, null];
    this.lastAnchorTimes = [null, null];
    return this.emit({
      status: "NEUTRAL",
      handCount,
      tracking: "missing",
      delta: null,
      triggered: false,
    });
  }

  emit(event) {
    const telemetry = {
      timestamp: performance.now(),
      previousState: this.previousState,
      crossedLevelBand: this.crossedLevelBand,
      crossCount: this.crossCount,
      crossThreshold: this.config.crossThreshold,
      minCrossesPerFlap: this.config.minCrossesPerFlap,
      anchorSmoothing: this.config.anchorSmoothing,
      jumpDebounceMs: this.config.jumpDebounceMs,
      levelResetMs: this.config.levelResetMs,
      jumpDebounceRemainingMs: this.jumpDebounceRemaining(performance.now()),
      ...event,
    };
    this.onTelemetry(telemetry);
    return telemetry;
  }

  jumpDebounceRemaining(now) {
    return Math.max(0, this.config.jumpDebounceMs - (now - this.lastJumpAt));
  }
}

export function orderedHands(result) {
  const landmarks = result.landmarks || [];
  const handsBySide = [null, null];

  for (const handLandmarks of landmarks) {
    const anchor = handAnchorPoint(handLandmarks);
    if (!anchor) {
      continue;
    }

    const side = screenSideIndex(anchor);
    const candidate = {
      landmarks: handLandmarks,
      anchor,
      distanceFromSideCenter: Math.abs(anchor.x - (side === 0 ? 0.75 : 0.25)),
    };
    const current = handsBySide[side];
    if (!current || candidate.distanceFromSideCenter < current.distanceFromSideCenter) {
      handsBySide[side] = candidate;
    }
  }

  return handsBySide.filter(Boolean).map((hand) => hand.landmarks);
}

export function screenSideIndex(anchor) {
  return anchor.x >= 0.5 ? 0 : 1;
}

export function handAnchorPoint(hand) {
  const landmarks = hand.filter(
    (landmark) => landmark && Number.isFinite(landmark.x) && Number.isFinite(landmark.y),
  );
  if (!landmarks.length) {
    return null;
  }

  return {
    x: median(landmarks.map((landmark) => landmark.x)),
    y: median(landmarks.map((landmark) => landmark.y)),
    z: median(landmarks.map((landmark) => landmark.z || 0)),
  };
}

export function handHeight(anchor) {
  return 1 - anchor.y;
}

function median(values) {
  const sorted = [...values].sort((first, second) => first - second);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle];
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
