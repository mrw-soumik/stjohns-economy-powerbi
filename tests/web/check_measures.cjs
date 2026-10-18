// Compare the web measures (docs/assets/js/measures.js) with the expected results of
// the DAX check query (powerbi/check-query-expected.csv). Run: node tests/web/check_measures.cjs
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const root = path.resolve(__dirname, "..", "..");
const sandbox = { window: {} };
vm.runInNewContext(fs.readFileSync(path.join(root, "docs/data/dashboard.js"), "utf8"), sandbox);
const data = sandbox.window.DASHBOARD;
const SJM = require(path.join(root, "docs/assets/js/measures.js"));
const M = SJM.create(data);

function parseCsv(text) {
  const lines = text.trim().split("\n");
  const header = lines[0].split(",");
  return lines.slice(1).map((line) => {
    const cells = [];
    let cur = "", quoted = false;
    for (const ch of line) {
      if (ch === '"') quoted = !quoted;
      else if (ch === "," && !quoted) { cells.push(cur); cur = ""; }
      else cur += ch;
    }
    cells.push(cur);
    return Object.fromEntries(header.map((h, i) => [h, cells[i]]));
  });
}

const geoByShort = Object.fromEntries(data.geographies.map((g) => [g.short, g.code]));
const rows = parseCsv(fs.readFileSync(path.join(root, "powerbi/check-query-expected.csv"), "utf8"));
const failures = [];
const close = (a, b, tol) => (a === null && b === null) || (a !== null && b !== null && Math.abs(a - b) <= tol);
const num = (s) => (s === "" || s === undefined ? null : Number(s));

for (const row of rows) {
  const ind = row.IndicatorCode, geo = geoByShort[row.ShortName];
  const meta = M.meta(ind);
  const latest = M.latestDate(ind, geo, null);
  const checks = [
    ["Latest period", SJM.periodLabel(latest, meta.frequency), row["Latest period"]],
    ["Latest value", M.valueAt(ind, geo, latest), num(row["Latest value"]), 1e-9],
    ["YoY headline change", M.headline(ind, geo, null), num(row["YoY headline change"]), 5e-5],
    ["Gap vs Canada", geo === "CA" ? 0 : M.gapVsCanada(ind, geo, null), num(row["Gap vs Canada"]), 5e-5],
    ["Rolling 12-month total", meta.aggregation === "Sum" ? M.rollingTotal(ind, geo, null).value : null, num(row["Rolling 12-month total"]), 1e-9],
    ["Assessment", M.yoyAssessment(ind, geo, null), row.Assessment || null],
  ];
  for (const [name, got, want, tol] of checks) {
    const ok = tol === undefined ? got === want : close(got, want, tol);
    if (!ok) failures.push(`${ind} ${row.ShortName} ${name}: web=${got} expected=${want}`);
  }
}

// Spot checks of labels and the per-capita measure against values verified in Python.
const spot = [
  [M.gapDelta("CPI_ALL", "SJ", null).text, "1.3 pts above Canada (12-month change)"],
  [M.yoyDelta("LFS_UR", "SJ", null).text, "▼ −0.4 pts from Sep 2025 (not significant)"],
  [M.rollingDelta("BP_UNITS", "SJ", null).text, "▲ +22.2% vs previous 12 months (favourable)"],
  [M.perCapita("SJ", null).value.toFixed(2), "6.48"],
  [M.perCapita("CA", null).value.toFixed(2), "7.16"],
  [M.perCapitaDelta("SJ", null).text, "0.7 below Canada (7.2)"],
];
for (const [got, want] of spot) if (got !== want) failures.push(`label: got "${got}" expected "${want}"`);

if (failures.length) {
  console.error(`${failures.length} mismatch(es):\n` + failures.join("\n"));
  process.exit(1);
}
console.log(`OK: ${rows.length} series rows and ${spot.length} spot checks match`);
