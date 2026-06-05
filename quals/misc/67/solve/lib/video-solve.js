import { WIN_SCORE } from "../../shared/game-core.js";
import {
  SAMPLE_INTERVAL_MS,
  simulateWinningRun,
} from "./flap-solver.js";
import { normalizeTraceEvents } from "../../shared/frontend-client.js";
import {
  simulateGestureFlaps,
  replayScoreFromGestureEvents,
} from "./gesture-solve.js";

const DEFAULT_SPEED_PATTERN = [2.85, 3.05, 3.22, 2.96, 3.14, 2.9, 3.28];
const DEFAULT_UNIT_SECTION_SPEED_PATTERN = [
  { lead: 1, gesture: 1, recovery: 1, settle: 1 },
];
const DEFAULT_STABLE_SAMPLE_INTERVAL_MS = SAMPLE_INTERVAL_MS;
const DEFAULT_VIDEO_FRAME_INTERVAL_MS = 120;
const DEFAULT_PRE_TRIGGER_HOLD_MS = 620;
const DEFAULT_POST_TRIGGER_HOLD_MS = 320;
const DEFAULT_PRE_ACTION_CONTEXT_MS = 260;
const DEFAULT_START_DELAY_MS = 900;
const DEFAULT_FINAL_TAIL_MS = 300;
const DEFAULT_STABLE = { leftY: 0.47, rightY: 0.48, handCount: 2 };

export function buildVideoSolvePlan({
  clipTrace,
  targetScore = WIN_SCORE,
  overshoot = 0,
  maxSimMs = 130000,
  strategy = "lookahead",
  directionPattern = "pingpong",
  speedPattern = DEFAULT_SPEED_PATTERN,
  unitSectionSpeedPattern = DEFAULT_UNIT_SECTION_SPEED_PATTERN,
  sampleIntervalMs = DEFAULT_STABLE_SAMPLE_INTERVAL_MS,
  videoFrameIntervalMs = DEFAULT_VIDEO_FRAME_INTERVAL_MS,
  startDelayMs = DEFAULT_START_DELAY_MS,
  finalTailMs = DEFAULT_FINAL_TAIL_MS,
  preTriggerHoldMs = DEFAULT_PRE_TRIGGER_HOLD_MS,
  postTriggerHoldMs = DEFAULT_POST_TRIGGER_HOLD_MS,
} = {}) {
  if (!clipTrace) {
    throw new Error("A cropped stable -> 67 -> stable recording trace is required.");
  }

  const source = prepareSourceGestureClip(normalizeTraceEvents(clipTrace.events || clipTrace), {
    preTriggerHoldMs,
    postTriggerHoldMs,
  });
  const planned = simulateWinningRun({
    targetScore: targetScore + overshoot,
    maxSimMs,
    motion: "camouflage",
    strategy,
  });

  if (planned.state.score < targetScore + overshoot) {
    throw new Error(
      `Jump planner stopped at score ${planned.state.score}; expected at least ${targetScore + overshoot}.`,
    );
  }

  const plannedFlaps = planned.flapSchedule.map((entry) => entry.atMs + startDelayMs);
  let desiredFlaps = plannedFlaps;
  const totalDurationMs = planned.simMs + startDelayMs + finalTailMs;
  let windows = [];
  let events = [];
  let fullReplay = null;
  for (let attempt = 0; attempt < 6; attempt += 1) {
    windows = buildGestureWindows({
      source,
      desiredFlaps,
      directionPattern,
      speedPattern,
      unitSectionSpeedPattern,
      totalDurationMs,
    });
    events = buildTimelineEvents({
      source,
      windows,
      totalDurationMs,
      intervalMs: sampleIntervalMs,
    });
    fullReplay = replayScoreFromGestureEvents(events);
    if (fullReplay.score >= targetScore || fullReplay.flaps.length === 0) {
      break;
    }
    desiredFlaps = calibrateDesiredFlaps(plannedFlaps, fullReplay.flaps);
  }
  const frames = buildTimelineFrames({
    source,
    windows,
    totalDurationMs,
    intervalMs: videoFrameIntervalMs,
  });
  const derivedFlaps = fullReplay.flaps;
  const replayScore = fullReplay.score;
  const replay = {
    score: replayScore,
    gameOver: fullReplay.gameOver,
    flaps: derivedFlaps,
  };

  return {
    trace: buildTraceDocument(events, {
      result: replay.score >= targetScore ? "video-solve" : "video-solve-miss",
      score: replay.score,
      claimScore: targetScore,
    }),
    replay,
    planned,
    source,
    desiredFlaps,
    videoSolve: {
      version: 1,
      directionPattern,
      speedPattern,
      unitSectionSpeedPattern,
      sourceDurationMs: source.durationMs,
      unitSections: source.unitSections,
      totalDurationMs,
      sampleIntervalMs,
      videoFrameIntervalMs,
      windows,
      frames,
    },
  };
}

export function prepareSourceGestureClip(
  events,
  {
    preTriggerHoldMs = DEFAULT_PRE_TRIGGER_HOLD_MS,
    postTriggerHoldMs = DEFAULT_POST_TRIGGER_HOLD_MS,
  } = {},
) {
  const source = extractHandSamples(events);
  const durationMs = source.at(-1)?.atMs ?? 0;
  if (durationMs <= 0) {
    throw new Error("Cropped recording duration must be greater than 0.");
  }

  const sourceFlaps = simulateGestureFlaps(source);
  if (sourceFlaps.length !== 1) {
    throw new Error(
      `Cropped recording must produce exactly one 67 gesture flap; observed ${sourceFlaps.length}.`,
    );
  }

  const triggerAtMs = sourceFlaps[0].triggerAtMs;
  const auditAtMs = sourceFlaps[0].auditAtMs ?? triggerAtMs;
  const forward = prepareDirectionalClip(source, {
    direction: "forward",
    durationMs,
    preTriggerHoldMs,
    postTriggerHoldMs,
  });
  const reverse = prepareDirectionalClip(source, {
    direction: "reverse",
    durationMs,
    preTriggerHoldMs,
    postTriggerHoldMs,
  });

  return {
    events: source,
    durationMs,
    triggerAtMs,
    auditAtMs,
    stableRanges: stableRangesForSource(durationMs, triggerAtMs, {
      preTriggerHoldMs,
      postTriggerHoldMs,
    }),
    unitSections: forward.unitSections,
    directions: {
      forward,
      reverse,
    },
  };
}

export function analyzeSourceGestureClip(
  events,
  {
    preActionMs = 900,
    postTriggerMs = 900,
    preTriggerHoldMs = DEFAULT_PRE_TRIGGER_HOLD_MS,
    postTriggerHoldMs = DEFAULT_POST_TRIGGER_HOLD_MS,
  } = {},
) {
  const normalized = normalizeTraceEvents(events || []);
  const handEvents = normalized.filter((event) => event.message?.type === "hands");
  const usableHands = handEvents.filter(
    (event) =>
      Number.isFinite(event.message.leftY) &&
      Number.isFinite(event.message.rightY) &&
      (event.message.handCount ?? 0) >= 2,
  );
  const durationMs = Math.max(
    0,
    normalized.at(-1)?.atMs ?? handEvents.at(-1)?.atMs ?? usableHands.at(-1)?.atMs ?? 0,
  );
  const gaps = sampleGaps(usableHands);
  const fullFlaps = usableHands.length ? simulateGestureFlaps(usableHands) : [];
  const reverseFullFlaps = usableHands.length
    ? simulateGestureFlaps(reverseEventsForDuration(usableHands, durationMs))
    : [];
  const candidates = fullFlaps.map((flap, index) =>
    analyzeCropCandidate({
      index,
      flap,
      source: usableHands,
      durationMs,
      preActionMs,
      postTriggerMs,
      preTriggerHoldMs,
      postTriggerHoldMs,
    }),
  );

  return {
    durationMs,
    samples: handEvents.length,
    usableSamples: usableHands.length,
    coverageRatio: handEvents.length ? usableHands.length / handEvents.length : 0,
    maxSampleGapMs: gaps.max,
    averageSampleGapMs: gaps.average,
    fullFlaps: fullFlaps.map(describeFlap),
    reverseFullFlaps: reverseFullFlaps.map(describeFlap),
    candidates,
    bestCandidate: pickBestCandidate(candidates),
  };
}

export function sourceSampleAt(source, sourceAtMs) {
  const events = source.events || source;
  if (!events.length) {
    return { type: "hands", ...DEFAULT_STABLE };
  }

  if (sourceAtMs <= events[0].atMs) {
    return cloneHandMessage(events[0].message);
  }

  for (let index = 0; index < events.length - 1; index += 1) {
    const left = events[index];
    const right = events[index + 1];
    if (sourceAtMs >= left.atMs && sourceAtMs <= right.atMs) {
      const span = Math.max(1, right.atMs - left.atMs);
      const t = clamp((sourceAtMs - left.atMs) / span, 0, 1);
      return {
        type: "hands",
        leftY: lerp(left.message.leftY, right.message.leftY, t),
        rightY: lerp(left.message.rightY, right.message.rightY, t),
        handCount: Math.max(left.message.handCount ?? 0, right.message.handCount ?? 0, 2),
      };
    }
  }

  return cloneHandMessage(events.at(-1).message);
}

export function sampleVideoSolveAt(videoSolve, source, atMs) {
  const windows = videoSolve?.windows || [];
  const window = windowForTimelineAt(windows, atMs);
  const sourceAtMs = window
    ? sourceAtMsForWindow(window, atMs)
    : stableSourceAt(source, atMs);
  const sample = sourceSampleAt(source, sourceAtMs);
  return {
    atMs: Math.round(atMs),
    sourceAtMs,
    sample,
  };
}

function buildGestureWindows({
  source,
  desiredFlaps,
  directionPattern,
  speedPattern,
  unitSectionSpeedPattern,
  totalDurationMs,
}) {
  return desiredFlaps.map((flapAtMs, index) => {
    const direction = directionForIndex(index, directionPattern);
    const clip = source.directions[direction];
    const speed = speedForJump(index, speedPattern);
    const sectionSpeeds = sectionSpeedsForJump(index, unitSectionSpeedPattern);
    const unit = hasSectionWarp(sectionSpeeds)
      ? buildWarpedJumpUnit(clip, {
          baseSpeed: speed,
          sectionSpeeds,
        })
      : buildLinearJumpUnit(clip, {
          baseSpeed: speed,
          sectionSpeeds,
        });
    const durationMs = unit.durationMs;
    const triggerAtMs = unit.triggerAtMs;
    const startAtMs = Math.max(0, flapAtMs - triggerAtMs);
    const endAtMs = Math.min(totalDurationMs, startAtMs + durationMs);
    return {
      index,
      direction,
      speed,
      sectionSpeeds,
      flapAtMs: timelineMs(flapAtMs),
      startAtMs: timelineMs(startAtMs),
      endAtMs: timelineMs(endAtMs),
      triggerAtMs: timelineMs(startAtMs + triggerAtMs),
      sourceStartAtMs: clip.sourceStartAtMs,
      sourceEndAtMs: clip.sourceEndAtMs,
      clipDurationMs: clip.durationMs,
      unit,
    };
  });
}

function calibrateDesiredFlaps(plannedFlaps, observedFlaps) {
  return plannedFlaps.map((plannedAtMs, index) => {
    const observedAtMs = observedFlaps[index]?.triggerAtMs;
    if (!Number.isFinite(observedAtMs)) {
      return plannedAtMs;
    }
    const correctionMs = clamp(plannedAtMs - observedAtMs, -220, 220);
    return plannedAtMs + correctionMs;
  });
}

function buildTimelineEvents({ source, windows, totalDurationMs, intervalMs }) {
  const events = [];
  for (let atMs = 0; atMs <= totalDurationMs; atMs += intervalMs) {
    const entry = timelineEntryAt(source, windows, atMs);
    const sample = addCameraTexture(entry.sample, atMs, entry.window);
    events.push({
      atMs: timelineMs(atMs),
      message: sample,
      priority: 1,
    });
  }

  for (const window of windows) {
    for (let atMs = window.startAtMs; atMs <= window.endAtMs; atMs += intervalMs) {
      if (windowForTimelineAt(windows, atMs) !== window) {
        continue;
      }
      const entry = timelineEntryAt(source, windows, atMs, window);
      const sample = addCameraTexture(entry.sample, atMs, window);
      events.push({
        atMs: timelineMs(atMs),
        message: sample,
        priority: 2 + unitSamplePriority(window, atMs),
      });
    }
    const triggerEntry = timelineEntryAt(source, windows, window.triggerAtMs, window);
    const triggerSample = addCameraTexture(triggerEntry.sample, window.triggerAtMs, window);
    events.push({
      atMs: timelineMs(window.triggerAtMs),
      message: triggerSample,
      priority: 10,
    });
  }

  const finalEntry = timelineEntryAt(source, windows, totalDurationMs);
  const finalSample = addCameraTexture(finalEntry.sample, totalDurationMs, finalEntry.window);
  events.push({
    atMs: timelineMs(totalDurationMs),
    message: finalSample,
    priority: 1,
  });

  return dedupeEvents(events);
}

function unitSamplePriority(window, atMs) {
  const distance = Math.abs(atMs - window.triggerAtMs);
  const span = Math.max(1, window.unit?.durationMs ?? window.clipDurationMs);
  return 1 - clamp(distance / span, 0, 1);
}

function buildTimelineFrames({ source, windows, totalDurationMs, intervalMs }) {
  const frames = [];
  let sequence = 1;
  for (let atMs = 0; atMs <= totalDurationMs; atMs += intervalMs) {
    const entry = timelineEntryAt(source, windows, atMs);
    const sample = addCameraTexture(entry.sample, atMs, entry.window);
    frames.push({
      sequence,
      atMs: timelineMs(atMs),
      sourceAtMs: timelineMs(entry.sourceAtMs),
      leftY: sample.leftY,
      rightY: sample.rightY,
      handCount: sample.handCount ?? 2,
      windowIndex: entry.window?.index ?? null,
      direction: entry.window?.direction || "stable",
    });
    sequence += 1;
  }
  return frames;
}

function timelineMs(value) {
  return Math.round(value * 1000) / 1000;
}

function timelineEntryAt(source, windows, atMs, forcedWindow = null) {
  const window = forcedWindow || windowForTimelineAt(windows, atMs);
  const sourceAtMs = window
    ? sourceAtMsForWindow(window, atMs)
    : stableSourceAt(source, atMs);
  return {
    sourceAtMs,
    sample: sourceSampleAt(source, sourceAtMs),
    window,
  };
}

function addCameraTexture(sample, atMs, window = null) {
  if (!sample || sample.type !== "hands") {
    return sample;
  }

  const windowPhase = window ? (window.index + 1) * 0.73 : 0;
  const common =
    0.0045 * Math.sin(atMs / 83 + 0.4) +
    0.0028 * Math.sin(atMs / 211 + 1.7) +
    0.0018 * Math.sin(atMs / 37 + windowPhase);
  const differential =
    0.0015 * Math.sin(atMs / 127 + windowPhase) +
    0.0009 * Math.sin(atMs / 53 + 2.3);
  if (window) {
    return {
      ...sample,
      leftY: clamp(sample.leftY + common, 0.12, 0.88),
      rightY: clamp(sample.rightY + common, 0.12, 0.88),
    };
  }

  return {
    ...sample,
    leftY: clamp(sample.leftY + common + differential, 0.12, 0.88),
    rightY: clamp(sample.rightY + common * 0.92 - differential, 0.12, 0.88),
  };
}

function windowForTimelineAt(windows, atMs) {
  let best = null;
  let bestDistance = Infinity;
  for (const window of windows) {
    if (atMs < window.startAtMs || atMs > window.endAtMs) {
      continue;
    }
    const distance = Math.abs(atMs - window.triggerAtMs);
    if (distance < bestDistance) {
      best = window;
      bestDistance = distance;
    }
  }
  return best;
}

function sourceAtMsForWindow(window, atMs) {
  const elapsedMs = clamp(atMs - window.startAtMs, 0, window.unit?.durationMs ?? window.clipDurationMs);
  const clipAtMs = window.unit?.warped
    ? sourceClipAtMsForUnit(window.unit, elapsedMs)
    : clamp(elapsedMs * window.speed, 0, window.clipDurationMs);
  if (window.direction === "reverse") {
    return clamp(window.sourceEndAtMs - clipAtMs, window.sourceStartAtMs, window.sourceEndAtMs);
  }
  return clamp(window.sourceStartAtMs + clipAtMs, window.sourceStartAtMs, window.sourceEndAtMs);
}

function buildLinearJumpUnit(clip, { baseSpeed, sectionSpeeds }) {
  const sections = buildUnitSections(clip).map((section) => ({
    ...section,
    sectionSpeed: sectionSpeeds[section.name] ?? 1,
    effectiveSpeed: baseSpeed,
    displayStartAtMs: section.sourceStartAtMs / baseSpeed,
    displayEndAtMs: section.sourceEndAtMs / baseSpeed,
    displayDurationMs: section.sourceDurationMs / baseSpeed,
  }));
  return {
    warped: false,
    sourceDurationMs: clip.durationMs,
    durationMs: clip.durationMs / baseSpeed,
    triggerAtMs: clip.triggerAtMs / baseSpeed,
    auditAtMs: (clip.auditAtMs ?? clip.triggerAtMs) / baseSpeed,
    baseSpeed,
    sectionSpeeds,
    sections,
  };
}

function buildWarpedJumpUnit(clip, { baseSpeed, sectionSpeeds }) {
  const sections = buildUnitSections(clip).map((section) => {
    const sectionFactor = Number(sectionSpeeds[section.name] ?? 1);
    const effectiveSpeed = Math.max(0.2, baseSpeed * sectionFactor);
    return {
      ...section,
      sectionSpeed: sectionFactor,
      effectiveSpeed,
      displayDurationMs: section.sourceDurationMs / effectiveSpeed,
    };
  });

  let displayAtMs = 0;
  let rawTriggerAtMs = 0;
  let rawAuditAtMs = 0;
  const timedSections = sections.map((section) => {
    const displayStartAtMs = displayAtMs;
    const displayEndAtMs = displayStartAtMs + section.displayDurationMs;
    if (clip.triggerAtMs >= section.sourceStartAtMs && clip.triggerAtMs <= section.sourceEndAtMs) {
      rawTriggerAtMs =
        displayStartAtMs +
        (clip.triggerAtMs - section.sourceStartAtMs) / section.effectiveSpeed;
    }
    if ((clip.auditAtMs ?? clip.triggerAtMs) >= section.sourceStartAtMs && (clip.auditAtMs ?? clip.triggerAtMs) <= section.sourceEndAtMs) {
      rawAuditAtMs =
        displayStartAtMs +
        ((clip.auditAtMs ?? clip.triggerAtMs) - section.sourceStartAtMs) / section.effectiveSpeed;
    }
    displayAtMs = displayEndAtMs;
    return {
      ...section,
      displayStartAtMs,
      displayEndAtMs,
    };
  });

  const unit = {
    warped: true,
    sourceDurationMs: clip.durationMs,
    durationMs: displayAtMs,
    triggerAtMs: rawTriggerAtMs,
    baseSpeed,
    sectionSpeeds,
    sections: timedSections,
  };
  const calibrated = calibrateUnitTrigger(unit, clip, rawTriggerAtMs);
  unit.triggerAtMs = calibrated.triggerAtMs;
  unit.auditAtMs = calibrated.auditAtMs ?? rawAuditAtMs;
  return unit;
}

function calibrateUnitTrigger(unit, clip, fallbackTriggerAtMs) {
  const events = [];
  for (let atMs = 0; atMs <= unit.durationMs; atMs += SAMPLE_INTERVAL_MS) {
    events.push({
      atMs,
      message: sampleDirectionalClipAt(clip, sourceClipAtMsForUnit(unit, atMs)),
    });
  }
  events.push({
    atMs: fallbackTriggerAtMs,
    message: sampleDirectionalClipAt(clip, sourceClipAtMsForUnit(unit, fallbackTriggerAtMs)),
  });
  const flaps = simulateGestureFlaps(events.sort((left, right) => left.atMs - right.atMs));
  if (flaps.length !== 1) {
    return {
      triggerAtMs: fallbackTriggerAtMs,
      auditAtMs: fallbackTriggerAtMs,
      fallback: true,
      observedFlaps: flaps.length,
    };
  }
  return flaps[0];
}

function sampleDirectionalClipAt(clip, clipAtMs) {
  const events = clip.events;
  if (clipAtMs <= events[0].atMs) {
    return cloneHandMessage(events[0].message);
  }
  for (let index = 0; index < events.length - 1; index += 1) {
    const left = events[index];
    const right = events[index + 1];
    if (clipAtMs >= left.atMs && clipAtMs <= right.atMs) {
      const span = Math.max(1, right.atMs - left.atMs);
      const t = clamp((clipAtMs - left.atMs) / span, 0, 1);
      return {
        type: "hands",
        leftY: lerp(left.message.leftY, right.message.leftY, t),
        rightY: lerp(left.message.rightY, right.message.rightY, t),
        handCount: Math.max(left.message.handCount ?? 0, right.message.handCount ?? 0, 2),
      };
    }
  }
  return cloneHandMessage(events.at(-1).message);
}

function buildUnitSections(clip) {
  const durationMs = clip.durationMs;
  const actionStartAtMs = clamp(clip.auditAtMs ?? clip.triggerAtMs - 360, 0, durationMs);
  const leadEnd = actionStartAtMs;
  const gestureEnd = clamp(clip.triggerAtMs + 90, leadEnd, durationMs);
  const recoveryEnd = clamp(clip.triggerAtMs + 260, gestureEnd, durationMs);
  return [
    { name: "lead", sourceStartAtMs: 0, sourceEndAtMs: leadEnd },
    { name: "gesture", sourceStartAtMs: leadEnd, sourceEndAtMs: gestureEnd },
    { name: "recovery", sourceStartAtMs: gestureEnd, sourceEndAtMs: recoveryEnd },
    { name: "settle", sourceStartAtMs: recoveryEnd, sourceEndAtMs: durationMs },
  ]
    .map((section) => ({
      ...section,
      sourceDurationMs: Math.max(0, section.sourceEndAtMs - section.sourceStartAtMs),
    }))
    .filter((section) => section.sourceDurationMs > 0.5);
}

function sourceClipAtMsForUnit(unit, displayAtMs) {
  const section =
    unit.sections.find(
      (entry) =>
        displayAtMs >= entry.displayStartAtMs &&
        displayAtMs <= entry.displayEndAtMs,
    ) || unit.sections.at(-1);
  if (!section) {
    return 0;
  }
  const sectionDisplayAtMs = clamp(
    displayAtMs - section.displayStartAtMs,
    0,
    section.displayDurationMs,
  );
  return clamp(
    section.sourceStartAtMs + sectionDisplayAtMs * section.effectiveSpeed,
    0,
    unit.sourceDurationMs,
  );
}

function stableSourceAt(source, atMs) {
  const ranges = source.stableRanges?.length
    ? source.stableRanges
    : [{ startAtMs: 0, endAtMs: source.durationMs }];
  const totalStableMs = ranges.reduce(
    (sum, range) => sum + Math.max(0, range.endAtMs - range.startAtMs),
    0,
  );
  if (totalStableMs <= 1) {
    return clamp(source.triggerAtMs - DEFAULT_PRE_TRIGGER_HOLD_MS, 0, source.durationMs);
  }

  let offset = positiveModulo(atMs * 0.72, totalStableMs);
  for (const range of ranges) {
    const span = Math.max(0, range.endAtMs - range.startAtMs);
    if (offset <= span) {
      return range.startAtMs + offset;
    }
    offset -= span;
  }

  return ranges.at(-1).endAtMs;
}

function prepareDirectionalClip(
  source,
  { direction, durationMs, preTriggerHoldMs, postTriggerHoldMs },
) {
  const oriented = source
    .map((event) => ({
      atMs: direction === "reverse" ? durationMs - event.atMs : event.atMs,
      sourceAtMs: event.atMs,
      message: cloneHandMessage(event.message),
    }))
    .sort((left, right) => left.atMs - right.atMs);
  const flaps = simulateGestureFlaps(oriented);
  if (flaps.length !== 1) {
    throw new Error(
      `${direction} cropped recording must produce exactly one 67 gesture flap; observed ${flaps.length}.`,
    );
  }

  const triggerAtMs = flaps[0].triggerAtMs;
  const actionAtMs = flaps[0].auditAtMs ?? triggerAtMs;
  const clipStartMs = Math.max(
    0,
    Math.min(triggerAtMs - preTriggerHoldMs, actionAtMs - DEFAULT_PRE_ACTION_CONTEXT_MS),
  );
  const clipEndMs = Math.min(durationMs, triggerAtMs + postTriggerHoldMs);
  const trimmed = oriented
    .filter((event) => event.atMs >= clipStartMs && event.atMs <= clipEndMs)
    .map((event) => ({
      atMs: event.atMs - clipStartMs,
      sourceAtMs: event.sourceAtMs,
      message: cloneHandMessage(event.message),
    }));

  if (!trimmed.length) {
    throw new Error(`${direction} cropped recording has no usable samples after trimming.`);
  }

  const trimmedFlaps = simulateGestureFlaps(trimmed);
  if (trimmedFlaps.length !== 1) {
    throw new Error(
      `${direction} trimmed recording must produce exactly one 67 gesture flap; observed ${trimmedFlaps.length}.`,
    );
  }

  const sourceTimes = trimmed.map((event) => event.sourceAtMs);
  return {
    direction,
    events: trimmed,
    durationMs: trimmed.at(-1)?.atMs ?? clipEndMs - clipStartMs,
    triggerAtMs: trimmedFlaps[0].triggerAtMs,
    auditAtMs: trimmedFlaps[0].auditAtMs,
    unitSections: buildUnitSections({
      durationMs: trimmed.at(-1)?.atMs ?? clipEndMs - clipStartMs,
      triggerAtMs: trimmedFlaps[0].triggerAtMs,
      auditAtMs: trimmedFlaps[0].auditAtMs,
    }),
    sourceStartAtMs: Math.min(...sourceTimes),
    sourceEndAtMs: Math.max(...sourceTimes),
  };
}

function analyzeCropCandidate({
  index,
  flap,
  source,
  durationMs,
  preActionMs,
  postTriggerMs,
  preTriggerHoldMs,
  postTriggerHoldMs,
}) {
  const actionAtMs = flap.auditAtMs ?? flap.triggerAtMs;
  const startMs = clamp(actionAtMs - preActionMs, 0, durationMs);
  const minEndMs = Math.min(durationMs, startMs + 500);
  const endMs = Math.max(minEndMs, Math.min(durationMs, flap.triggerAtMs + postTriggerMs));
  const events = source
    .filter((event) => event.atMs >= startMs && event.atMs <= endMs)
    .map((event) => ({
      atMs: Math.round(event.atMs - startMs),
      message: cloneHandMessage(event.message),
    }));
  const forwardFlaps = simulateGestureFlaps(events);
  const reverseFlaps = simulateGestureFlaps(reverseEventsForDuration(events, endMs - startMs));
  const gaps = sampleGaps(events);
  let prepared = null;
  let error = "";
  try {
    prepared = prepareSourceGestureClip(events, {
      preTriggerHoldMs,
      postTriggerHoldMs,
    });
  } catch (caught) {
    error = caught?.message || String(caught);
  }

  return {
    index,
    startMs,
    endMs,
    durationMs: endMs - startMs,
    actionAtMs,
    triggerAtMs: flap.triggerAtMs,
    triggerLagMs: flap.triggerAtMs - actionAtMs,
    samples: events.length,
    maxSampleGapMs: gaps.max,
    forwardFlapCount: forwardFlaps.length,
    reverseFlapCount: reverseFlaps.length,
    reversible: Boolean(prepared),
    error,
    score: candidateScore({
      events,
      startMs,
      endMs,
      actionAtMs,
      triggerAtMs: flap.triggerAtMs,
      prepared,
      forwardFlaps,
      reverseFlaps,
      maxSampleGapMs: gaps.max,
    }),
  };
}

function candidateScore({
  events,
  startMs,
  endMs,
  actionAtMs,
  triggerAtMs,
  prepared,
  forwardFlaps,
  reverseFlaps,
  maxSampleGapMs,
}) {
  let score = 0;
  if (prepared) {
    score += 1000;
  }
  if (forwardFlaps.length === 1) {
    score += 160;
  }
  if (reverseFlaps.length === 1) {
    score += 160;
  }
  score += Math.min(100, events.length);
  score += Math.min(160, actionAtMs - startMs) * 0.2;
  score += Math.min(160, endMs - triggerAtMs) * 0.2;
  score -= Math.max(0, maxSampleGapMs - 90) * 2;
  return score;
}

function pickBestCandidate(candidates) {
  const viable = candidates.filter((candidate) => candidate.reversible);
  const pool = viable.length ? viable : candidates;
  return [...pool].sort((left, right) => right.score - left.score)[0] || null;
}

function reverseEventsForDuration(events, durationMs) {
  return events
    .map((event) => ({
      atMs: Math.max(0, durationMs - event.atMs),
      message: cloneHandMessage(event.message),
    }))
    .sort((left, right) => left.atMs - right.atMs);
}

function describeFlap(flap) {
  return {
    actionAtMs: Math.round(flap.auditAtMs ?? flap.triggerAtMs),
    triggerAtMs: Math.round(flap.triggerAtMs),
    triggerLagMs: Math.round(flap.triggerAtMs - (flap.auditAtMs ?? flap.triggerAtMs)),
  };
}

function sampleGaps(events) {
  if (events.length < 2) {
    return { max: Infinity, average: Infinity };
  }
  const gaps = events.slice(1).map((event, index) => event.atMs - events[index].atMs);
  return {
    max: Math.max(...gaps),
    average: gaps.reduce((sum, gap) => sum + gap, 0) / gaps.length,
  };
}

function stableRangesForSource(
  durationMs,
  triggerAtMs,
  { preTriggerHoldMs, postTriggerHoldMs },
) {
  const ranges = [];
  const headEnd = Math.max(0, triggerAtMs - preTriggerHoldMs);
  const tailStart = Math.min(durationMs, triggerAtMs + postTriggerHoldMs);
  if (headEnd > 120) {
    ranges.push({ startAtMs: 0, endAtMs: headEnd });
  }
  if (durationMs - tailStart > 120) {
    ranges.push({ startAtMs: tailStart, endAtMs: durationMs });
  }
  if (ranges.length) {
    return ranges;
  }
  return [
    {
      startAtMs: Math.max(0, triggerAtMs - preTriggerHoldMs),
      endAtMs: Math.min(durationMs, triggerAtMs + postTriggerHoldMs),
    },
  ];
}

function extractHandSamples(events) {
  const hands = events
    .filter(
      (event) =>
        event.message?.type === "hands" &&
        Number.isFinite(event.message.leftY) &&
        Number.isFinite(event.message.rightY),
    )
    .map((event) => ({
      atMs: Math.max(0, Number(event.atMs) || 0),
      message: cloneHandMessage(event.message),
    }))
    .sort((left, right) => left.atMs - right.atMs);

  if (!hands.length) {
    throw new Error("Cropped recording has no two-hand samples.");
  }
  return hands;
}

function cloneHandMessage(message) {
  return {
    type: "hands",
    leftY: message.leftY,
    rightY: message.rightY,
    handCount: message.handCount ?? 2,
  };
}

function directionForIndex(index, pattern) {
  if (pattern === "forward") {
    return "forward";
  }
  if (pattern === "reverse") {
    return "reverse";
  }
  return index % 2 === 0 ? "forward" : "reverse";
}

function speedForJump(index, pattern) {
  const speed = Number(pattern[index % pattern.length]);
  if (!Number.isFinite(speed) || speed <= 0) {
    throw new Error(`Invalid video replay speed at index ${index}: ${speed}`);
  }
  return speed;
}

function sectionSpeedsForJump(index, pattern) {
  const profile = Array.isArray(pattern) ? pattern[index % pattern.length] : pattern;
  return normalizeSectionSpeeds(profile || {});
}

function normalizeSectionSpeeds(profile) {
  const normalized = {};
  for (const name of ["lead", "gesture", "recovery", "settle"]) {
    const value = Number(profile[name] ?? 1);
    if (!Number.isFinite(value) || value <= 0) {
      throw new Error(`Invalid ${name} section speed: ${profile[name]}`);
    }
    normalized[name] = value;
  }
  return normalized;
}

function hasSectionWarp(profile) {
  return ["lead", "gesture", "recovery", "settle"].some(
    (name) => Math.abs((profile[name] ?? 1) - 1) > 1e-6,
  );
}

function dedupeEvents(events) {
  const byTime = new Map();
  for (const event of events) {
    const previous = byTime.get(event.atMs);
    if (!previous || (event.priority ?? 0) > (previous.priority ?? 0)) {
      byTime.set(event.atMs, {
        atMs: event.atMs,
        message: event.message,
      });
    }
  }
  return [...byTime.values()].sort((left, right) => left.atMs - right.atMs);
}

function buildTraceDocument(events, meta = {}) {
  return {
    version: 1,
    createdAt: new Date().toISOString(),
    target: meta.target || "ws://127.0.0.1:8787/ws",
    startedAt: null,
    completedAt: meta.completedAt || new Date().toISOString(),
    result: meta.result || "video-solve",
    score: meta.score ?? 0,
    claimScore: meta.claimScore ?? meta.score ?? 0,
    handSamples: events.length,
    flaps: 0,
    events,
  };
}

function positiveModulo(value, divisor) {
  return ((value % divisor) + divisor) % divisor;
}

function lerp(left, right, t) {
  return left + (right - left) * t;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
