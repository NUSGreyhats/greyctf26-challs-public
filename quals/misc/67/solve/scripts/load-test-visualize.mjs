#!/usr/bin/env node
/**
 * Regenerate the HTML chart report from a saved JSON report.
 *
 *   node solve/scripts/load-test-visualize.mjs solve/reports/latest/load-test-report.json
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { writeLoadTestReport } from "./lib/load-test-report.mjs";

const inputPath = resolve(process.argv[2] || "solve/reports/latest/load-test-report.json");
const report = JSON.parse(readFileSync(inputPath, "utf8"));
const outputDir = dirname(inputPath);

const paths = writeLoadTestReport(report, outputDir);
console.log(`Wrote ${paths.htmlPath}`);
