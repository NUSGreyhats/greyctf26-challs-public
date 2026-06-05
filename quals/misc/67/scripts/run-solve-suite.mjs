#!/usr/bin/env node
/**
 * Build the supported video-backed solver trace locally.
 *
 *   node scripts/run-solve-suite.mjs
 *   node scripts/run-solve-suite.mjs --trace path/to/cropped-trace.json
 */
import { WIN_SCORE } from "../shared/game-core.js";
import {
  SOLVE_MODES,
  buildSuiteTrace,
  listSolveModesByTier,
} from "../shared/solve-suite.js";
import { loadTrace } from "./lib/trace-utils.mjs";

const argv = process.argv.slice(2);
const verify = argv.includes("--verify");
const modeFlag = argv.findIndex((token) => token === "--mode");
const traceFlag = argv.findIndex((token) => token === "--trace");
const selectedMode =
  modeFlag >= 0 ? argv[modeFlag + 1] : process.env.SOLVE_SUITE_MODE || null;
const tracePath =
  traceFlag >= 0
    ? argv[traceFlag + 1]
    : process.env.SOLVE_SUITE_TRACE || null;

const targetUrl = process.env.TARGET_WS_URL || "ws://127.0.0.1:8787/ws";
const claimScore = Number(process.env.SIMULATE_CLAIMED_SCORE || WIN_SCORE);

function printHeader() {
  console.log("Solve suite — video-backed solver\n");
  for (const group of listSolveModesByTier()) {
    console.log(`Tier ${group.tier}: ${group.title}`);
    console.log(`  ${group.description}`);
    for (const mode of group.modes) {
      console.log(`  - ${mode.id}: ${mode.label} (verify: ${mode.verifyExpected})`);
    }
    console.log("");
  }
}

async function verifyOnBackend(events, claimedScore) {
  const socket = new WebSocket(targetUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });

  let sessionId = "";
  const onMessage = (event) => {
    const message = JSON.parse(String(event.data));
    if (message.type === "welcome") {
      sessionId = message.id;
    }
    if (message.type === "verified") {
      socket._verified = message;
    }
  };
  socket.addEventListener("message", onMessage);

  await new Promise((resolve) => {
    const check = () => {
      if (sessionId) {
        resolve();
        return;
      }
      setTimeout(check, 20);
    };
    check();
  });

  socket.send(JSON.stringify({ type: "restart" }));

  const sorted = [...events].sort((left, right) => left.atMs - right.atMs);
  const durationMs = sorted.at(-1)?.atMs || 0;
  await new Promise((resolve) => {
    for (const entry of sorted) {
      setTimeout(() => {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(
            JSON.stringify({
              ...entry.message,
              clientTime: Date.now(),
              traceAtMs: entry.atMs,
            }),
          );
        }
      }, entry.atMs);
    }

    setTimeout(resolve, durationMs + 600);
  });

  socket.send(
    JSON.stringify({
      type: "finish",
      score: claimedScore,
      clientTime: Date.now(),
    }),
  );

  await new Promise((resolve) => {
    const deadline = Date.now() + 6000;
    const wait = () => {
      if (socket._verified || Date.now() > deadline) {
        resolve();
        return;
      }
      setTimeout(wait, 50);
    };
    wait();
  });

  socket.removeEventListener("message", onMessage);
  socket.close();
  return socket._verified || null;
}

async function runMode(modeId, trace) {
  const options = {
    targetScore: claimScore,
    overshoot: Number(process.env.SOLVE_OVERSHOOT ?? "0"),
    trace,
  };

  let built;
  try {
    built = buildSuiteTrace(modeId, options);
  } catch (error) {
    return {
      mode: modeId,
      error: error.message,
    };
  }

  const replayScore = built.replayScore ?? built.score;
  const row = {
    mode: modeId,
    tier: built.mode.tier,
    expected: built.mode.verifyExpected,
    events: built.events?.length ?? 0,
    localScore: built.score,
    replayScore,
    claim: built.claimScore ?? claimScore,
    note: built.note || "",
  };

  if (verify && Array.isArray(built.events)) {
    try {
      const verified = await verifyOnBackend(built.events, row.claim);
      row.verified = verified?.verified ?? false;
      row.valid = verified?.valid ?? false;
      row.serverScore = verified?.score ?? null;
      row.flag = verified?.flag || "";
      row.message = verified?.message || "";
    } catch (error) {
      row.verifyError = error.message;
    }
  }

  return row;
}

async function main() {
  printHeader();

  let trace = null;
  if (tracePath) {
    try {
      trace = loadTrace(tracePath);
      console.log(`Loaded trace: ${tracePath} (${trace.events.length} events)\n`);
    } catch {
      console.log(`No trace at ${tracePath} — solver will skip.\n`);
    }
  } else {
    console.log("No trace provided — pass --trace <cropped-trace.json> to run the solver.\n");
  }

  const modes = selectedMode
    ? SOLVE_MODES.filter((mode) => mode.id === selectedMode)
    : SOLVE_MODES;

  if (!modes.length) {
    throw new Error(`Unknown mode: ${selectedMode}`);
  }

  const results = [];
  for (const mode of modes) {
    if (mode.needsTrace && !trace) {
      results.push({ mode: mode.id, skipped: "no trace" });
      continue;
    }
    process.stdout.write(`Running ${mode.id}… `);
    const row = await runMode(mode.id, trace);
    results.push(row);
    if (row.error) {
      console.log(`ERROR ${row.error}`);
    } else if (row.skipped) {
      console.log("skipped");
    } else {
      const verifyBit =
        row.valid === undefined
          ? ""
          : ` verify valid=${row.valid} server=${row.serverScore}${row.flag ? ` flag=${row.flag}` : ""}`;
      console.log(
        `local=${row.localScore} replay=${row.replayScore} claim=${row.claim}${verifyBit}`,
      );
    }
  }

  console.log("\n--- summary ---");
  for (const row of results) {
    if (row.skipped) {
      console.log(`${row.mode}: skipped (${row.skipped})`);
      continue;
    }
    if (row.error) {
      console.log(`${row.mode}: ERROR ${row.error}`);
      continue;
    }
    console.log(
      `${row.mode} [tier ${row.tier}] expected=${row.expected} local=${row.localScore} replay=${row.replayScore}${row.valid !== undefined ? ` valid=${row.valid}` : ""}`,
    );
    if (row.note) {
      console.log(`  note: ${row.note}`);
    }
    if (row.message) {
      console.log(`  server: ${row.message}`);
    }
    if (row.flag) {
      console.log(`  flag: ${row.flag}`);
    }
    if (row.verifyError) {
      console.log(`  verify error: ${row.verifyError}`);
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
