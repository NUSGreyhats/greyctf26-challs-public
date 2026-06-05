#!/usr/bin/env node
import { spawn } from "node:child_process";
import { createServer as createHttpServer } from "node:http";
import { createServer as createNetServer } from "node:net";

const HOST = "127.0.0.1";

async function main() {
  await runCase("missing video stream", {
    sendVideo: false,
    expectedReason: "Not enough camera frames were captured",
  });
  await runCase("static video landmarks", {
    sendVideo: true,
    staticLandmarks: true,
    expectedReason: "Hands didn't move enough in the camera",
  });
  await runCase("client/video mismatch", {
    sendVideo: true,
    mismatchLandmarks: true,
    expectedReason: "Hands didn't move enough in the camera",
  });
  console.log("video stream tests passed");
}

async function runCase(name, options) {
  const landmarkService = await startLandmarkService(options);
  const port = await freePort();
  const server = await startBackend(port, landmarkService.url);
  try {
    const reason = await exerciseRun(port, options);
    if (!reason.includes(options.expectedReason)) {
      throw new Error(`${name}: expected "${options.expectedReason}", got "${reason}"`);
    }
    console.log(`${name}: ${reason}`);
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

async function startLandmarkService(options) {
  const port = await freePort();
  let requestCount = 0;
  const server = createHttpServer((request, response) => {
    if (request.method !== "POST") {
      response.writeHead(405).end();
      return;
    }

    request.resume();
    request.on("end", () => {
      requestCount += 1;
      const moving = 0.5 + Math.sin(requestCount / 3) * 0.16;
      const leftY = options.staticLandmarks ? 0.5 : moving;
      const rightY = options.staticLandmarks
        ? 0.5
        : 0.5 + Math.cos(requestCount / 4) * 0.16;
      response.writeHead(200, { "content-type": "application/json" });
      response.end(
        JSON.stringify({
          handCount: 2,
          leftY: options.mismatchLandmarks ? 0.12 : leftY,
          rightY: options.mismatchLandmarks ? 0.88 : rightY,
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

async function startBackend(port, landmarkServiceUrl) {
  const child = spawn(process.execPath, ["backend/server.js"], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      HOST,
      PORT: String(port),
      FINAL_FLAG: "grey{test_flag}",
      SNAPSHOT_CHALLENGES: "false",
      HAND_LANDMARK_SERVICE_URL: landmarkServiceUrl,
      SNAPSHOT_LANDMARK_MODE: "required",
      VIDEO_VERIFY_MODE: "required",
      VIDEO_VERIFY_MIN_FRAMES: "8",
      VIDEO_VERIFY_MIN_VALID_FRAMES: "8",
      VIDEO_VERIFY_MIN_AVERAGE_FPS: "2",
      VIDEO_VERIFY_MAX_MEDIAN_GAP_MS: "280",
      VIDEO_VERIFY_MAX_P90_GAP_MS: "320",
      VIDEO_VERIFY_MAX_P99_GAP_MS: "360",
      VIDEO_VERIFY_MIN_MOTION_RANGE: "0.16",
      VIDEO_VERIFY_MIN_MOVING_FRAME_RATIO: "0.25",
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

async function exerciseRun(port, { sendVideo }) {
  const socket = new WebSocket(`ws://${HOST}:${port}/ws`);
  const startedAt = Date.now();
  let closed = null;

  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("timed out")), 6000);

    socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data));
      if (message.type !== "welcome") {
        return;
      }

      socket.send(JSON.stringify({ type: "restart", clientTime: Date.now(), traceAtMs: 0 }));
      for (let index = 0; index < 12; index += 1) {
        setTimeout(() => {
          const elapsed = Date.now() - startedAt;
          const leftY = 0.48 + Math.sin(index / 3) * 0.08;
          const rightY = 0.49 + Math.cos(index / 4) * 0.08;
          socket.send(
            JSON.stringify({
              type: "hands",
              leftY,
              rightY,
              handCount: 2,
              clientTime: Date.now(),
              traceAtMs: elapsed,
            }),
          );
          if (sendVideo) {
            socket.send(
              JSON.stringify({
                type: "video_frame",
                sequence: index + 1,
                image: fakeJpegDataUrl(index + 1),
                leftY,
                rightY,
                handCount: 2,
                clientTime: Date.now(),
                traceAtMs: elapsed,
              }),
            );
          }
          if (index === 11) {
            setTimeout(() => {
              socket.send(JSON.stringify({ type: "finish", score: 67, clientTime: Date.now() }));
            }, 120);
          }
        }, index * 90);
      }
    });

    socket.addEventListener("close", (event) => {
      clearTimeout(timeout);
      closed = { code: event.code, reason: event.reason };
      resolve();
    });

    socket.addEventListener("error", () => {
      clearTimeout(timeout);
      reject(new Error("socket error"));
    });
  });

  if (closed?.code !== 1008) {
    throw new Error(`expected close 1008, got ${JSON.stringify(closed)}`);
  }
  return closed.reason;
}

function fakeJpegDataUrl(seed) {
  const bytes = Buffer.alloc(9500);
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
