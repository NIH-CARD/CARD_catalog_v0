#!/usr/bin/env -S npx tsx
// Precomputes a full-catalog, per-column baseline (value counts for
// categorical columns, mean/variance for numeric ones) for every column
// tableRegistry.ts declares for each table Connections can merge - including
// columns the Connections merge-UI itself never surfaces as mergeable (e.g.
// Code Repositories' FAIR Score), since those still belong in the AI
// Analysis prompt as contrastive context.
//
// Run via tsx (not plain node) specifically so this can import
// tableRegistry.ts directly - the single source of truth for which columns
// each table actually has and how to split a multivalue one (comma vs.
// semicolon vs. single-value) - rather than re-guessing that from raw TSV
// headers, which also silently pulled in a few malformed upstream columns
// (e.g. pub_grants.tsv's stray "PI"/"Union."/"ID" columns) that
// tableRegistry.ts never declares.
//
// Static and build-time by design: computed once here from public/data/*.tsv
// (run after `npm run sync-data`), not recomputed client-side per keystroke.
// Rerun whenever the pipeline emits new tables/final/ output.
import { readFileSync, writeFileSync, existsSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";
import Papa from "papaparse";
import { TABLE_REGISTRY } from "../src/lib/tableRegistry.ts";
import { publicationYearFrom } from "../src/lib/loadPublications.ts";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DATA_DIR = join(__dirname, "..", "public", "data");
const OUT_PATH = join(DATA_DIR, "connections_stats.json");

// Table name (as tableRegistry.ts/connectionsGraph.ts use it) -> TSV file in
// public/data/. SciLite uses the full mention-level table (not the small
// per-PMC aggregate Connections loads client-side) since this script runs at
// build time, not in the browser - size isn't a constraint here.
const TSV_FILE = {
  Publications: "publications.tsv",
  Resources: "resources.tsv",
  "Code Repositories": "code_repos.tsv",
  Datasets: "pub_datasets.tsv",
  "Supplementary Files": "pub_supplementary.tsv",
  Grants: "pub_grants.tsv",
  Software: "pub_software.tsv",
  Models: "pub_models.tsv",
  "SciLite Annotations": "scilite_annotations.tsv",
  "Human Cellular Models": "cellular_models.tsv",
};

const NUMERIC_RE = /^-?\d+(\.\d+)?$/;
const FREE_TEXT_AVG_LEN = 150;
const FREE_TEXT_DISTINCT_RATIO = 0.8;
const FREE_TEXT_MIN_ROWS = 20;
const TOP_K_STORED = 20;

function loadRows(path) {
  const text = readFileSync(path, "utf-8");
  return Papa.parse(text, { header: true, delimiter: "\t", skipEmptyLines: true }).data;
}

/**
 * `delimiter` is undefined for a single-value column - it is never split,
 * even if a raw value happens to contain the character elsewhere, since
 * tableRegistry.ts's own multivalue/delimiter metadata (the same source
 * every join/facet in this app already trusts) is the only thing that
 * decides whether a column is multivalue.
 */
function summarizeColumn(rawValues, delimiter) {
  const nonEmpty = rawValues.map((v) => (v ?? "").trim()).filter(Boolean);
  if (nonEmpty.length === 0) return { kind: "skipped", reason: "no values" };

  const avgLen = nonEmpty.reduce((s, v) => s + v.length, 0) / nonEmpty.length;

  if (!delimiter) {
    const numericCount = nonEmpty.filter((v) => NUMERIC_RE.test(v)).length;
    if (numericCount / nonEmpty.length >= 0.9) {
      const nums = nonEmpty.filter((v) => NUMERIC_RE.test(v)).map(Number);
      const mean = nums.reduce((s, n) => s + n, 0) / nums.length;
      const variance = nums.reduce((s, n) => s + (n - mean) ** 2, 0) / nums.length;
      return { kind: "numeric", count: nums.length, mean, variance };
    }
  }

  const values = delimiter ? nonEmpty.flatMap((v) => v.split(delimiter).map((s) => s.trim()).filter(Boolean)) : nonEmpty;
  const distinct = new Set(values);

  if (avgLen > FREE_TEXT_AVG_LEN || (nonEmpty.length > FREE_TEXT_MIN_ROWS && distinct.size / values.length > FREE_TEXT_DISTINCT_RATIO)) {
    return { kind: "skipped", reason: "free text / near-unique" };
  }

  const counts = new Map();
  for (const v of values) counts.set(v, (counts.get(v) ?? 0) + 1);
  const top = Array.from(counts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, TOP_K_STORED);

  return { kind: "categorical", distinct: distinct.size, top };
}

const stats = {};
for (const table of TABLE_REGISTRY) {
  const file = TSV_FILE[table.name];
  if (!file) continue;
  const path = join(DATA_DIR, file);
  if (!existsSync(path)) {
    console.warn(`WARN: ${path} not found - skipping ${table.name}`);
    continue;
  }
  const rows = loadRows(path);
  // Publication Year isn't a real TSV column - derive it exactly the way the
  // client does, so the baseline can actually be contrasted against the
  // subset summary's own Publication Year distribution.
  if (table.name === "Publications") {
    for (const row of rows) row["Publication Year"] = publicationYearFrom(row["Publication Date"]);
  }
  const columns = {};
  for (const col of table.columns) {
    const delimiter = col.multivalue ? (col.delimiter ?? ";") : undefined;
    columns[col.field] = summarizeColumn(rows.map((r) => r[col.field]), delimiter);
  }
  stats[table.name] = { rowCount: rows.length, columns };
  console.log(`  ${table.name}: ${rows.length.toLocaleString()} rows, ${Object.keys(columns).length} columns`);
}

writeFileSync(OUT_PATH, JSON.stringify(stats));
console.log(`Wrote ${OUT_PATH}`);