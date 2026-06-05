#!/usr/bin/env node
/**
 * Transform trace JSON: scale timing, tile loops, strip flaps.
 *
 * Usage:
 *   node scripts/transform-trace.mjs input.json -o out.json --scale 0.95
 *   node scripts/transform-trace.mjs input.json --tile loop.json --duration 120000 -o out.json
 *   node scripts/transform-trace.mjs input.json --hands-only -o out.json
 */
import {
  buildTraceDocument,
  extractHandLoop,
  filterHandsOnly,
  loadTrace,
  mergeTraceEvents,
  normalizeTraceEvents,
  parseArgs,
  scaleTraceEvents,
  summarizeTrace,
  tileHandLoop,
  writeTrace,
} from "./lib/trace-utils.mjs";

function main() {
  const { positional, flags } = parseArgs(process.argv.slice(2));
  const inputPath = positional[0];
  if (!inputPath) {
    throw new Error(
      "Usage: node scripts/transform-trace.mjs <input.json> [-o out.json] [--scale N] [--tile loop.json --duration MS] [--hands-only]",
    );
  }

  const input = loadTrace(inputPath);
  let events = normalizeTraceEvents(input);

  if (flags.tile) {
    const loopTrace = loadTrace(flags.tile);
    const loopEvents = extractHandLoop(normalizeTraceEvents(loopTrace));
    const durationMs =
      flags.duration ?? events.at(-1)?.atMs ?? loopEvents.at(-1)?.atMs ?? 0;
    const tiled = tileHandLoop(loopEvents, durationMs);
    const overlay = flags.handsOnly ? filterHandsOnly(events) : events;
    const overlayHands = filterHandsOnly(overlay);
    events = mergeTraceEvents(tiled, overlayHands.length ? overlay : []);
  }

  if (flags.handsOnly) {
    events = filterHandsOnly(events);
  }

  if (flags.scale) {
    events = scaleTraceEvents(events, flags.scale);
  }

  const trace = buildTraceDocument(events, {
    result: input.result || "transformed",
    score: input.score ?? 0,
    target: input.target,
  });

  const output = flags.output || inputPath.replace(/\.json$/i, ".transformed.json");
  writeTrace(output, trace);
  const summary = summarizeTrace(trace);
  console.log(
    `Wrote ${output}: ${summary.events} events (${summary.handEvents} hands, ${summary.flaps} flaps), ` +
      `${(summary.durationMs / 1000).toFixed(2)}s`,
  );
}

main();
