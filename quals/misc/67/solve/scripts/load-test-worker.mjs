#!/usr/bin/env node
/**
 * Forked worker for solve load tests. Config via LOAD_TEST_CONFIG env (JSON).
 */
import { runLoadTestClient } from "./lib/load-test-client.mjs";
import { prepareLoadTestPlan } from "./lib/load-test-plan.mjs";

function readConfig() {
  const raw = process.env.LOAD_TEST_CONFIG;
  if (!raw) {
    throw new Error("LOAD_TEST_CONFIG is required");
  }
  return JSON.parse(raw);
}

async function main() {
  const config = readConfig();
  const plan = await prepareLoadTestPlan(config);

  const result = await runLoadTestClient({
    clientId: config.clientId,
    mode: config.mode,
    targetUrl: config.targetUrl,
    events: plan.events,
    durationMs: plan.durationMs,
    submitFinish: config.submitFinish ?? false,
    claimScore: plan.claimScore,
    suite: plan.suite,
  });

  if (process.send) {
    process.send({ type: "result", result }, () => process.exit(0));
    return;
  }

  process.stdout.write(`${JSON.stringify(result)}\n`);
}

main().catch((error) => {
  const payload = {
    clientId: Number(process.env.LOAD_TEST_CLIENT_ID || "0"),
    error: error.message,
  };
  if (process.send) {
    process.send({ type: "error", error: payload });
  } else {
    process.stderr.write(`${error.stack || error.message}\n`);
    process.exitCode = 1;
  }
});
