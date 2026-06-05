const http = require("http");
const fs = require("fs");
const path = require("path");
const { URL } = require("url");
const crypto = require("crypto");

const root = __dirname;
const port = Number(process.env.PORT || 4173);
const FLAG_FRAGMENTS = [
  "grey{th3_",
  "trex_",
  "rep1ac3d_",
  "by_a_",
  "gr3y_",
  "cat}",
];
const FAST_PHASE_SCORE = 2250;

const types = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
};

const blockedFiles = new Set([
  "serve-local.js",
  "solve.js",
  "SOLUTION.md",
  "progress.md",
  "Dockerfile",
  ".dockerignore",
  "cat.json",
]);

const sessions = new Map();

function maskFragment(fragment) {
  return fragment.replace(/[a-z0-9]/gi, ".");
}

function encodeTrace(fragment, session, index) {
  const salt = `${session.seed}:${index}`;
  return Buffer.from(`${salt}:${fragment}`, "utf8").toString("base64");
}

function encodeStamp(fragment, session, index) {
  const key = session.seed
    .split("")
    .reduce((sum, ch) => sum + ch.charCodeAt(0), 0) + index * 17;
  const bytes = Array.from(fragment, (ch, offset) => {
    return ch.charCodeAt(0) ^ ((key + offset * 13) & 0xff);
  });
  return Buffer.from(bytes).toString("base64");
}

function sendJson(res, statusCode, body, extraHeaders = {}) {
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    ...extraHeaders,
  });
  res.end(JSON.stringify(body));
}

function parseCookies(cookieHeader = "") {
  return Object.fromEntries(
    cookieHeader
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => {
        const pivot = part.indexOf("=");
        if (pivot === -1) {
          return [part, ""];
        }
        return [part.slice(0, pivot), decodeURIComponent(part.slice(pivot + 1))];
      }),
  );
}

function createSession() {
  const id = crypto.randomBytes(8).toString("hex");
  const seed = crypto.randomBytes(4).toString("hex");
  const session = {
    id,
    seed,
    history: [],
    issuedCount: 0,
    run: {
      startedAt: 0,
      lastTick: 0,
      lastScore: 0,
      lastUpdateAt: 0,
      validSamples: 0,
      unlocked: false,
      crashed: false,
    },
  };
  sessions.set(id, session);
  return session;
}

function getSession(req, res) {
  const cookies = parseCookies(req.headers.cookie);
  let session = cookies.sid ? sessions.get(cookies.sid) : null;
  if (!session) {
    session = createSession();
    res.setHeader("Set-Cookie", `sid=${session.id}; Path=/; HttpOnly; SameSite=Lax`);
  }
  return session;
}

function serveFile(reqPath, res) {
  const safePath = path.normalize(reqPath).replace(/^(\.\.[/\\])+/, "");
  const filePath = path.join(root, safePath);
  const fileName = path.basename(filePath);

  if (!filePath.startsWith(root)) {
    res.writeHead(403);
    res.end("Forbidden");
    return;
  }

  if (blockedFiles.has(fileName)) {
    res.writeHead(404, {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
    });
    res.end("Not found");
    return;
  }

  fs.readFile(filePath, (error, data) => {
    if (error) {
      res.writeHead(error.code === "ENOENT" ? 404 : 500, {
        "Content-Type": "text/plain; charset=utf-8",
      });
      res.end(error.code === "ENOENT" ? "Not found" : "Server error");
      return;
    }

    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, {
      "Content-Type": types[ext] || "application/octet-stream",
      "Cache-Control": "no-store",
    });
    res.end(data);
  });
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || "127.0.0.1"}`);
  const pathname = url.pathname === "/" ? "/index.html" : url.pathname;
  const session = getSession(req, res);

  if (pathname === "/api/bootstrap") {
    session.run = {
      startedAt: 0,
      lastTick: 0,
      lastScore: 0,
      lastUpdateAt: 0,
      validSamples: 0,
      unlocked: false,
      crashed: false,
    };
    session.history = [];
    session.issuedCount = 0;
    sendJson(res, 200, {
      session: session.id,
      fastPhaseScore: FAST_PHASE_SCORE,
    });
    return;
  }

  if (pathname === "/api/run") {
    const score = Number(url.searchParams.get("score") || 0);
    const tick = Number(url.searchParams.get("tick") || 0);
    const state = String(url.searchParams.get("state") || "running");
    const now = Date.now();
    const run = session.run;

    if (!Number.isFinite(score) || !Number.isFinite(tick) || score < 0 || tick < 0) {
      sendJson(res, 400, { ok: false, error: "bad_run_sample" });
      return;
    }

    if (run.startedAt === 0) {
      run.startedAt = now;
      run.lastUpdateAt = now;
      run.lastTick = tick;
      run.lastScore = score;
      run.validSamples = 1;
      run.crashed = state === "crashed";
      sendJson(res, 200, {
        ok: true,
        accepted: true,
        unlocked: run.unlocked,
        validSamples: run.validSamples,
      });
      return;
    }

    const deltaTick = tick - run.lastTick;
    const deltaScore = score - run.lastScore;
    const deltaMs = Math.max(1, now - run.lastUpdateAt);
    const maxTickAdvance = Math.max(30, Math.floor(deltaMs / 6));
    const maxScoreAdvance = Math.max(80, deltaTick * 8.5);
    const plausible =
      deltaTick >= 0 &&
      deltaScore >= 0 &&
      deltaTick <= maxTickAdvance &&
      deltaScore <= maxScoreAdvance;

    if (!plausible) {
      sendJson(res, 200, {
        ok: true,
        accepted: false,
        unlocked: false,
        validSamples: run.validSamples,
      });
      return;
    }

    run.lastTick = tick;
    run.lastScore = score;
    run.lastUpdateAt = now;
    run.validSamples += 1;
    run.crashed = state === "crashed";

    if (
      !run.unlocked &&
      run.validSamples >= 6 &&
      score >= FAST_PHASE_SCORE &&
      tick >= 500 &&
      now - run.startedAt >= 5000
    ) {
      run.unlocked = true;
    }

    sendJson(res, 200, {
      ok: true,
      accepted: true,
      unlocked: run.unlocked,
      validSamples: run.validSamples,
    });
    return;
  }

  if (pathname === "/api/ghost") {
    const score = Number(url.searchParams.get("score") || 0);
    const lane = Number(url.searchParams.get("lane") || 0);
    const forceTrace = req.headers["x-runner-debug"] === "trace";
    const isFastPhase = score >= FAST_PHASE_SCORE && session.run.unlocked;
    let trace = null;
    let echo = null;
    let stamp = null;

    if (isFastPhase) {
      const fragment = FLAG_FRAGMENTS[session.issuedCount % FLAG_FRAGMENTS.length];
      trace = encodeTrace(fragment, session, session.issuedCount);
      echo = maskFragment(fragment);
      stamp = encodeStamp(fragment, session, session.issuedCount);
      session.issuedCount += 1;
      session.history.push({
        trace,
        echo,
        stamp,
        score: Math.floor(score),
        lane,
        at: Date.now(),
      });
    } else {
      session.history.push({
        trace: null,
        echo: null,
        stamp: null,
        score: Math.floor(score),
        lane,
        at: Date.now(),
      });
    }

    const headers = {};
    if (trace && forceTrace) {
      headers["X-Runner-Trace"] = trace;
    }

    sendJson(
      res,
      200,
      {
        ok: true,
        lane,
        fastPhase: isFastPhase,
        traceId: trace ? `ghost-${session.seed}-${session.issuedCount}` : null,
        echo,
        stamp,
        ttl: trace ? 22 : 0,
      },
      headers,
    );
    return;
  }

  if (pathname === "/api/replay") {
    const exportMode = url.searchParams.get("view");
    const includeFragments = exportMode === "debug";
    const payload = {
      session: session.id,
      attempts: session.history.length,
      fastPhaseHits: session.history.filter((entry) => entry.trace).length,
      checksum: `bg:7f3a1:${session.seed}`,
      unlocked: session.run.unlocked,
      validSamples: session.run.validSamples,
    };

    if (includeFragments) {
      payload.trace = session.history
        .filter((entry) => entry.trace)
        .map((entry) => ({
          lane: entry.lane,
          score: entry.score,
          trace: entry.trace,
          echo: entry.echo,
          stamp: entry.stamp,
        }));
    }

    sendJson(res, 200, payload);
    return;
  }

  serveFile(pathname, res);
});

server.listen(port, "0.0.0.0", () => {
  console.log(`GreyCat Game serving on http://0.0.0.0:${port}`);
});
