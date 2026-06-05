#!/usr/bin/env node
import { spawn } from "node:child_process";
import { createServer as createHttpServer } from "node:http";
import { createServer as createNetServer } from "node:net";

const HOST = "127.0.0.1";

async function main() {
  const port = await freePort();
  const landmarkService = await startLandmarkService();
  const server = await startBackend(port, {
    landmarkServiceUrl: landmarkService.url,
  });

  try {
    await runCase("missing snapshot response", port, {
      respondToChallenges: false,
      expectedReason: "Snapshot challenge missed",
    });
    await runCase("invalid snapshot image", port, {
      respondToChallenges: true,
      expectedReason: "Snapshot image was unreadable",
    });
    await runCase("landmark mismatch", port, {
      respondToChallenges: true,
      snapshotImage: (index) => fakeJpegDataUrl(index),
      expectedReason: "Hand tracking dropped out too much",
    });
    console.log("snapshot challenge tests passed");
  } finally {
    server.kill("SIGTERM");
    landmarkService.close();
  }
}

async function freePort() {
  return await new Promise((resolve, reject) => {
    const server = createNetServer();
    server.on("error", reject);
    server.listen(0, HOST, () => {
      const address = server.address();
      const port = address.port;
      server.close(() => resolve(port));
    });
  });
}

async function startLandmarkService() {
  const port = await freePort();
  const server = createHttpServer((request, response) => {
    if (request.method !== "POST") {
      response.writeHead(405).end();
      return;
    }

    request.resume();
    request.on("end", () => {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(
        JSON.stringify({
          handCount: 2,
          leftY: 0.12,
          rightY: 0.88,
        }),
      );
    });
  });

  await new Promise((resolve, reject) => {
    server.on("error", reject);
    server.listen(port, HOST, resolve);
  });

  return {
    url: `http://${HOST}:${port}/landmarks`,
    close: () => server.close(),
  };
}

async function startBackend(port, { landmarkServiceUrl } = {}) {
  const child = spawn(process.execPath, ["backend/server.js"], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      HOST,
      PORT: String(port),
      FINAL_FLAG: "grey{test_flag}",
      SNAPSHOT_MIN_REQUIRED: "2",
      SNAPSHOT_START_DELAY_MS: "50",
      SNAPSHOT_MIN_INTERVAL_MS: "50",
      SNAPSHOT_MAX_INTERVAL_MS: "80",
      SNAPSHOT_DEADLINE_MS: "250",
      HAND_LANDMARK_SERVICE_URL: landmarkServiceUrl || "",
      SNAPSHOT_LANDMARK_MODE: landmarkServiceUrl ? "required" : "off",
      VIDEO_VERIFY_MODE: "off",
      VERIFY_SCORE_THRESHOLD: "50",
      CLIENT_SIM: "true",
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  let output = "";
  child.stdout.on("data", (chunk) => {
    output += chunk.toString("utf8");
  });
  child.stderr.on("data", (chunk) => {
    output += chunk.toString("utf8");
  });

  await waitUntil(() => output.includes("67 Flight backend listening"), 3000);
  return child;
}

async function runCase(name, port, { respondToChallenges, snapshotImage = () => "", expectedReason }) {
  const socket = new WebSocket(`ws://${HOST}:${port}/ws`);
  const startedAt = Date.now();
  let challengeCount = 0;
  let handTimer = null;
  let closed = null;

  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`${name}: timed out`)), 6000);

    socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (message.type === "welcome") {
        socket.send(JSON.stringify({ type: "restart", clientTime: Date.now(), traceAtMs: 0 }));
        handTimer = setInterval(() => sendHandSample(socket, startedAt), 25);
        return;
      }

      if (message.type === "snapshot_challenge") {
        challengeCount += 1;
        if (respondToChallenges) {
          socket.send(
            JSON.stringify({
              type: "snapshot",
              challengeId: message.challengeId,
              image: snapshotImage(challengeCount),
              leftY: 0.5,
              rightY: 0.5,
              handCount: 2,
              clientTime: Date.now(),
              traceAtMs: Date.now() - startedAt,
            }),
          );
        }
        if (challengeCount >= 2) {
          setTimeout(() => {
            socket.send(JSON.stringify({ type: "finish", score: 67, clientTime: Date.now() }));
          }, respondToChallenges ? 50 : 300);
        }
      }
    });

    socket.addEventListener("close", (event) => {
      clearTimeout(timeout);
      if (handTimer) {
        clearInterval(handTimer);
      }
      closed = { code: event.code, reason: event.reason };
      resolve();
    });

    socket.addEventListener("error", () => {
      clearTimeout(timeout);
      reject(new Error(`${name}: socket error`));
    });
  });

  if (closed?.code !== 1008 || !closed.reason.includes(expectedReason)) {
    throw new Error(
      `${name}: expected close 1008 containing "${expectedReason}", got ${JSON.stringify(closed)}`,
    );
  }
  console.log(`${name}: ${closed.reason}`);
}

function fakeJpegDataUrl(seed) {
  const bytes = Buffer.alloc(9000);
  let offset = 0;
  bytes[offset++] = 0xff;
  bytes[offset++] = 0xd8;
  bytes[offset++] = 0xff;
  bytes[offset++] = 0xc0;
  bytes.writeUInt16BE(17, offset);
  offset += 2;
  bytes[offset++] = 8;
  bytes.writeUInt16BE(240, offset);
  offset += 2;
  bytes.writeUInt16BE(320, offset);
  offset += 2;
  bytes[offset++] = 3;
  bytes[offset++] = 1;
  bytes[offset++] = 0x11;
  bytes[offset++] = 0;
  bytes[offset++] = 2;
  bytes[offset++] = 0x11;
  bytes[offset++] = 0;
  bytes[offset++] = 3;
  bytes[offset++] = 0x11;
  bytes[offset++] = 0;

  let state = seed >>> 0;
  for (; offset < bytes.length - 2; offset += 1) {
    state = (state * 1664525 + 1013904223) >>> 0;
    bytes[offset] = state & 0xff;
  }
  bytes[bytes.length - 2] = 0xff;
  bytes[bytes.length - 1] = 0xd9;
  return `data:image/jpeg;base64,${bytes.toString("base64")}`;
}

function sendHandSample(socket, startedAt) {
  if (socket.readyState !== WebSocket.OPEN) {
    return;
  }
  const elapsed = Date.now() - startedAt;
  const phase = elapsed / 210;
  socket.send(
    JSON.stringify({
      type: "hands",
      leftY: 0.48 + Math.sin(phase) * 0.03,
      rightY: 0.49 + Math.cos(phase * 0.9) * 0.03,
      handCount: 2,
      clientTime: Date.now(),
      traceAtMs: elapsed,
    }),
  );
}

async function waitUntil(check, timeoutMs) {
  const started = Date.now();
  while (!check()) {
    if (Date.now() - started > timeoutMs) {
      throw new Error("Timed out waiting for backend start.");
    }
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
