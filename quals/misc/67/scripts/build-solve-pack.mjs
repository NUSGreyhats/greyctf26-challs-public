#!/usr/bin/env node
/**
 * Build a legacy gesture trace for local regression only.
 *
 * Do not commit or serve the output in production. Production verification derives
 * flaps from continuous hand samples and rejects explicit gesture flaps.
 */
import { WIN_SCORE } from "../shared/game-core.js";
import { buildSolveTrace } from "../shared/flap-solver.js";
import { buildGestureLoopEvents } from "../shared/gesture-loop.js";
import { buildGestureSolvePack } from "./lib/gesture-solve.mjs";
import {
  buildTraceDocument,
  loadTrace,
  parseArgs,
  scaleTraceEvents,
  summarizeTrace,
  writeTrace,
} from "./lib/trace-utils.mjs";

function main() {
  const { flags } = parseArgs(process.argv.slice(2));
  const output = flags.output || "solve-pack.json";
  const targetScore = Number(process.env.SOLVE_TARGET_SCORE || WIN_SCORE);
  const overshoot = Number(process.env.SOLVE_OVERSHOOT ?? "0");
  const motion = flags.motion || process.env.SOLVE_MOTION || "camouflage";
  const strategy = flags.strategy || process.env.SOLVE_STRATEGY || "lookahead";
  const maxSimMs = Number(process.env.SOLVE_MAX_MS || "130000");

  if (flags.manual) {
    buildManualPack({ output, targetScore, overshoot, motion, maxSimMs, flags });
    return;
  }

  const loopTrace = flags.tile
    ? loadTrace(flags.tile)
    : buildTraceDocument(buildGestureLoopEvents(), { result: "synthetic-gesture-loop" });
  const built = buildGestureSolvePack({
    loopTrace,
    targetScore,
    overshoot,
    maxSimMs,
    strategy,
    reverse: false,
  });

  let trace = built.trace;
  if (flags.scale && flags.scale !== 1) {
    trace = {
      ...trace,
      events: scaleTraceEvents(trace.events, flags.scale),
    };
  }

  writeTrace(output, trace);
  const summary = summarizeTrace(trace);
  console.log(
    `Built ${output}: score=${built.replay.score}/${targetScore} ` +
      `derivedGestureFlaps=${built.replay.flaps.length} events=${summary.events} ` +
      `duration=${(summary.durationMs / 1000).toFixed(2)}s reversed=${built.clip.reversed}`,
  );
  console.log(
    `Gesture clip: trigger=${built.clip.triggerAtMs.toFixed(1)}ms ` +
      `duration=${built.clip.durationMs.toFixed(1)}ms speeds=${built.speedPattern.join(",")}`,
  );

  if (built.replay.score < targetScore) {
    console.error("Gesture replay score below claim target; record a cleaner clip or increase SOLVE_OVERSHOOT.");
    process.exitCode = 1;
  }
}

function buildManualPack({ output, targetScore, overshoot, motion, maxSimMs, flags }) {
  let loopDurationMs = 240;
  if (flags.tile) {
    const loopTrace = loadTrace(flags.tile);
    loopDurationMs = Math.max(240, loopTrace.events.at(-1)?.atMs || 240);
  }

  const built = buildSolveTrace({
    targetScore,
    overshoot,
    maxSimMs,
    motion,
    loopDurationMs,
  });

  let finalEvents = built.events;
  if (flags.scale && flags.scale !== 1) {
    finalEvents = scaleTraceEvents(finalEvents, flags.scale);
  }

  const trace = buildTraceDocument(finalEvents, {
    result: built.won ? "won" : "game-over",
    score: built.score,
    claimScore: built.claimScore,
  });

  writeTrace(output, trace);
  const summary = summarizeTrace(trace);
  console.log(
    `Built ${output}: score=${built.score}/${targetScore} replay=${built.replayScore} ` +
      `flaps=${summary.flaps} duration=${(summary.durationMs / 1000).toFixed(2)}s motion=${motion}`,
  );
  console.log(`Flap schedule: ${built.flapSchedule.length} jumps (pipe-targeted).`);

  if (built.score < targetScore + overshoot) {
    console.error("Pack did not reach build target in local simulation.");
    process.exitCode = 1;
  }

  if (built.replayScore < targetScore) {
    console.error("Manual replay-style score below claim target; increase SOLVE_OVERSHOOT.");
    process.exitCode = 1;
  }
}

main();
