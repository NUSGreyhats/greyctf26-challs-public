import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { buildTimeSeries, mergeTypeMetrics } from "./load-test-metrics.mjs";

export function buildLoadTestReport(options) {
  const { meta, thresholds, rounds, lastSustainable } = options;

  const normalizedRounds = rounds.map((round) => {
    const byMessageType = mergeTypeMetrics(round.results);
    return {
      clientCount: round.clientCount,
      flags: round.flags,
      aggregate: {
        ...round.aggregate,
        byMessageType,
      },
      clients: round.results.map((client) => ({
        clientId: client.clientId,
        error: client.error || null,
        sessionId: client.sessionId || "",
        connectMs: client.connectMs,
        welcomeMs: client.welcomeMs,
        durationMs: client.durationMs,
        suite: client.suite || null,
        byType: summarizeClientByType(client),
        driftMs: client.driftMs,
        pingRttMs: summarizeSamplesList(client.pingRttMs),
        motionDistance: client.motionDistance,
        eventsSent: client.eventsSent,
        handsSent: client.handsSent,
        videoFramesSent: client.videoFramesSent,
        snapshotsSent: client.snapshotsSent,
        finish: client.finish || null,
      })),
    };
  });

  const firstNoticeable = normalizedRounds.find((round) => round.flags?.noticeable);

  return {
    version: 1,
    generatedAt: new Date().toISOString(),
    meta,
    thresholds,
    summary: {
      rounds: normalizedRounds.length,
      lastSustainable,
      firstNoticeableClients: firstNoticeable?.clientCount ?? null,
    },
    series: buildTimeSeries(normalizedRounds),
    rounds: normalizedRounds,
  };
}

function summarizeSamplesList(samples) {
  if (!Array.isArray(samples) || !samples.length) {
    return { count: 0, p50: 0, p95: 0, max: 0 };
  }
  const sorted = [...samples].sort((left, right) => left - right);
  return {
    count: sorted.length,
    p50: sorted[Math.floor(sorted.length * 0.5)],
    p95: sorted[Math.floor(sorted.length * 0.95)],
    max: sorted.at(-1),
  };
}

function summarizeClientByType(client) {
  const summary = {};
  for (const [type, stats] of Object.entries(client.byType || {})) {
    summary[type] = {
      count: stats.driftMs?.length ?? stats.pingRttMs?.length ?? 0,
      drift: summarizeSamplesList(stats.driftMs),
      ping: summarizeSamplesList(stats.pingRttMs),
      ack: summarizeSamplesList(stats.ackRttMs),
    };
  }
  return summary;
}

export function writeLoadTestReport(report, outputDir) {
  const dir = resolve(outputDir);
  mkdirSync(dir, { recursive: true });

  const jsonPath = resolve(dir, "load-test-report.json");
  const htmlPath = resolve(dir, "load-test-report.html");

  writeFileSync(jsonPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  writeFileSync(htmlPath, renderReportHtml(report), "utf8");

  return { dir, jsonPath, htmlPath };
}

function renderReportHtml(report) {
  const data = JSON.stringify(report).replace(/</g, "\\u003c");
  const meta = report.meta;
  const summary = report.summary;
  const plannedDuration = meta.plannedDurationMs ?? meta.durationMs ?? 0;

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Solve load test — ${meta.mode}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    :root {
      color-scheme: light dark;
      --bg: #0f1115;
      --panel: #171a21;
      --text: #e8eaed;
      --muted: #9aa0a6;
      --grid: #2a2f3a;
      --good: #56d3a0;
      --warn: #ffb74d;
      --bad: #ff8a80;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font: 14px/1.5 system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header, main { max-width: 1180px; margin: 0 auto; padding: 24px 20px; }
    h1 { font-size: 1.35rem; margin: 0 0 8px; }
    .meta { color: var(--muted); font-size: 0.9rem; }
    .summary {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 10px;
      margin-top: 18px;
    }
    .metric {
      border: 1px solid var(--grid);
      border-radius: 8px;
      padding: 12px;
      background: var(--panel);
    }
    .metric span { display: block; color: var(--muted); font-size: 0.78rem; }
    .metric strong { display: block; margin-top: 4px; font-size: 1.1rem; }
    .grid {
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--grid);
      border-radius: 10px;
      padding: 16px;
    }
    .card h2 {
      margin: 0 0 12px;
      font-size: 0.95rem;
      font-weight: 600;
    }
    .chart-wrap { position: relative; height: 260px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    th, td { padding: 8px 10px; border-bottom: 1px solid var(--grid); text-align: left; }
    th { color: var(--muted); font-weight: 500; }
    td.num { font-variant-numeric: tabular-nums; text-align: right; }
    .tag {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 0.75rem;
      background: #243044;
      color: #8ab4ff;
    }
    .noticeable { color: var(--bad); }
  </style>
</head>
<body>
  <header>
    <h1>Solve load test report</h1>
    <p class="meta">
      ${meta.mode} · ${meta.targetUrl} · ${plannedDuration}ms/client ·
      generated ${new Date(report.generatedAt).toLocaleString()}
    </p>
    <p class="meta">
      Rounds: ${summary.rounds} · last sustainable: <strong>${summary.lastSustainable ?? "—"}</strong> clients
      ${summary.firstNoticeableClients ? ` · first degradation: <span class="noticeable">${summary.firstNoticeableClients} clients</span>` : ""}
    </p>
    <div class="summary">
      <div class="metric"><span>Planned events/client</span><strong>${meta.plannedEvents ?? "—"}</strong></div>
      <div class="metric"><span>Video frames/client</span><strong>${meta.plannedVideoFrames ?? 0}</strong></div>
      <div class="metric"><span>Finish verification</span><strong>${meta.submitFinish ? "enabled" : "disabled"}</strong></div>
      <div class="metric"><span>Mode</span><strong>${meta.fullSolveMode ? "full solve" : meta.mode}</strong></div>
      <div class="metric"><span>Thresholds</span><strong>${report.thresholds.driftThresholdMs}ms / ${report.thresholds.motionThreshold}</strong></div>
    </div>
  </header>
  <main>
    <div class="grid">
      <section class="card">
        <h2>Ping RTT (ms) vs concurrent clients</h2>
        <div class="chart-wrap"><canvas id="chartPing"></canvas></div>
      </section>
      <section class="card">
        <h2>Connect + welcome latency (ms)</h2>
        <div class="chart-wrap"><canvas id="chartWelcome"></canvas></div>
      </section>
      <section class="card">
        <h2>Schedule drift p95 (ms) by message type</h2>
        <div class="chart-wrap"><canvas id="chartDrift"></canvas></div>
      </section>
      <section class="card">
        <h2>Hand motion distance (min p50)</h2>
        <div class="chart-wrap"><canvas id="chartMotion"></canvas></div>
      </section>
      <section class="card">
        <h2>Run outcomes</h2>
        <div class="chart-wrap"><canvas id="chartOutcome"></canvas></div>
      </section>
    </div>

    <section class="card" style="margin-top: 16px;">
      <h2>Per-round metrics by message type</h2>
      <div style="overflow-x: auto;">
        <table id="roundsTable"></table>
      </div>
    </section>
  </main>
  <script>
    const report = ${data};
    const series = report.series;
    const labels = series.labels.map((n) => String(n));

    const colors = {
      blue: "#5b9cff",
      cyan: "#58d6ff",
      green: "#56d3a0",
      amber: "#ffb74d",
      red: "#ff8a80",
      violet: "#9c7cff",
    };

    function line(label, data, color) {
      return {
        label,
        data,
        borderColor: color,
        backgroundColor: color,
        tension: 0.2,
        pointRadius: 2,
        spanGaps: true,
      };
    }

    const chartDefaults = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#c8ccd0" } } },
      scales: {
        x: {
          title: { display: true, text: "Concurrent clients", color: "#9aa0a6" },
          ticks: { color: "#9aa0a6" },
          grid: { color: "#2a2f3a" },
        },
        y: {
          title: { display: true, text: "Latency (ms)", color: "#9aa0a6" },
          ticks: { color: "#9aa0a6" },
          grid: { color: "#2a2f3a" },
        },
      },
    };

    function renderLineChart(id, datasets, yTitle = "Latency (ms)") {
      new Chart(document.getElementById(id), {
        type: "line",
        data: { labels, datasets },
        options: {
          ...chartDefaults,
          scales: {
            ...chartDefaults.scales,
            y: {
              ...chartDefaults.scales.y,
              title: { display: true, text: yTitle, color: "#9aa0a6" },
            },
          },
        },
      });
    }

    renderLineChart("chartPing", [
      line("Ping p50", series.pingP50, colors.blue),
      line("Ping p95", series.pingP95, colors.violet),
    ]);

    renderLineChart("chartWelcome", [
      line("Welcome p95", series.welcomeP95, colors.blue),
      line("Connect p95", series.connectP95, colors.green),
    ]);

    renderLineChart("chartDrift", [
      line("hands drift p95", series.handsDriftP95, colors.blue),
      line("hands drift p50", series.handsDriftP50, colors.cyan),
      line("video frame drift p95", series.videoDriftP95, colors.green),
      line("snapshot response drift p95", series.snapshotDriftP95, colors.violet),
      line("flap drift p95", series.flapDriftP95, colors.amber),
      line("aggregate drift p95 max", series.driftP95Max, colors.red),
    ]);

    renderLineChart("chartMotion", [
      line("Motion p50 min", series.motionP50Min, colors.green),
    ], "Motion distance");

    renderLineChart("chartOutcome", [
      line("Finish submitted", series.finished, colors.cyan),
      line("Finish valid", series.finishValid, colors.green),
      line("Video frames sent", series.videoFramesSent, colors.violet),
      line("Snapshots sent", series.snapshotsSent, colors.amber),
      line("Failures", series.failed, colors.red),
    ], "Clients");

    const types = ["ping", "welcome", "connect", "restart", "hands", "video_frame", "snapshot", "flap", "finish"];
    const table = document.getElementById("roundsTable");
    const head = document.createElement("thead");
    head.innerHTML = "<tr><th>Clients</th><th>Status</th>" +
      types.map((t) => "<th>" + t + " p95</th>").join("") +
      "<th>Finish</th><th>Failed</th></tr>";
    table.appendChild(head);
    const body = document.createElement("tbody");
    for (const round of report.rounds) {
      const row = document.createElement("tr");
      const status = round.flags?.noticeable
        ? '<span class="tag noticeable">degraded</span>'
        : '<span class="tag">ok</span>';
      const cells = types.map((type) => {
        const m = round.aggregate.byMessageType?.[type];
        const ping = m?.pingRttMs?.p95;
        const drift = m?.driftMs?.p95;
        const lat = m?.latencyMs?.p95;
        const ack = m?.ackRttMs?.p95;
        const value = ping ?? drift ?? lat ?? ack;
        return "<td class=\\"num\\">" + (value != null ? value.toFixed(1) : "—") + "</td>";
      }).join("");
      row.innerHTML = "<td class=\\"num\\">" + round.clientCount + "</td><td>" + status + "</td>" +
        cells +
        "<td class=\\"num\\">" + (round.aggregate.finishValid || 0) + "/" + (round.aggregate.finished || 0) + "</td>" +
        "<td class=\\"num\\">" + (round.aggregate.failed || 0) + "</td>";
      body.appendChild(row);
    }
    table.appendChild(body);
  </script>
</body>
</html>`;
}
