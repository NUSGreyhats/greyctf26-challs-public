#!/usr/bin/env node
/**
 * Parallel solve load test — ramp concurrent WebSocket clients until
 * schedule drift or hand motion distance degrades noticeably.
 *
 *   node solve/scripts/load-test-solver.mjs --clients 8
 *   node solve/scripts/load-test-solver.mjs --ramp --max-clients 64
 *   node solve/scripts/load-test-solver.mjs --trace solve-trace.json
 */
import { fork } from "node:child_process";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { WIN_SCORE } from "../../shared/game-core.js";
import { SOLVE_MODES } from "../lib/solve-suite.js";
import { mergeTypeMetrics } from "./lib/load-test-metrics.mjs";
import { LOAD_TEST_FINISH_VERIFY_TIMEOUT_MS } from "./lib/load-test-client.mjs";
import { isSolveSuiteMode, previewLoadTestPlan } from "./lib/load-test-plan.mjs";
import { buildLoadTestReport, writeLoadTestReport } from "./lib/load-test-report.mjs";
import { resolveLoadTestTarget } from "./lib/target-url.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const workerPath = resolve(__dirname, "load-test-worker.mjs");

import {
  flagValue,
  firstFlagValue,
  hasFlag,
  optionalFlagValue,
} from "./lib/cli-args.mjs";

const argv = process.argv.slice(2);

const urlFlag = flagValue(argv, "--url");
const serverFlag = flagValue(argv, "--server");
const proxyFlag = optionalFlagValue(argv, "--proxy");
const proxyTargetFlag = firstFlagValue(argv, ["--proxy-target", "--proxy-client"]);

let target;
try {
  target = resolveLoadTestTarget({
    url: urlFlag,
    server: serverFlag,
    proxy: proxyFlag,
    proxyTarget: proxyTargetFlag,
    proxyClient: proxyTargetFlag,
    envUrl: process.env.TARGET_WS_URL,
  });
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
  process.exit(1);
}

const targetUrl = target.targetUrl;
const tracePath = process.env.SOLVE_SUITE_TRACE || flagValue(argv, "--trace");
const mode =
  process.env.LOAD_TEST_MODE ||
  flagValue(argv, "--mode", tracePath ? SOLVE_MODES[0]?.id : "synthetic");
const durationOverride = process.env.LOAD_TEST_DURATION_MS || flagValue(argv, "--duration-ms");
const claimScore = Number(process.env.SIMULATE_CLAIMED_SCORE || WIN_SCORE);
const fullSolveMode = isSolveSuiteMode(mode);
const durationMs = durationOverride == null ? null : Number(durationOverride);
const submitFinish = hasFlag(argv, "--finish") || (fullSolveMode && !hasFlag(argv, "--no-finish"));
const ramp = hasFlag(argv, "--ramp");
const clients = Number(flagValue(argv, "--clients", ramp ? "1" : "4"));
const maxClients = Number(flagValue(argv, "--max-clients", "128"));
const step = Number(flagValue(argv, "--step", "0"));
const driftThresholdMs = Number(flagValue(argv, "--drift-threshold-ms", "500"));
const motionThreshold = Number(flagValue(argv, "--motion-threshold", "0.0012"));
const settleMs = Number(flagValue(argv, "--settle-ms", "500"));
const reportFlag = flagValue(argv, "--report");
const noReport = hasFlag(argv, "--no-report");
const videoPath = flagValue(argv, "--video") || flagValue(argv, "--video-source");
const videoCropStartMs = Number(
  flagValue(argv, "--video-crop-start-ms", flagValue(argv, "--video-start-ms", "0")),
);
let runPlan = null;

function printUsage() {
  console.log(`Solve load test — parallel forked workers

Usage:
  node solve/scripts/load-test-solver.mjs --clients <n> [options]
  node solve/scripts/load-test-solver.mjs --ramp [options]

Options:
  --url <ws://host/ws>         Full WebSocket URL (same as TARGET_WS_URL)
  --server <host[:port]|url>   Custom game backend (e.g. 127.0.0.1:8787, wss://game.example.com)
  --proxy [host[:port]]        Connect via solve lab proxy (default 127.0.0.1:4180; requires pnpm start:solve)
  --proxy-target <ws-url>      Remote game server the proxy forwards to
  --proxy-client <ws-url>      Alias for --proxy-target
  --trace <path>               Cropped trace JSON (required for solve-suite modes)
  --video <path>               Source video for real video_frame/snapshot images
  --video-crop-start-ms <n>    Offset when sourceAtMs is relative to a crop (default 0)
  --mode <id>                  synthetic | trace-loop | recorded-video-pingpong
  --duration-ms <n>            Replay length per client (default 8000; solve modes use full duration)
  --finish                     Submit finish/verify after replay
  --no-finish                  Skip finish for solve-suite modes
  --ramp                       Double client count until thresholds trip
  --max-clients <n>            Ramp ceiling (default 128)
  --step <n>                   Ramp increment when set; otherwise double each round
  --drift-threshold-ms <n>     Stop ramp when aggregate p95 drift exceeds this (default 50)
  --motion-threshold <n>       Stop when aggregate motion p50 drops below (default 0.0015)
  --settle-ms <n>              Pause between ramp rounds (default 500)
  --report <dir>               Write JSON + HTML charts (default solve/reports/<timestamp>)
  --no-report                  Skip report generation

Modes:
${SOLVE_MODES.map((entry) => `  - ${entry.id}: needs trace, full solve plan`).join("\n")}
  - trace-loop: tile hand samples from --trace
  - synthetic: human-like hands without trace (default when no --trace)

Passing --trace without --mode runs the supported full solve mode.

  Env: TARGET_WS_URL, SOLVE_SUITE_TRACE, LOAD_TEST_DURATION_MS, LOAD_TEST_FINISH_VERIFY_TIMEOUT_MS (optional)

Server examples:
  --url ws://127.0.0.1:8787/ws
  --url wss://your-host.example/ws
  --server 192.168.1.10:8787
  --server https://staging.example.com
  TARGET_WS_URL=wss://prod.example/ws pnpm solve:load-test -- --clients 8
  --proxy --proxy-target ws://127.0.0.1:8787/ws   # via solve lab :4180
`);
}

if (hasFlag(argv, "--help") || hasFlag(argv, "-h")) {
  printUsage();
  process.exit(0);
}

function spawnWorker(clientId, config) {
  return new Promise((resolve) => {
    const child = fork(workerPath, [], {
      env: {
        ...process.env,
        LOAD_TEST_CLIENT_ID: String(clientId),
        LOAD_TEST_CONFIG: JSON.stringify(config),
      },
      stdio: ["ignore", "ignore", "ignore", "ipc"],
    });

    let settled = false;
    let timeout = null;
    const finish = (payload) => {
      if (settled) {
        return;
      }
      settled = true;
      if (timeout) {
        clearTimeout(timeout);
      }
      child.removeAllListeners();
      if (!child.killed) {
        child.kill("SIGTERM");
      }
      resolve(payload);
    };

    child.on("message", (message) => {
      if (message?.type === "result") {
        finish(message.result);
      }
      if (message?.type === "error") {
        finish(message.error);
      }
    });

    child.on("error", (error) => {
      finish({ clientId, error: error.message });
    });

    child.on("exit", (code) => {
      if (!settled && code !== 0) {
        finish({ clientId, error: `worker exited with code ${code}` });
      }
    });

    const timeoutBaseMs =
      Number.isFinite(config.durationMs) && config.durationMs > 0
        ? config.durationMs
        : 8000;
    const workerGraceMs = config.submitFinish
      ? LOAD_TEST_FINISH_VERIFY_TIMEOUT_MS === null
        ? null
        : LOAD_TEST_FINISH_VERIFY_TIMEOUT_MS + 10000
      : 20000;
    if (workerGraceMs !== null) {
      timeout = setTimeout(() => {
        finish({ clientId, error: "worker timeout" });
      }, timeoutBaseMs + workerGraceMs);
    }
  });
}

function aggregateResults(results) {
  const ok = results.filter((row) => !row.error);
  const driftP95 = ok.map((row) => row.driftMs?.p95 ?? 0);
  const driftMax = ok.map((row) => row.driftMs?.max ?? 0);
  const motionP50 = ok
    .map((row) => row.motionDistance?.p50)
    .filter((value) => Number.isFinite(value));
  const connectMs = ok.map((row) => row.connectMs ?? 0);
  const welcomeMs = ok.map((row) => row.welcomeMs ?? 0);
  const finished = ok.filter((row) => row.finish).length;
  const finishValid = ok.filter((row) => row.finish?.valid).length;
  const videoFramesSent = ok.reduce((total, row) => total + (row.videoFramesSent ?? 0), 0);
  const snapshotsSent = ok.reduce((total, row) => total + (row.snapshotsSent ?? 0), 0);

  const sorted = (values) => [...values].sort((left, right) => left - right);
  const maxOf = (values) => (values.length ? Math.max(...values) : 0);
  const minOf = (values) => (values.length ? Math.min(...values) : 0);
  const medianOf = (values) => {
    if (!values.length) {
      return 0;
    }
    const sortedValues = sorted(values);
    return sortedValues[Math.floor(sortedValues.length / 2)];
  };

  const aggregate = {
    total: results.length,
    ok: ok.length,
    failed: results.length - ok.length,
    driftP95Max: maxOf(driftP95),
    driftP95Median: medianOf(driftP95),
    driftMaxWorst: maxOf(driftMax),
    motionP50Min: minOf(motionP50),
    motionP50Median: medianOf(motionP50),
    connectMsMax: maxOf(connectMs),
    welcomeMsMax: maxOf(welcomeMs),
    finished,
    finishValid,
    videoFramesSent,
    snapshotsSent,
    errors: results.filter((row) => row.error).map((row) => row.error),
  };

  aggregate.byMessageType = mergeTypeMetrics(results);
  return aggregate;
}

function isNoticeable(aggregate) {
  const driftHit = aggregate.driftP95Max >= driftThresholdMs;
  const motionHit =
    aggregate.motionP50Min > 0 && aggregate.motionP50Min < motionThreshold;
  const failureHit = aggregate.failed > 0 || aggregate.ok < aggregate.total;
  return {
    driftHit,
    motionHit,
    failureHit,
    noticeable: driftHit || motionHit || failureHit,
  };
}

function formatAggregate(clientsCount, aggregate, flags) {
  const pingP95 = aggregate.byMessageType?.ping?.pingRttMs?.p95;
  const handsDriftP95 = aggregate.byMessageType?.hands?.driftMs?.p95;
  const videoDriftP95 = aggregate.byMessageType?.video_frame?.driftMs?.p95;
  const finishBit =
    aggregate.finished > 0
      ? [`finish=${aggregate.finishValid}/${aggregate.finished}`]
      : [];
  const bits = [
    `clients=${clientsCount}`,
    `ok=${aggregate.ok}/${aggregate.total}`,
    ...finishBit,
    `pingP95=${pingP95 != null ? `${pingP95.toFixed(1)}ms` : "—"}`,
    `handsDriftP95=${handsDriftP95 != null ? `${handsDriftP95.toFixed(1)}ms` : "—"}`,
    `videoDriftP95=${videoDriftP95 != null ? `${videoDriftP95.toFixed(1)}ms` : "—"}`,
    `driftP95 max=${aggregate.driftP95Max.toFixed(1)}ms med=${aggregate.driftP95Median.toFixed(1)}ms`,
    `motionP50 min=${aggregate.motionP50Min.toFixed(5)}`,
    `video=${aggregate.videoFramesSent}`,
    `snapshots=${aggregate.snapshotsSent}`,
    `welcome max=${aggregate.welcomeMsMax.toFixed(1)}ms`,
  ];

  if (flags.noticeable) {
    const reasons = [];
    if (flags.driftHit) {
      reasons.push(`drift p95 >= ${driftThresholdMs}ms`);
    }
    if (flags.motionHit) {
      reasons.push(`motion p50 < ${motionThreshold}`);
    }
    if (flags.failureHit) {
      reasons.push("worker failures");
    }
    bits.push(`NOTICEABLE (${reasons.join(", ")})`);
  }

  if (aggregate.errors.length) {
    bits.push(`errors=${aggregate.errors.slice(0, 3).join("; ")}`);
  }

  return bits.join(" | ");
}

async function runRound(clientCount) {
  const configs = Array.from({ length: clientCount }, (_, index) => ({
    clientId: index,
    mode,
    targetUrl,
    tracePath: tracePath || null,
    durationMs: runPlan.durationMs,
    claimScore,
    submitFinish,
    overshoot: Number(process.env.SOLVE_OVERSHOOT ?? "0"),
    videoPath: videoPath || null,
    videoCropStartMs,
  }));

  const results = await Promise.all(
    configs.map((config) => spawnWorker(config.clientId, config)),
  );

  return { clientCount, results, aggregate: aggregateResults(results) };
}

async function main() {
  runPlan = previewLoadTestPlan({
    clientId: 0,
    mode,
    tracePath: tracePath || null,
    durationMs,
    claimScore,
    overshoot: Number(process.env.SOLVE_OVERSHOOT ?? "0"),
  });

  console.log("Solve load test\n");
  console.log(`Target: ${targetUrl}${target.kind === "proxy" ? " (solve proxy)" : ""}`);
  if (target.backendUrl) {
    console.log(`Proxy backend: ${target.backendUrl}`);
  }
  console.log(`Mode: ${mode}`);
  console.log(`Duration: ${runPlan.durationMs}ms per client`);
  console.log(`Events: ${runPlan.events} planned per client`);
  if (runPlan.videoFrames) {
    console.log(`Video frames: ${runPlan.videoFrames} planned per client`);
  }
  if (runPlan.suite) {
    console.log(
      `Full solve: replay=${runPlan.suite.replayScore}, claim=${runPlan.claimScore}, generated=${runPlan.suite.generatedEvents} events`,
    );
    if (runPlan.suite.generatedVideoFrames) {
      console.log(
        `Video evidence: ${runPlan.suite.plannedVideoFrames}/${runPlan.suite.generatedVideoFrames} frames scheduled per client`,
      );
    }
  }
  console.log(`Finish: ${submitFinish ? "enabled" : "disabled"}`);
  console.log(
    `Thresholds: drift p95 >= ${driftThresholdMs}ms, motion p50 < ${motionThreshold}`,
  );
  if (tracePath) {
    console.log(`Trace: ${tracePath}`);
  }
  if (videoPath) {
    console.log(`Video source: ${videoPath}`);
    if (videoCropStartMs > 0) {
      console.log(`Video crop start: ${videoCropStartMs}ms`);
    }
  }
  console.log("");

  const rounds = [];
  let lastSustainable = 0;

  if (ramp) {
    let count = Math.max(1, clients);
    while (count <= maxClients) {
      process.stdout.write(`Round ${rounds.length + 1}: spawning ${count} workers… `);
      const round = await runRound(count);
      const flags = isNoticeable(round.aggregate);
      rounds.push({ ...round, flags });
      console.log(formatAggregate(count, round.aggregate, flags));

      if (!flags.noticeable) {
        lastSustainable = count;
      } else {
        console.log(`\nStopped ramp: noticeable degradation at ${count} clients.`);
        break;
      }

      if (step > 0) {
        count += step;
      } else {
        count *= 2;
      }

      if (settleMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, settleMs));
      }
    }
  } else {
    process.stdout.write(`Spawning ${clients} workers… `);
    const round = await runRound(clients);
    const flags = isNoticeable(round.aggregate);
    rounds.push({ ...round, flags });
    console.log(formatAggregate(clients, round.aggregate, flags));
    if (!flags.noticeable) {
      lastSustainable = clients;
    }
  }

  console.log("\n--- summary ---");
  for (const round of rounds) {
    console.log(formatAggregate(round.clientCount, round.aggregate, round.flags));
  }

  if (ramp) {
    console.log(
      `\nLast sustainable client count (below thresholds): ${lastSustainable || "none"}`,
    );
    const firstBad = rounds.find((round) => round.flags.noticeable);
    if (firstBad) {
      console.log(`First noticeable load: ${firstBad.clientCount} clients`);
    }
  } else if (rounds[0]?.flags.noticeable) {
    console.log(`\nLoad at ${clients} clients exceeds drift/motion thresholds.`);
  } else {
    console.log(`\n${clients} clients stayed within thresholds for this run.`);
  }

  if (!noReport) {
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    const reportDir = resolve(
      reportFlag || resolve(__dirname, "../reports", stamp),
    );
    mkdirSync(dirname(reportDir), { recursive: true });

    const report = buildLoadTestReport({
      meta: {
        targetUrl,
        targetKind: target.kind,
        proxyBackend: target.backendUrl,
        mode,
        durationMs,
        plannedDurationMs: runPlan.durationMs,
        plannedEvents: runPlan.events,
        plannedVideoFrames: runPlan.videoFrames,
        tracePath: tracePath || null,
        videoPath: videoPath || null,
        videoCropStartMs,
        submitFinish,
        ramp,
        fullSolveMode,
        suite: runPlan.suite,
      },
      thresholds: {
        driftThresholdMs,
        motionThreshold,
      },
      rounds,
      lastSustainable,
    });

    const paths = writeLoadTestReport(report, reportDir);
    const latestDir = resolve(__dirname, "../reports/latest");
    mkdirSync(latestDir, { recursive: true });
    writeLoadTestReport(report, latestDir);

    console.log(`\nReport: ${paths.htmlPath}`);
    console.log(`JSON:   ${paths.jsonPath}`);
    console.log(`Latest: ${resolve(latestDir, "load-test-report.html")}`);
  }
}

main().catch((error) => {
  console.error(error?.message || error);
  process.exitCode = 1;
});
