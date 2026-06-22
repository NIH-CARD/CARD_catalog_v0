# Trends Chart — Configurable Y-axis

## Status: implemented

## Context

`web/src/components/TrendsChart.tsx` currently hardwires Y to `COUNT(*)`.
The goal is to make Y configurable across three categories: counts, relative counts, and percentiles of a numeric field.

---

## New type: `YMeasure`

```ts
type YMeasure =
  | "count"               // COUNT(*) — current behaviour
  | "pct_of_total"        // each bucket as % of all filtered papers
  | "pct_of_period"       // each bucket as % of full catalog for that same period
  | "completeness_avg"    // AVG(Data Completeness) per period
  | "completeness_median" // MEDIAN(Data Completeness) per period
```

`pct_of_total` and `pct_of_period` cover "relative counts".
`completeness_avg` / `completeness_median` cover "percentiles" — `Data Completeness` is the only numeric field in the schema for now.
Percentile bands (P25–P75 shaded area) are a follow-up requiring `ComposedChart`.

### `pct_of_period` semantics (corrected)

Denominator is **full unfiltered catalog count for that period**, not the filtered period sum.
Answers: "of all papers published in this period, what fraction matches my filter?"
Works with or without a breakdown. Requires `allRows` passed as a prop.

---

## Changes to `buildChartData`

Signature: `buildChartData(rows, allRows, gran, breakBy, measure)`.
Grouping logic (by period, by breakdown) stays unchanged — only accumulation and post-processing change per cell.

| Measure | Accumulate per `(period, series)` | Post-process |
|---|---|---|
| `count` | `+= 1` | none |
| `pct_of_total` | `+= 1` | divide every cell by total filtered row count × 100 |
| `pct_of_period` | `+= 1` | divide every cell by `catalogPeriodCounts.get(period)` × 100 |
| `completeness_avg` | push `parseFloat(row["Data Completeness"])` | `mean(values)` per cell |
| `completeness_median` | push `parseFloat(row["Data Completeness"])` | `median(values)` per cell |

---

## Chart rendering changes

| What | Change |
|---|---|
| Y-axis `tickFormatter` | append `%` for all non-count measures |
| Tooltip `formatter` | same suffix + round to 1 decimal |
| `allowDecimals` | `true` for everything except `count` |
| Y-axis `domain` | `[0, 100]` for `pct_of_period`, auto otherwise |

---

## UI control

A `"Measure"` dropdown inserted between "Break down by" and "Chart type" in the controls bar:

```
Measure: [Count ▼]
  Count
  % of filtered total
  % of catalog in period
  Avg Data Completeness
  Median Data Completeness
```

---

## Files touched

| File | Change |
|---|---|
| `web/src/components/TrendsChart.tsx` | All of the above — self-contained |
| `web/src/pages/PublicationsPage.tsx` | Pass `allRows={allAugmented}` to `TrendsChart` |

---

## Follow-up: AlaSQL expression input

**Status: planned, not implemented — keeping select menu for now.**

Replace the `<select>` with a free-text SQL expression input powered by **AlaSQL**,
which runs SQL aggregates directly against JavaScript arrays (no server).

### How it would work

User types a SQL aggregate expression. Internally:

```js
const expr = raw
  .replace(/\bCATALOG\b/g, String(catalogPeriodCount))  // full catalog count for this period
  .replace(/\bTOTAL\b/g, String(totalFilteredCount));    // total filtered count (scalar)

alasql(`SELECT ${expr} AS __v FROM ?`, [rows])[0].__v
```

`rows` is the already-filtered+grouped array for the (period, series) cell.
`CATALOG` and `TOTAL` are the only references to unfiltered data — injected as numbers, not queryable arrays.

### Example expressions

```sql
COUNT(*)
COUNT(*) / CATALOG * 100
COUNT(*) / TOTAL * 100
AVG([Data Completeness])
MEDIAN([Data Completeness])
SUM([Data Completeness]) / COUNT(*) * 100
```

Column names with spaces use bracket notation: `[Data Completeness]`.

### UI

Monospace text input + inline valid/error state. Quick-insert buttons for the five common expressions. `isPercent` detected heuristically (expression ends in `* 100`).

### Files touched (when implemented)

| File | Change |
|---|---|
| `web/src/components/TrendsChart.tsx` | Replace select with text input; call `alasql` per cell; remove manual aggregation |
| `web/package.json` | Add `alasql` (~500 KB gzipped) |

---

## Other follow-ups (out of scope)

- Percentile band chart (P25/median/P75) using Recharts `ComposedChart` + `Area`
- Additional numeric measures if new fields are added to the schema
- X-axis as a non-time categorical field (turns Trends into a general bar explorer)
- Querying `allRows` directly in AlaSQL (would require passing it as a second table parameter)
