import { WIN_SCORE } from "../../../shared/game-core.js";
import { SOLVE_MODES, buildSuiteTrace } from "../../lib/solve-suite.js";
import { createHumanLikeSampleFactory } from "./hand-samples.mjs";
import { attachVideoFrameImages } from "./load-test-video.mjs";
import { SAMPLE_INTERVAL_MS, loadTrace, tileHandLoop } from "./trace-utils.mjs";

const SOLVE_MODE_IDS = new Set(SOLVE_MODES.map((entry) => entry.id));

export function isSolveSuiteMode(mode) {
  return SOLVE_MODE_IDS.has(mode);
}

export function buildSyntheticEvents(durationMs, seed) {
  const sampleFor = createHumanLikeSampleFactory({ seed });
  const events = [];
  for (let atMs = 0; atMs < durationMs; atMs += SAMPLE_INTERVAL_MS) {
    const sample = sampleFor(atMs);
    events.push({
      atMs: Math.round(atMs),
      message: {
        type: "hands",
        leftY: sample.leftY,
        rightY: sample.rightY,
        handCount: sample.handCount,
      },
    });
  }
  return events;
}

export function buildLoadTestPlan(config) {
  const requestedDurationMs = positiveNumberOrNull(config.durationMs);
  const claimScore = config.claimScore ?? WIN_SCORE;

  if (config.mode === "synthetic") {
    const durationMs = requestedDurationMs ?? 8000;
    const events = buildSyntheticEvents(durationMs, config.clientId ?? 0);
    return {
      events,
      durationMs,
      replayDurationMs: events.at(-1)?.atMs ?? 0,
      claimScore,
      suite: null,
    };
  }

  if (!config.tracePath) {
    throw new Error(`${config.mode} requires --trace <path>`);
  }

  const trace = loadTrace(config.tracePath);

  if (config.mode === "trace-loop") {
    const durationMs = requestedDurationMs ?? 8000;
    const hands = trace.events.filter((event) => event.message?.type === "hands");
    const events = tileHandLoop(hands, durationMs);
    return {
      events,
      durationMs,
      replayDurationMs: events.at(-1)?.atMs ?? 0,
      claimScore,
      suite: null,
    };
  }

  if (trace.videoSolve?.frames?.length) {
    return buildPrebuiltSuitePlan({ trace, requestedDurationMs, claimScore });
  }

  const built = buildSuiteTrace(config.mode, {
    trace,
    targetScore: claimScore,
    overshoot: config.overshoot ?? 0,
    strategy: config.strategy || "lookahead",
  });

  const fullDurationMs = Math.ceil(
    Math.max(
      built.events.at(-1)?.atMs ?? 0,
      built.videoSolve?.frames?.at(-1)?.atMs ?? 0,
    ),
  );
  const durationMs = requestedDurationMs ?? fullDurationMs;
  const cappedEvents = built.events.filter((event) => event.atMs <= durationMs);
  const videoEvents = (built.videoSolve?.frames || [])
    .filter((frame) => frame.atMs <= durationMs)
    .map((frame) => ({
      atMs: frame.atMs,
      message: {
        type: "video_frame",
        sequence: frame.sequence,
        sourceAtMs: frame.sourceAtMs,
        leftY: frame.leftY,
        rightY: frame.rightY,
        handCount: frame.handCount ?? 2,
      },
    }));
  const events = [...cappedEvents, ...videoEvents].sort(
    (left, right) => left.atMs - right.atMs,
  );

  return {
    events,
    durationMs,
    replayDurationMs: events.at(-1)?.atMs ?? 0,
    claimScore: built.claimScore ?? claimScore,
    suite: {
      mode: built.mode.id,
      expected: built.mode.verifyExpected,
      localScore: built.score ?? null,
      replayScore: built.replayScore ?? built.score ?? null,
      fullDurationMs,
      generatedEvents: built.events.length,
      generatedVideoFrames: built.videoSolve?.frames?.length ?? 0,
      plannedVideoFrames: videoEvents.length,
      note: built.note || "",
    },
  };
}

function buildPrebuiltSuitePlan({ trace, requestedDurationMs, claimScore }) {
  const resolvedClaimScore = trace.claimScore ?? claimScore;
  const fullDurationMs = Math.ceil(
    Math.max(
      trace.events.at(-1)?.atMs ?? 0,
      trace.videoSolve.frames.at(-1)?.atMs ?? 0,
    ),
  );
  const durationMs = requestedDurationMs ?? fullDurationMs;
  const traceEvents = trace.events.filter((event) => event.atMs <= durationMs);
  const videoEvents = trace.videoSolve.frames
    .filter((frame) => frame.atMs <= durationMs)
    .map((frame) => ({
      atMs: frame.atMs,
      message: {
        type: "video_frame",
        sequence: frame.sequence,
        sourceAtMs: frame.sourceAtMs,
        leftY: frame.leftY,
        rightY: frame.rightY,
        handCount: frame.handCount ?? 2,
        ...(frame.image ? { image: frame.image } : {}),
      },
    }));
  const events = [...traceEvents, ...videoEvents].sort(
    (left, right) => left.atMs - right.atMs,
  );

  return {
    events,
    durationMs,
    replayDurationMs: events.at(-1)?.atMs ?? 0,
    claimScore: resolvedClaimScore,
    suite: {
      mode: trace.result || "prebuilt-video-solve",
      expected: "prebuilt full solve trace",
      localScore: trace.score ?? null,
      replayScore: trace.score ?? null,
      fullDurationMs,
      generatedEvents: trace.events.length,
      generatedVideoFrames: trace.videoSolve.frames.length,
      plannedVideoFrames: videoEvents.length,
      note: "Loaded prebuilt video solve trace with videoSolve frame metadata.",
    },
  };
}

export async function prepareLoadTestPlan(config) {
  const plan = buildLoadTestPlan(config);
  if (!config.videoPath) {
    return plan;
  }

  const prepared = await attachVideoFrameImages(plan.events, {
    videoPath: config.videoPath,
    videoCropStartMs: config.videoCropStartMs,
    videoExtractChunkSize: config.videoExtractChunkSize,
    clientId: config.clientId,
  });

  return {
    ...plan,
    events: prepared.events,
    suite: plan.suite
      ? {
          ...plan.suite,
          videoSource: prepared.videoSource,
        }
      : plan.suite,
  };
}

export function previewLoadTestPlan(config) {
  const plan = buildLoadTestPlan(config);
  return {
    durationMs: plan.durationMs,
    replayDurationMs: plan.replayDurationMs,
    events: plan.events.length,
    videoFrames: plan.events.filter((event) => event.message?.type === "video_frame").length,
    claimScore: plan.claimScore,
    suite: plan.suite,
  };
}

function positiveNumberOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : null;
}
