import { createHash, randomUUID } from "node:crypto";
import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize, resolve } from "node:path";

const ROOT = process.cwd();
const SOLVE_FRONTEND_ROOT = resolve(ROOT, "solve/frontend");
const SOLVE_LIB_ROOT = resolve(ROOT, "solve/lib");
const SOLVE_MEDIA_ROOT = resolve(ROOT, "solve");
const SHARED_ASSET_ROOT = resolve(ROOT, "frontend/public/assets");
const SHARED_ROOT = resolve(ROOT, "shared");
const PUBLIC_SHARED_MODULES = new Set(["game-core.js", "frontend-client.js"]);
const PORT = Number(process.env.SOLVE_PORT || process.env.PORT || "4180");
const HOST = process.env.SOLVE_HOST || process.env.HOST || "127.0.0.1";
const DEFAULT_TARGET_WS_URL = normalizeTargetUrl(
  process.env.TARGET_WS_URL || "ws://127.0.0.1:8787/ws",
);

const MIME_TYPES = new Map([
  [".html", "text/html; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".svg", "image/svg+xml"],
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".mov", "video/quicktime"],
  [".mp4", "video/mp4"],
  [".webm", "video/webm"],
  [".ico", "image/x-icon"],
]);

const proxySessions = new Set();

const server = createServer(async (request, response) => {
  if (!request.url) {
    response.writeHead(400).end("Bad request");
    return;
  }

  const url = new URL(request.url, `http://${request.headers.host}`);
  if (url.pathname === "/api/healthz") {
    response.writeHead(200, { "content-type": "application/json; charset=utf-8" });
    response.end(
      JSON.stringify({
        ok: true,
        proxySessions: proxySessions.size,
        defaultTarget: DEFAULT_TARGET_WS_URL,
      }),
    );
    return;
  }

  if (url.pathname === "/api/config") {
    response.writeHead(200, { "content-type": "application/json; charset=utf-8" });
    response.end(
      JSON.stringify({
        defaultTarget: DEFAULT_TARGET_WS_URL,
        assetPath: "/shared-assets/flappy_atlas.png",
      }),
    );
    return;
  }

  if (url.pathname.startsWith("/shared-assets/")) {
    await serveStaticFrom(SHARED_ASSET_ROOT, url.pathname.replace("/shared-assets", ""), response, request);
    return;
  }

  if (url.pathname.startsWith("/solve-lib/")) {
    await serveStaticFrom(SOLVE_LIB_ROOT, url.pathname.replace("/solve-lib", ""), response, request);
    return;
  }

  if (url.pathname.startsWith("/shared/")) {
    const sharedRelativePath = normalize(decodeURIComponent(url.pathname.slice("/shared/".length))).replace(
      /^(\.\.(\/|\\|$))+/,
      "",
    );
    const sharedBasename = sharedRelativePath.split(/[/\\]/).pop();
    if (!PUBLIC_SHARED_MODULES.has(sharedBasename)) {
      response.writeHead(404, { "content-type": "text/plain; charset=utf-8" }).end("Not found");
      return;
    }
    await serveStaticFrom(SHARED_ROOT, url.pathname.replace("/shared", ""), response, request);
    return;
  }

  if (url.pathname.startsWith("/media/")) {
    await serveStaticFrom(SOLVE_MEDIA_ROOT, url.pathname.replace("/media", ""), response, request);
    return;
  }

  await serveStaticFrom(SOLVE_FRONTEND_ROOT, url.pathname, response, request);
});

server.on("upgrade", (request, socket) => {
  if (!request.url) {
    socket.destroy();
    return;
  }

  const url = new URL(request.url, `http://${request.headers.host}`);
  if (url.pathname === "/ws") {
    const connection = acceptWebSocket(request, socket);
    if (!connection) {
      return;
    }
    new ProxySession(connection, request);
    return;
  }

  socket.destroy();
});

process.on("uncaughtException", (error) => {
  console.error("[solve] uncaughtException:", error);
});

process.on("unhandledRejection", (error) => {
  console.error("[solve] unhandledRejection:", error);
});

server.listen(PORT, HOST, () => {
  console.log(`solve frontend listening on http://${HOST}:${PORT}`);
  console.log(`proxy target default ${DEFAULT_TARGET_WS_URL}`);
});

class ProxySession {
  constructor(client, request) {
    this.id = randomUUID().slice(0, 8);
    this.client = client;
    this.request = request;
    this.closed = false;
    this.backend = null;
    this.targetUrl = resolveTargetUrlFromRequest(request);
    proxySessions.add(this);

    this.client.onMessage = (payload, opcode) => this.handleClientFrame(payload, opcode);
    this.client.onClose = ({ code, reason }) => this.handleClientClose(code, reason);

    this.connectBackend();
  }

  connectBackend() {
    this.backend = new WebSocket(this.targetUrl);
    this.backend.binaryType = "arraybuffer";

    this.backend.addEventListener("message", (event) => {
      const payload = toBuffer(event.data);
      if (typeof event.data === "string") {
        this.client.sendText(event.data);
      } else {
        this.client.sendBinary(payload);
      }
    });

    this.backend.addEventListener("close", (event) => {
      this.close(safeCloseCode(event.code), event.reason || "backend closed");
    });
  }

  handleClientFrame(payload, opcode) {
    if (this.closed) {
      return;
    }

    if (!this.backend || this.backend.readyState !== WebSocket.OPEN) {
      return;
    }

    if (opcode === 0x1) {
      this.backend.send(payload.toString("utf8"));
      return;
    }

    this.backend.send(payload);
  }

  handleClientClose(code, reason) {
    this.close(safeCloseCode(code), reason || "client closed");
  }

  close(code = 1000, reason = "closed") {
    if (this.closed) {
      return;
    }
    this.closed = true;
    proxySessions.delete(this);

    const sendCode = safeCloseCode(code);
    const sendReason = safeCloseReason(reason);

    if (this.backend) {
      forceCloseWebSocket(this.backend, sendCode, sendReason, this.id);
      this.backend = null;
    }
    this.client.close(sendCode, sendReason);
  }
}

class RawWebSocketConnection {
  constructor(socket) {
    this.socket = socket;
    this.buffer = Buffer.alloc(0);
    this.closed = false;
    this.onMessage = () => {};
    this.onClose = () => {};

    socket.on("data", (chunk) => this.receive(chunk));
    socket.on("close", () => this.close(1000, "socket closed"));
    socket.on("error", () => this.close(1006, "socket error"));
  }

  receive(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);

    while (this.buffer.length >= 2) {
      const frame = parseFrame(this.buffer);
      if (!frame) {
        return;
      }

      this.buffer = this.buffer.subarray(frame.bytes);
      if (frame.opcode === 0x8) {
        const { code, reason } = parseClosePayload(frame.payload);
        this.close(code, reason);
        return;
      }

      if (frame.opcode === 0x9) {
        this.writeFrame(frame.payload, 0xA);
        continue;
      }

      if (frame.opcode === 0xA) {
        continue;
      }

      if (frame.opcode === 0x1 || frame.opcode === 0x2) {
        this.onMessage(frame.payload, frame.opcode);
      }
    }
  }

  sendText(text) {
    this.writeFrame(Buffer.from(text, "utf8"), 0x1);
  }

  sendBinary(buffer) {
    this.writeFrame(Buffer.from(buffer), 0x2);
  }

  sendJson(value) {
    this.sendText(JSON.stringify(value));
  }

  writeFrame(payload, opcode = 0x1) {
    if (this.closed || this.socket.destroyed) {
      return;
    }

    const length = payload.length;
    let header;
    if (length < 126) {
      header = Buffer.from([0x80 | opcode, length]);
    } else if (length < 65536) {
      header = Buffer.alloc(4);
      header[0] = 0x80 | opcode;
      header[1] = 126;
      header.writeUInt16BE(length, 2);
    } else {
      header = Buffer.alloc(10);
      header[0] = 0x80 | opcode;
      header[1] = 127;
      header.writeBigUInt64BE(BigInt(length), 2);
    }

    this.socket.write(Buffer.concat([header, payload]));
  }

  close(code = 1000, reason = "closed") {
    if (this.closed) {
      return;
    }
    const sendCode = safeCloseCode(code);
    const sendReason = safeCloseReason(reason);

    if (!this.socket.destroyed) {
      const payload = closePayload(sendCode, sendReason);
      this.writeFrame(payload, 0x8);
      this.socket.end();
    }
    this.closed = true;
    this.onClose({ code: sendCode, reason: sendReason });
  }
}

async function serveStaticFrom(root, pathname, response, request) {
  const requestedPath = pathname === "/" ? "/index.html" : decodeURIComponent(pathname);
  const normalized = normalize(requestedPath).replace(/^(\.\.(\/|\\|$))+/, "");
  const absolutePath = resolve(join(root, normalized));

  if (!absolutePath.startsWith(root)) {
    response.writeHead(403, { "content-type": "text/plain; charset=utf-8" }).end("Forbidden");
    return;
  }

  try {
    const fileStat = await stat(absolutePath);
    if (!fileStat.isFile()) {
      response.writeHead(404, { "content-type": "text/plain; charset=utf-8" }).end("Not found");
      return;
    }

    const contentType = MIME_TYPES.get(extname(absolutePath)) || "application/octet-stream";
    const range = parseRangeHeader(request?.headers?.range, fileStat.size);
    if (range) {
      response.writeHead(206, {
        "content-type": contentType,
        "cache-control": "no-store",
        "accept-ranges": "bytes",
        "content-range": `bytes ${range.start}-${range.end}/${fileStat.size}`,
        "content-length": range.end - range.start + 1,
      });
      createReadStream(absolutePath, range).pipe(response);
      return;
    }

    response.writeHead(200, {
      "content-type": contentType,
      "cache-control": "no-store",
      "accept-ranges": "bytes",
      "content-length": fileStat.size,
    });
    createReadStream(absolutePath).pipe(response);
  } catch {
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" }).end("Not found");
  }
}

function parseRangeHeader(rawRange, fileSize) {
  if (!rawRange || !rawRange.startsWith("bytes=")) {
    return null;
  }
  const [rawStart, rawEnd] = rawRange.slice("bytes=".length).split("-");
  const start = Number(rawStart);
  const end = rawEnd ? Number(rawEnd) : fileSize - 1;
  if (
    !Number.isInteger(start) ||
    !Number.isInteger(end) ||
    start < 0 ||
    end < start ||
    start >= fileSize
  ) {
    return null;
  }
  return {
    start,
    end: Math.min(end, fileSize - 1),
  };
}

function acceptWebSocket(request, socket) {
  const key = request.headers["sec-websocket-key"];
  if (!key || request.headers.upgrade?.toLowerCase() !== "websocket") {
    socket.destroy();
    return null;
  }

  const accept = createHash("sha1")
    .update(`${key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`)
    .digest("base64");

  socket.write(
    [
      "HTTP/1.1 101 Switching Protocols",
      "Upgrade: websocket",
      "Connection: Upgrade",
      `Sec-WebSocket-Accept: ${accept}`,
      "",
      "",
    ].join("\r\n"),
  );

  return new RawWebSocketConnection(socket);
}

function resolveTargetUrlFromRequest(request) {
  const url = new URL(request.url, `http://${request.headers.host}`);
  return normalizeTargetUrl(url.searchParams.get("target") || DEFAULT_TARGET_WS_URL);
}

function normalizeTargetUrl(rawTarget) {
  let url;
  try {
    url = new URL(rawTarget);
  } catch {
    url = new URL(rawTarget, "ws://127.0.0.1:8787");
  }

  if (url.protocol === "http:") {
    url.protocol = "ws:";
  } else if (url.protocol === "https:") {
    url.protocol = "wss:";
  }

  const pathname = url.pathname.replace(/\/+$/, "");
  url.pathname = pathname.endsWith("/ws") ? pathname : `${pathname || ""}/ws`;
  url.search = "";
  url.hash = "";
  return url.toString();
}

function toBuffer(data) {
  if (typeof data === "string") {
    return Buffer.from(data, "utf8");
  }
  if (data instanceof ArrayBuffer) {
    return Buffer.from(data);
  }
  if (ArrayBuffer.isView(data)) {
    return Buffer.from(data.buffer, data.byteOffset, data.byteLength);
  }
  return Buffer.from([]);
}

function closePayload(code, reason) {
  const safeReason = String(reason || "").slice(0, 123);
  const payload = Buffer.alloc(2 + Buffer.byteLength(safeReason));
  payload.writeUInt16BE(code, 0);
  payload.write(safeReason, 2);
  return payload;
}

function parseClosePayload(payload) {
  if (!payload || payload.length < 2) {
    return { code: 1000, reason: "closed" };
  }
  return {
    code: safeCloseCode(payload.readUInt16BE(0)),
    reason: payload.subarray(2).toString("utf8"),
  };
}

function parseFrame(buffer) {
  const first = buffer[0];
  const second = buffer[1];
  const opcode = first & 0x0f;
  const masked = (second & 0x80) === 0x80;
  let length = second & 0x7f;
  let offset = 2;

  if (length === 126) {
    if (buffer.length < offset + 2) {
      return null;
    }
    length = buffer.readUInt16BE(offset);
    offset += 2;
  } else if (length === 127) {
    if (buffer.length < offset + 8) {
      return null;
    }
    const bigLength = buffer.readBigUInt64BE(offset);
    if (bigLength > BigInt(Number.MAX_SAFE_INTEGER)) {
      throw new Error("Frame too large");
    }
    length = Number(bigLength);
    offset += 8;
  }

  let maskingKey;
  if (masked) {
    if (buffer.length < offset + 4) {
      return null;
    }
    maskingKey = buffer.subarray(offset, offset + 4);
    offset += 4;
  }

  if (buffer.length < offset + length) {
    return null;
  }

  const payload = Buffer.from(buffer.subarray(offset, offset + length));
  if (masked && maskingKey) {
    for (let index = 0; index < payload.length; index += 1) {
      payload[index] ^= maskingKey[index % 4];
    }
  }

  return {
    opcode,
    payload,
    bytes: offset + length,
  };
}

function forceCloseWebSocket(ws, code = 1000, reason = "closed", sessionId = "") {
  if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
    return;
  }

  if (typeof ws.terminate === "function") {
    try {
      ws.terminate();
    } catch (error) {
      console.warn(`[proxy ${sessionId}] backend terminate failed: ${error.message}`);
    }
    return;
  }

  if (ws.readyState !== WebSocket.OPEN) {
    return;
  }

  try {
    ws.close(code, reason);
  } catch (error) {
    console.warn(`[proxy ${sessionId}] backend close failed: ${error.message}`);
    try {
      ws.close();
    } catch {
      // ignore — connection may already be gone
    }
  }
}

function safeCloseCode(code) {
  if (!Number.isInteger(code)) {
    return 1000;
  }
  if (code >= 3000 && code <= 4999) {
    return code;
  }
  if ([1000, 1001, 1002, 1003, 1007, 1008, 1009, 1010, 1011].includes(code)) {
    return code;
  }
  return 1000;
}

function safeCloseReason(reason) {
  return String(reason || "closed").slice(0, 123);
}
