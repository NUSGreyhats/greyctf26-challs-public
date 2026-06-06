export function percentile(sorted, p) {
  if (!sorted.length) {
    return 0;
  }
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return sorted[index];
}

export function summarizeSamples(samples) {
  if (!samples.length) {
    return { count: 0, min: 0, p50: 0, p95: 0, max: 0, mean: 0 };
  }
  const sorted = [...samples].sort((left, right) => left - right);
  const sum = sorted.reduce((total, value) => total + value, 0);
  return {
    count: sorted.length,
    min: sorted[0],
    p50: percentile(sorted, 50),
    p95: percentile(sorted, 95),
    max: sorted.at(-1),
    mean: sum / sorted.length,
  };
}

export function mergeTypeMetrics(clientResults) {
  const buckets = new Map();

  const add = (type, field, value) => {
    if (!Number.isFinite(value)) {
      return;
    }
    if (!buckets.has(type)) {
      buckets.set(type, {});
    }
    const row = buckets.get(type);
    if (!row[field]) {
      row[field] = [];
    }
    row[field].push(value);
  };

  for (const client of clientResults) {
    if (client.error) {
      continue;
    }

    add("connect", "latencyMs", client.connectMs);
    add("welcome", "latencyMs", client.welcomeMs);

    for (const [type, stats] of Object.entries(client.byType || {})) {
      for (const sample of stats.driftMs || []) {
        add(type, "driftMs", sample);
      }
      for (const sample of stats.pingRttMs || []) {
        add(type, "pingRttMs", sample);
      }
      for (const sample of stats.ackRttMs || []) {
        add(type, "ackRttMs", sample);
      }
    }

    for (const sample of client.pingRttMs || []) {
      add("ping", "pingRttMs", sample);
    }
  }

  const byMessageType = {};
  for (const [type, fields] of buckets.entries()) {
    byMessageType[type] = {};
    for (const [field, samples] of Object.entries(fields)) {
      byMessageType[type][field] = summarizeSamples(samples);
    }
  }

  return byMessageType;
}

export function buildTimeSeries(rounds) {
  const labels = rounds.map((round) => round.clientCount);

  const pick = (type, field, stat) =>
    rounds.map((round) => round.aggregate?.byMessageType?.[type]?.[field]?.[stat] ?? null);

  return {
    labels,
    pingP50: pick("ping", "pingRttMs", "p50"),
    pingP95: pick("ping", "pingRttMs", "p95"),
    welcomeP95: pick("welcome", "latencyMs", "p95"),
    connectP95: pick("connect", "latencyMs", "p95"),
    handsDriftP95: pick("hands", "driftMs", "p95"),
    handsDriftP50: pick("hands", "driftMs", "p50"),
    videoDriftP95: pick("video_frame", "driftMs", "p95"),
    snapshotDriftP95: pick("snapshot", "driftMs", "p95"),
    flapDriftP95: pick("flap", "driftMs", "p95"),
    restartDriftP95: pick("restart", "driftMs", "p95"),
    finishRttP95: pick("finish", "ackRttMs", "p95"),
    driftP95Max: rounds.map((round) => round.aggregate?.driftP95Max ?? null),
    motionP50Min: rounds.map((round) => round.aggregate?.motionP50Min ?? null),
    finishValid: rounds.map((round) => round.aggregate?.finishValid ?? 0),
    finished: rounds.map((round) => round.aggregate?.finished ?? 0),
    videoFramesSent: rounds.map((round) => round.aggregate?.videoFramesSent ?? 0),
    snapshotsSent: rounds.map((round) => round.aggregate?.snapshotsSent ?? 0),
    failed: rounds.map((round) => round.aggregate?.failed ?? 0),
  };
}
