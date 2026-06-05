#!/usr/bin/env node
/**
 * Write a stable -> 67 -> stable gesture loop for solve-pack generation.
 *
 * Usage:
 *   node solve/scripts/record-loop.mjs [-o loop.json]
 */
import { buildGestureLoopEvents } from "../lib/gesture-loop.js";
import { buildTraceDocument, parseArgs, summarizeTrace, writeTrace } from "./lib/trace-utils.mjs";

function main() {
  const { flags } = parseArgs(process.argv.slice(2));
  const output = flags.output || "loop.json";
  const events = buildGestureLoopEvents(flags.loopMs);

  const trace = buildTraceDocument(events, { result: "loop", score: 0 });
  writeTrace(output, trace);
  const summary = summarizeTrace(trace);
  console.log(
    `Wrote stable -> 67 -> stable loop ${output}: ` +
      `${summary.handEvents} hand samples, ${(summary.durationMs / 1000).toFixed(2)}s`,
  );
}

main();
