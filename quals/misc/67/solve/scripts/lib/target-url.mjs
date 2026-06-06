/**
 * Resolve load-test WebSocket targets (direct backend, remote host, solve proxy).
 */

export function normalizeBackendUrl(rawTarget) {
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
  } else if (url.protocol !== "ws:" && url.protocol !== "wss:") {
    throw new Error(`Unsupported WebSocket protocol: ${url.protocol}`);
  }

  const pathname = url.pathname.replace(/\/+$/, "");
  url.pathname = pathname.endsWith("/ws") ? pathname : `${pathname || ""}/ws`;
  url.search = "";
  url.hash = "";
  return url.toString();
}

export function backendUrlFromServer(server) {
  const trimmed = String(server).trim();
  if (!trimmed) {
    throw new Error("--server requires a host or URL");
  }

  if (trimmed.includes("://")) {
    return normalizeBackendUrl(trimmed);
  }

  const hasPath = trimmed.includes("/");
  const base = hasPath ? `ws://${trimmed}` : `ws://${trimmed}/ws`;
  return normalizeBackendUrl(base);
}

export function proxyUrlFromOptions({ proxyHost, backendUrl }) {
  const host = proxyHost?.trim() || "127.0.0.1:4180";
  const base = host.includes("://") ? host : `ws://${host}`;
  const url = new URL("/ws", base.endsWith("/") ? base : `${base}/`);

  if (backendUrl) {
    url.searchParams.set("target", normalizeBackendUrl(backendUrl));
  }

  return url.toString();
}

/**
 * @param {object} options
 * @param {string} [options.url]           Full ws/wss URL (--url)
 * @param {string} [options.server]        Backend host:port or URL (--server)
 * @param {string} [options.proxy]         Solve proxy host:port; set to "" for default 4180
 * @param {string} [options.proxyTarget]   Backend behind proxy (--proxy-target)
 * @param {string} [options.envUrl]        TARGET_WS_URL
 */
export function resolveLoadTestTarget(options) {
  const envUrl = options.envUrl?.trim();
  const urlFlag = options.url?.trim();
  const serverFlag = options.server?.trim();
  const proxyFlag = options.proxy;
  const proxyTarget = (options.proxyTarget || options.proxyClient || "").trim();

  if (urlFlag && (serverFlag || proxyFlag !== undefined)) {
    throw new Error("Use only one of --url, --server, or --proxy");
  }

  if (proxyFlag !== undefined) {
    if (proxyFlag && (proxyFlag.startsWith("--") || proxyFlag.includes("://") && proxyFlag.includes("--"))) {
      throw new Error(
        `Invalid --proxy host "${proxyFlag}". Use bare --proxy with --proxy-target <url>, or --url for a direct connection.`,
      );
    }

    const backendUrl = proxyTarget || envUrl || null;
    if (!backendUrl) {
      throw new Error(
        "With --proxy, set the remote game server via --proxy-target <ws-url> (alias: --proxy-client).",
      );
    }

    return {
      targetUrl: proxyUrlFromOptions({
        proxyHost: proxyFlag === true || proxyFlag === "" ? null : proxyFlag,
        backendUrl,
      }),
      kind: "proxy",
      backendUrl: normalizeBackendUrl(backendUrl),
    };
  }

  if (serverFlag) {
    return {
      targetUrl: backendUrlFromServer(serverFlag),
      kind: "backend",
      backendUrl: null,
    };
  }

  const direct = urlFlag || envUrl || "ws://127.0.0.1:8787/ws";
  return {
    targetUrl: normalizeBackendUrl(direct),
    kind: "backend",
    backendUrl: null,
  };
}
