import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const PUBLIC_ROOT = resolve(__dirname);
const SHARED_ROOT = resolve(__dirname, "..", "shared");
const PUBLIC_SHARED_MODULES = new Set(["game-core.js", "frontend-client.js"]);
const PORT = Number(process.env.FRONTEND_PORT || process.env.PORT || "4173");
const HOST = process.env.FRONTEND_HOST || process.env.HOST || "127.0.0.1";
const DIAGNOSTIC_PAGE = parseBoolean(process.env.DIAGNOSTIC_PAGE, false);

const mimeTypes = new Map([
  [".html", "text/html; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".md", "text/markdown; charset=utf-8"],
  [".svg", "image/svg+xml"],
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".ico", "image/x-icon"],
]);

const server = createServer(async (request, response) => {
  if (!request.url) {
    response.writeHead(400).end("Bad request");
    return;
  }

  const url = new URL(request.url, `http://${request.headers.host}`);
  if (url.pathname === "/diagnostics" || url.pathname === "/diagnostics/") {
    if (!DIAGNOSTIC_PAGE) {
      response.writeHead(404).end("Not found");
      return;
    }
    await serveStatic("/diagnostics.html", response);
    return;
  }
  await serveStatic(url.pathname, response);
});

server.listen(PORT, HOST, () => {
  console.log(`67 Flight frontend listening on http://${HOST}:${PORT}`);
});

async function serveStatic(pathname, response) {
  if (pathname.startsWith("/shared/")) {
    const normalizedSharedPath = normalize(decodeURIComponent(pathname.slice("/shared/".length))).replace(
      /^(\.\.(\/|\\|$))+/,
      "",
    );
    const sharedAbsolutePath = resolve(join(SHARED_ROOT, normalizedSharedPath));
    if (!sharedAbsolutePath.startsWith(SHARED_ROOT)) {
      response.writeHead(403).end("Forbidden");
      return;
    }
    const sharedBasename = normalizedSharedPath.split(/[/\\]/).pop();
    if (!PUBLIC_SHARED_MODULES.has(sharedBasename)) {
      response.writeHead(404).end("Not found");
      return;
    }
    try {
      const fileStat = await stat(sharedAbsolutePath);
      if (!fileStat.isFile()) {
        response.writeHead(404).end("Not found");
        return;
      }

      response.writeHead(200, {
        "content-type": mimeTypes.get(extname(sharedAbsolutePath)) || "application/octet-stream",
        "cache-control": "no-store",
      });
      createReadStream(sharedAbsolutePath).pipe(response);
    } catch {
      response.writeHead(404).end("Not found");
    }
    return;
  }

  const requestedPath = pathname === "/" ? "/index.html" : decodeURIComponent(pathname);
  if (requestedPath === "/diagnostics.html" && !DIAGNOSTIC_PAGE) {
    response.writeHead(404).end("Not found");
    return;
  }
  const normalized = normalize(requestedPath).replace(/^(\.\.(\/|\\|$))+/, "");
  const absolutePath = resolve(join(PUBLIC_ROOT, normalized));

  if (!absolutePath.startsWith(PUBLIC_ROOT)) {
    response.writeHead(403).end("Forbidden");
    return;
  }

  try {
    const fileStat = await stat(absolutePath);
    if (!fileStat.isFile()) {
      response.writeHead(404).end("Not found");
      return;
    }

    response.writeHead(200, {
      "content-type": mimeTypes.get(extname(absolutePath)) || "application/octet-stream",
      "cache-control": "no-store",
    });
    createReadStream(absolutePath).pipe(response);
  } catch {
    response.writeHead(404).end("Not found");
  }
}

function parseBoolean(value, fallback) {
  if (value === undefined) {
    return fallback;
  }
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}
