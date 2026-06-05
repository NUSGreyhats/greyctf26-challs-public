/**
 * Canonical solve mode registry.
 *
 * The old empty-claim, god-mode, mechanical, and explicit-flap paths were useful
 * regression probes while hardening verification. The supported solver is now the
 * video-backed forward/back replay built from one cropped stable -> 67 -> stable clip.
 */
import { WIN_SCORE } from "./game-core.js";
import { normalizeTraceEvents } from "./frontend-client.js";
import { buildVideoSolvePlan } from "./video-solve.js";

export const SOLVE_TIERS = [
  {
    tier: 1,
    title: "Video-backed solver",
    description:
      "Build a hand-only replay and synchronized video frames from one cropped stable -> 67 -> stable recording.",
  },
];

export const SOLVE_MODES = [
  {
    id: "recorded-video-pingpong",
    tier: 1,
    label: "Recorded video solver - forward/back",
    verifyExpected: "requires live-compatible source video",
    needsTrace: true,
    needsVideo: true,
  },
];

export function getSolveMode(modeId) {
  const mode = SOLVE_MODES.find((entry) => entry.id === modeId);
  if (!mode) {
    throw new Error(`Unknown solve mode: ${modeId}`);
  }
  return mode;
}

export function listSolveModesByTier() {
  return SOLVE_TIERS.map((tier) => ({
    ...tier,
    modes: SOLVE_MODES.filter((mode) => mode.tier === tier.tier),
  }));
}

export function localSimOptionsForMode() {
  return null;
}

export function buildSuiteTrace(modeId, options = {}) {
  const mode = getSolveMode(modeId);
  if (!options.trace) {
    throw new Error(`${mode.id} requires a loaded cropped recording trace.`);
  }

  const built = buildVideoSolvePlan({
    clipTrace: options.trace,
    targetScore: options.targetScore ?? WIN_SCORE,
    overshoot: options.overshoot ?? 1,
    strategy: options.strategy || "lookahead",
    directionPattern: "pingpong",
  });

  return {
    mode,
    ...built.trace,
    events: normalizeTraceEvents(built.trace.events || []),
    replayScore: built.replay.score,
    source: built.source,
    videoSolve: built.videoSolve,
    clip: {
      triggerAtMs: built.source.triggerAtMs,
      durationMs: built.source.durationMs,
      directions: Object.keys(built.source.directions),
    },
    note:
      `Generated from one cropped video trace, alternating forward/backward ` +
      `(${built.videoSolve.windows.length} gestures, ${built.videoSolve.frames.length} video frames). ` +
      `The solve UI must have the matching source video loaded to submit video evidence.`,
  };
}

export function summarizeSuiteResult(mode, built, verified = null) {
  return {
    mode: mode.id,
    tier: mode.tier,
    verifyExpected: mode.verifyExpected,
    localScore: built.score,
    replayScore: built.replayScore ?? null,
    claimScore: built.claimScore,
    events: built.events?.length ?? 0,
    verified: verified?.verified ?? null,
    valid: verified?.valid ?? null,
    serverScore: verified?.score ?? null,
    message: verified?.message || built.note || "",
  };
}
