const baseUrl = (process.argv[2] || "http://127.0.0.1:34467").replace(/\/+$/, "");

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function extractCookie(headers) {
  const raw = headers.get("set-cookie");
  if (!raw) {
    return "";
  }
  return raw.split(";")[0];
}

function decodeStamp(stamp, traceId) {
  const encoded = Buffer.from(stamp, "base64");
  const parts = String(traceId || "").split("-");
  const seed = parts.length >= 3 ? parts[1] : "";
  const index = Number(parts.length >= 3 ? parts[2] : 0) - 1;
  const keyBase =
    seed.split("").reduce((sum, ch) => sum + ch.charCodeAt(0), 0) + Math.max(0, index) * 17;
  const bytes = [];

  for (let i = 0; i < encoded.length; i += 1) {
    bytes.push(encoded[i] ^ ((keyBase + i * 13) & 0xff));
  }

  return Buffer.from(bytes).toString("utf8");
}

async function requestJson(url, options = {}, cookie = "") {
  const headers = {
    ...(options.headers || {}),
  };
  if (cookie) {
    headers.Cookie = cookie;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  const text = await response.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch (error) {
    throw new Error(`Non-JSON response from ${url}: ${text}`);
  }

  return {
    response,
    json,
    cookie: extractCookie(response.headers) || cookie,
  };
}

async function main() {
  let cookie = "";

  const bootstrap = await requestJson(`${baseUrl}/api/bootstrap`, {}, cookie);
  cookie = bootstrap.cookie;
  const fastPhaseScore = bootstrap.json.fastPhaseScore;

  const runSamples = [
    { tick: 0, score: 0 },
    { tick: 90, score: 180 },
    { tick: 180, score: 420 },
    { tick: 300, score: 980 },
    { tick: 420, score: 1640 },
    { tick: 500, score: 2010 },
    { tick: 540, score: fastPhaseScore + 40 },
  ];

  for (const sample of runSamples) {
    const run = await requestJson(
      `${baseUrl}/api/run?score=${sample.score}&tick=${sample.tick}&state=running`,
      {},
      cookie,
    );
    cookie = run.cookie;
    await sleep(1100);
  }

  const fragments = [];
  for (let attempt = 0; attempt < 12; attempt += 1) {
    const ghost = await requestJson(
      `${baseUrl}/api/ghost?score=${fastPhaseScore + 50}&lane=${attempt % 2}`,
      {},
      cookie,
    );
    cookie = ghost.cookie;
    if (ghost.json.stamp && ghost.json.traceId) {
      fragments.push(decodeStamp(ghost.json.stamp, ghost.json.traceId));
      if (fragments.join("").endsWith("}")) {
        break;
      }
    }
  }

  const flag = fragments.join("");

  console.log(`base_url=${baseUrl}`);
  console.log(`session=${bootstrap.json.session}`);
  console.log(`fast_phase_score=${fastPhaseScore}`);
  console.log(`fragments=${JSON.stringify(fragments)}`);
  console.log(`flag=${flag}`);
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
