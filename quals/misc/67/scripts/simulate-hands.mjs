#!/usr/bin/env node
/**
 * CLI harness for the backend WebSocket API.
 *
 * Streams `hands` samples (and optional trace replay), then submits `finish` with
 * SIMULATE_CLAIMED_SCORE when above VERIFY_SCORE_THRESHOLD so the server replays
 * the session log.
 */
import { WIN_SCORE } from "../shared/game-core.js";
import { finishMessage, restartMessage, toSocketPayload } from "../shared/frontend-client.js";
import { createHumanLikeSampleFactory } from "./lib/hand-samples.mjs";
import {
  SAMPLE_INTERVAL_MS,
  clamp,
  loadTrace,
  parseArgs,
  scaleTraceEvents,
  summarizeTrace,
} from "../solve/scripts/lib/trace-utils.mjs";

const argv = process.argv.slice(2);
const mode = argv[0] || "sussy";
const traceScale = Number(process.env.TRACE_SCALE || "1");
const sampleIntervalMs = SAMPLE_INTERVAL_MS;
const runMs = Number(process.env.SIMULATE_MS || (mode === "sussy" ? 12000 : 18000));

const targetUrl =
  mode === "trace"
    ? argv[2] || process.env.TARGET_WS_URL || "ws://127.0.0.1:8787/ws"
    : argv[1] || process.env.TARGET_WS_URL || "ws://127.0.0.1:8787/ws";

function createSampleGenerator(modeName) {
  if (modeName === "human" || modeName === "loop") {
    return createHumanLikeSampleFactory({
      seed: modeName === "loop" ? 42 : 7,
      periodMs: modeName === "loop" ? 380 : 340,
      amplitude: 0.2,
    });
  }

  const periodMs = 180;
  const amplitude = 0.19;
  const centerHeight = 0.57;

  return (elapsedMs) => {
    const phase = ((elapsedMs % periodMs) / periodMs) * 2;
    const triangle = phase < 1 ? phase * 2 - 1 : 3 - phase * 2;
    const offset = amplitude * triangle;
    const leftHeight = clamp(centerHeight + offset, 0.08, 0.92);
    const rightHeight = clamp(centerHeight - offset, 0.08, 0.92);
    return {
      leftY: 1 - leftHeight,
      rightY: 1 - rightHeight,
      handCount: 2,
    };
  };
}

function createSocketMetrics() {
  let acceptedFlaps = 0;
  let lastAntiCheat = null;
  let lastVerified = null;

  return {
    handleMessage(message) {
      if (message.type === "state") {
        const state = message.state;
        if (state.acceptedFlapCount > acceptedFlaps) {
          acceptedFlaps = state.acceptedFlapCount;
          console.log(`Server accepted flap #${acceptedFlaps}`);
        }

        const antiCheat = state.antiCheat;
        if (
          antiCheat &&
          (antiCheat.level !== "none" || antiCheat.message) &&
          JSON.stringify(antiCheat) !== JSON.stringify(lastAntiCheat)
        ) {
          lastAntiCheat = antiCheat;
          console.log(
            `ANTI-CHEAT level=${antiCheat.level} score=${antiCheat.score}/${antiCheat.blockScore} message=${antiCheat.message}`,
          );
        }

        if (state.gameOver && antiCheat?.level === "blocked") {
          console.log(`Run blocked: ${antiCheat.message}`);
        }
        return;
      }

      if (message.type === "verified") {
        lastVerified = message;
        console.log(
          `VERIFIED valid=${message.valid} verified=${message.verified} score=${message.score} claimed=${message.claimedScore} won=${message.won} message=${message.message || ""}${message.hint ? ` hint=${message.hint}` : ""}`,
        );
        const antiCheat = message.antiCheat;
        if (antiCheat?.message) {
          console.log(
            `ANTI-CHEAT level=${antiCheat.level} score=${antiCheat.score}/${antiCheat.blockScore} message=${antiCheat.message}`,
          );
        }
      }
    },
    getAcceptedFlaps: () => acceptedFlaps,
    getLastVerified: () => lastVerified,
  };
}

async function submitFinish(socket, claimedScore) {
  const threshold = Number(process.env.VERIFY_SCORE_THRESHOLD || "50");
  if (claimedScore <= threshold) {
    return null;
  }

  return await new Promise((resolve) => {
    const onMessage = (event) => {
      const message = JSON.parse(String(event.data));
      if (message.type === "verified") {
        socket.removeEventListener("message", onMessage);
        resolve(message);
      }
    };
    socket.addEventListener("message", onMessage);
    socket.send(JSON.stringify(toSocketPayload(finishMessage(claimedScore))));
    setTimeout(() => {
      socket.removeEventListener("message", onMessage);
      resolve(null);
    }, 5000);
  });
}

async function openSocket(target) {
  const socket = new WebSocket(target);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  return socket;
}

async function waitForWelcome(socket) {
  return await new Promise((resolve, reject) => {
    const onMessage = (event) => {
      const message = JSON.parse(String(event.data));
      if (message.type === "welcome") {
        socket.removeEventListener("message", onMessage);
        resolve(message);
      }
    };
    socket.addEventListener("message", onMessage);
    socket.addEventListener("error", reject, { once: true });
  });
}

function prepareTraceEvents(trace) {
  let events = trace.events.filter(
    (entry) => entry.message?.type && entry.message.type !== "restart",
  );
  if (traceScale !== 1) {
    events = scaleTraceEvents(events, traceScale);
    console.log(`Applied TRACE_SCALE=${traceScale}`);
  }
  return events;
}

async function replayTrace(trace, socket) {
  const events = prepareTraceEvents(trace);
  const durationMs = events.at(-1)?.atMs || 0;
  const handEvents = events.filter((entry) => entry.message.type === "hands").length;
  const flaps = events.filter((entry) => entry.message.type === "flap").length;
  console.log(
    `Replaying trace: ${events.length} events, ${handEvents} hand samples, ${flaps} flaps, ${(durationMs / 1000).toFixed(2)}s`,
  );

  socket.send(JSON.stringify(toSocketPayload(restartMessage(), { traceAtMs: 0 })));

  await new Promise((resolve) => {
    for (const entry of events) {
      setTimeout(() => {
        if (socket.readyState !== WebSocket.OPEN) {
          return;
        }

        socket.send(JSON.stringify(toSocketPayload(entry.message, { traceAtMs: entry.atMs })));
      }, entry.atMs);
    }

    setTimeout(resolve, durationMs + 500);
  });
}

async function runSynthetic(modeName, socket, durationMs) {
  const sampleFor = createSampleGenerator(modeName);
  socket.send(JSON.stringify(toSocketPayload(restartMessage(), { traceAtMs: 0 })));

  await new Promise((resolve) => {
    let startedAt = Date.now();

    const pump = () => {
      const elapsed = Date.now() - startedAt;
      if (elapsed >= durationMs || socket.readyState !== WebSocket.OPEN) {
        resolve();
        return;
      }

      const sample = sampleFor(elapsed);
      socket.send(
        JSON.stringify(
          toSocketPayload(
            {
              type: "hands",
              leftY: sample.leftY,
              rightY: sample.rightY,
              handCount: sample.handCount,
            },
            { traceAtMs: elapsed },
          ),
        ),
      );

      setTimeout(pump, sampleIntervalMs);
    };

    pump();
  });
}

async function main() {
  const metrics = createSocketMetrics();

  if (mode === "trace") {
    const tracePath = argv[1];
    if (!tracePath) {
      throw new Error(
        "Usage: node scripts/simulate-hands.mjs trace /path/to/trace.json [ws://host/ws]",
      );
    }

    const trace = loadTrace(tracePath);
    console.log(`Connecting to ${targetUrl} (trace replay)`);
    const socket = await openSocket(targetUrl);
    socket.addEventListener("message", (event) => {
      metrics.handleMessage(JSON.parse(String(event.data)));
    });

    const welcome = await waitForWelcome(socket);
    console.log(`Connected as ${welcome.id}`);
    await replayTrace(trace, socket);
    const claimedScore = Number(process.env.SIMULATE_CLAIMED_SCORE || String(WIN_SCORE));
    const verified = await submitFinish(socket, claimedScore);
    console.log(
      `Trace replay finished. acceptedFlaps=${metrics.getAcceptedFlaps()} verified=${verified ? verified.valid : "timeout"}`,
    );
    socket.close();
    return;
  }

  console.log(`Connecting to ${targetUrl} (${mode} simulation for ${runMs}ms)`);
  const socket = await openSocket(targetUrl);
  socket.addEventListener("message", (event) => {
    metrics.handleMessage(JSON.parse(String(event.data)));
  });

  const welcome = await waitForWelcome(socket);
  console.log(`Connected as ${welcome.id}`);
  await runSynthetic(mode, socket, runMs);
  const claimedScore = Number(process.env.SIMULATE_CLAIMED_SCORE || String(WIN_SCORE));
  const verified = await submitFinish(socket, claimedScore);
  console.log(
    `Simulation finished. acceptedFlaps=${metrics.getAcceptedFlaps()} verified=${verified ? verified.valid : "timeout"}`,
  );
  socket.close();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
