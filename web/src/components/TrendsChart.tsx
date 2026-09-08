import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { GraphPublication } from "../lib/paperGraph";

type Granularity = "month" | "quarter" | "year";
type BreakdownField = "none" | "Resource Name";
type ChartType = "bar" | "line";
type YMeasure =
  | "count"
  | "pct_of_total"
  | "pct_of_period"
  | "completeness_avg"
  | "completeness_median";

const PALETTE = [
  "#6366f1", "#10b981", "#f59e0b", "#ef4444", "#3b82f6",
  "#8b5cf6", "#14b8a6", "#f97316", "#ec4899", "#84cc16",
  "#64748b",
];

const MAX_SERIES = 10;

const Y_LABELS: Record<YMeasure, string> = {
  count: "Papers",
  pct_of_total: "% of filtered total",
  pct_of_period: "% of catalog in period",
  completeness_avg: "Avg completeness (%)",
  completeness_median: "Median completeness (%)",
};

const IS_PERCENT: Record<YMeasure, boolean> = {
  count: false,
  pct_of_total: true,
  pct_of_period: true,
  completeness_avg: true,
  completeness_median: true,
};

function mean(values: number[]): number {
  if (values.length === 0) return 0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

function parsePeriod(dateStr: string, gran: Granularity): string | null {
  if (!dateStr?.trim()) return null;
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return null;
  const y = d.getFullYear();
  if (gran === "year") return `${y}`;
  if (gran === "quarter") return `${y} Q${Math.floor(d.getMonth() / 3) + 1}`;
  return dateStr;
}

function periodSortKey(period: string, gran: Granularity): number {
  if (gran === "year") return Number(period) * 100;
  if (gran === "quarter") {
    const [y, q] = period.split(" Q");
    return Number(y) * 10 + Number(q);
  }
  return new Date(period).getTime();
}

function buildChartData(
  rows: GraphPublication[],
  allRows: GraphPublication[],
  gran: Granularity,
  breakBy: BreakdownField,
  measure: YMeasure,
): { data: Record<string, string | number>[]; keys: string[]; multivalueWarning: boolean } {
  const isCompleteness = measure === "completeness_avg" || measure === "completeness_median";
  const aggregateFn = measure === "completeness_avg" ? mean : median;

  // Pre-compute full catalog counts per period (used as denominator for pct_of_period)
  const catalogPeriodCounts = new Map<string, number>();
  if (measure === "pct_of_period") {
    for (const row of allRows) {
      const p = parsePeriod(row["Publication Date"], gran);
      if (p) catalogPeriodCounts.set(p, (catalogPeriodCounts.get(p) ?? 0) + 1);
    }
  }

  // Accumulate: period → series → number[] (for completeness) or count (for others)
  const matrix = new Map<string, Map<string, number[]>>();
  const totals = new Map<string, number>(); // series → total count (for top-N ranking)
  let totalRows = 0;

  const delim = ";";

  for (const row of rows) {
    const p = parsePeriod(row["Publication Date"], gran);
    if (!p) continue;
    totalRows++;

    const completenessVal = parseFloat(row["Data Completeness"] ?? "");
    const raw = (row as unknown as Record<string, string>)[breakBy] ?? "";
    const series: string[] =
      breakBy === "none"
        ? ["Papers"]
        : breakBy === "Resource Name"
          ? [raw || "(none)"]
          : raw.split(delim).map((v) => v.trim()).filter(Boolean);
    const effective = series.length > 0 ? series : ["(none)"];

    const periodMap = matrix.get(p) ?? new Map<string, number[]>();
    for (const s of effective) {
      const arr = periodMap.get(s) ?? [];
      arr.push(isCompleteness && !isNaN(completenessVal) ? completenessVal : 1);
      periodMap.set(s, arr);
      totals.set(s, (totals.get(s) ?? 0) + 1);
    }
    matrix.set(p, periodMap);
  }

  // Top-N series by count
  const allSeriesKeys = [...totals.entries()].sort((a, b) => b[1] - a[1]);
  const topKeys = allSeriesKeys.slice(0, MAX_SERIES).map(([k]) => k);
  const hasOther = allSeriesKeys.length > MAX_SERIES && !isCompleteness;

  const sorted = [...matrix.keys()].sort(
    (a, b) => periodSortKey(a, gran) - periodSortKey(b, gran),
  );

  // First pass: raw aggregated values
  const rawData = sorted.map((p) => {
    const pm = matrix.get(p)!;
    const entry: Record<string, string | number> = { period: p };
    for (const k of topKeys) {
      const vals = pm.get(k) ?? [];
      entry[k] = isCompleteness ? aggregateFn(vals) : vals.length;
    }
    if (hasOther) {
      let other = 0;
      for (const [k, vals] of pm) if (!topKeys.includes(k)) other += vals.length;
      entry["Other"] = other;
    }
    return entry;
  });

  const keys = hasOther ? [...topKeys, "Other"] : topKeys;

  // Post-process percentages
  if (measure === "pct_of_total") {
    for (const entry of rawData) {
      for (const k of keys) {
        entry[k] = totalRows > 0 ? +((entry[k] as number / totalRows) * 100).toFixed(2) : 0;
      }
    }
  } else if (measure === "pct_of_period") {
    for (const entry of rawData) {
      const catalogTotal = catalogPeriodCounts.get(entry.period as string) ?? 0;
      for (const k of keys) {
        entry[k] = catalogTotal > 0 ? +((entry[k] as number / catalogTotal) * 100).toFixed(2) : 0;
      }
    }
  } else if (isCompleteness) {
    for (const entry of rawData) {
      for (const k of keys) {
        entry[k] = +((entry[k] as number)).toFixed(1);
      }
    }
  }

  const multivalueWarning = breakBy !== "none" && breakBy !== "Resource Name";

  return { data: rawData, keys, multivalueWarning };
}

export interface TrendsFilterProps {
  query: string;
  selections: Record<string, Set<string>>;
  totalSelected: number;
  fieldLabels: Record<string, string>;
  onRemoveFacetValue: (field: string, value: string) => void;
  onClearQuery: () => void;
  onClearAll: () => void;
}

interface Props {
  rows: GraphPublication[];
  allRows: GraphPublication[];
  filters?: TrendsFilterProps;
}

function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
  disabled,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <div>
      <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600 mb-1">
        {label}
      </label>
      <div className={`inline-flex rounded border overflow-hidden text-sm ${disabled ? "border-slate-100 opacity-40 pointer-events-none" : "border-slate-200"}`}>
        {options.map((o) => (
          <button
            key={o.value}
            onClick={() => onChange(o.value)}
            disabled={disabled}
            className={
              "px-3 py-1.5 " +
              (value === o.value
                ? "bg-accent text-white"
                : "bg-white text-slate-700 hover:bg-slate-100")
            }
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function TrendsChart({ rows, allRows, filters }: Props) {
  const [gran, setGran] = useState<Granularity>("month");
  const [breakBy, setBreakBy] = useState<BreakdownField>("none");
  const [chartType, setChartType] = useState<ChartType>("bar");
  const [measure, setMeasure] = useState<YMeasure>("count");

  const forceStacked = false;

  const { data, keys, multivalueWarning } = useMemo(
    () => buildChartData(rows, allRows, gran, breakBy, measure),
    [rows, allRows, gran, breakBy, measure],
  );

  const isPercent = IS_PERCENT[measure];
  const yLabel = Y_LABELS[measure];
  const tickFormatter = (v: number) => (isPercent ? `${v}%` : String(v));
  const tooltipFormatter = (value: number) =>
    isPercent ? `${value.toFixed(1)}%` : String(value);
  const yDomain: [number, number] | undefined = measure === "pct_of_period" ? [0, 100] : undefined;
  const actuallyStacked = chartType === "bar" && (forceStacked || keys.length > 1);

  return (
    <div className="space-y-3">
      <div className="border border-slate-200 rounded bg-white p-3 flex flex-wrap items-end gap-4 text-sm">
        <SegmentedControl
          label="Granularity"
          value={gran}
          onChange={setGran}
          options={[
            { value: "month", label: "Month" },
            { value: "quarter", label: "Quarter" },
            { value: "year", label: "Year" },
          ]}
        />

        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600 mb-1">
            Break down by
          </label>
          <select
            value={breakBy}
            onChange={(e) => setBreakBy(e.target.value as BreakdownField)}
            className="px-2 py-1.5 border border-slate-300 rounded text-sm bg-white text-slate-700"
          >
            <option value="none">None — total count</option>
            <option value="Resource Name">Study</option>
          </select>
        </div>

        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600 mb-1">
            Measure (Y)
          </label>
          <select
            value={measure}
            onChange={(e) => setMeasure(e.target.value as YMeasure)}
            className="px-2 py-1.5 border border-slate-300 rounded text-sm bg-white text-slate-700"
          >
            <option value="count">Count</option>
            <option value="pct_of_total">% of filtered total</option>
            <option value="pct_of_period">% of catalog in period</option>
            <option value="completeness_avg">Avg Data Completeness</option>
            <option value="completeness_median">Median Data Completeness</option>
          </select>
        </div>

        <SegmentedControl
          label="Chart type"
          value={chartType}
          onChange={setChartType}
          disabled={forceStacked}
          options={[
            { value: "bar", label: "Bar" },
            { value: "line", label: "Line" },
          ]}
        />

        {filters && (filters.query || filters.totalSelected > 0) && (
          <div className="flex-1 min-w-[200px]">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                Active filters
              </span>
              <button
                className="text-xs text-accent hover:underline"
                onClick={filters.onClearAll}
              >
                clear all ({filters.totalSelected + (filters.query ? 1 : 0)})
              </button>
            </div>
            <div className="flex flex-wrap gap-1">
              {filters.query && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-xs border border-slate-200">
                  <span className="text-slate-400">search:</span> {filters.query}
                  <button
                    className="ml-0.5 text-slate-400 hover:text-slate-700"
                    onClick={filters.onClearQuery}
                    aria-label="Remove search filter"
                  >
                    ×
                  </button>
                </span>
              )}
              {Object.entries(filters.selections).flatMap(([field, values]) =>
                [...values].map((v) => (
                  <span
                    key={`${field}:${v}`}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 text-xs border border-indigo-100"
                  >
                    <span className="text-indigo-400">
                      {filters.fieldLabels[field] ?? field}:
                    </span>{" "}
                    {v}
                    <button
                      className="ml-0.5 text-indigo-300 hover:text-indigo-700"
                      onClick={() => filters.onRemoveFacetValue(field, v)}
                      aria-label={`Remove ${v}`}
                    >
                      ×
                    </button>
                  </span>
                )),
              )}
            </div>
          </div>
        )}
      </div>

      {multivalueWarning && (
        <p className="text-xs text-slate-500">
          Papers with multiple values in this field are counted once per value — series totals may exceed paper count.
        </p>
      )}

      {data.length === 0 && (
        <p className="py-10 text-center text-sm text-slate-500">
          No dated publications in the current filter.
        </p>
      )}

      {data.length > 0 && chartType === "bar" ? (
        <ResponsiveContainer width="100%" height={380}>
          <BarChart data={data} margin={{ top: 4, right: 16, bottom: 64, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
            <XAxis
              dataKey="period"
              tick={{ fontSize: 11, fill: "#64748b" }}
              angle={-40}
              textAnchor="end"
              interval="preserveStartEnd"
            />
            <YAxis
              allowDecimals={isPercent}
              tickFormatter={tickFormatter}
              domain={yDomain}
              tick={{ fontSize: 11, fill: "#64748b" }}
              width={isPercent ? 48 : 36}
              label={
                keys.length === 1
                  ? { value: yLabel, angle: -90, position: "insideLeft", offset: 12, style: { fontSize: 10, fill: "#94a3b8" } }
                  : undefined
              }
            />
            <Tooltip
              contentStyle={{ fontSize: 12, borderColor: "#e2e8f0", borderRadius: 6 }}
              cursor={{ fill: "#f1f5f9" }}
              formatter={(value) => [tooltipFormatter(value as number), ""]}
            />
            {keys.length > 1 && (
              <Legend
                wrapperStyle={{ fontSize: 11, paddingTop: 12 }}
                iconType="square"
                iconSize={10}
              />
            )}
            {keys.map((k, i) => (
              <Bar
                key={k}
                dataKey={k}
                stackId={actuallyStacked ? "a" : undefined}
                fill={PALETTE[i % PALETTE.length]}
                radius={actuallyStacked ? undefined : [2, 2, 0, 0]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      ) : data.length > 0 ? (
        <ResponsiveContainer width="100%" height={380}>
          <LineChart data={data} margin={{ top: 4, right: 16, bottom: 64, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
            <XAxis
              dataKey="period"
              tick={{ fontSize: 11, fill: "#64748b" }}
              angle={-40}
              textAnchor="end"
              interval="preserveStartEnd"
            />
            <YAxis
              allowDecimals={isPercent}
              tickFormatter={tickFormatter}
              domain={yDomain}
              tick={{ fontSize: 11, fill: "#64748b" }}
              width={isPercent ? 48 : 36}
              label={
                keys.length === 1
                  ? { value: yLabel, angle: -90, position: "insideLeft", offset: 12, style: { fontSize: 10, fill: "#94a3b8" } }
                  : undefined
              }
            />
            <Tooltip
              contentStyle={{ fontSize: 12, borderColor: "#e2e8f0", borderRadius: 6 }}
              formatter={(value) => [tooltipFormatter(value as number), ""]}
            />
            {keys.length > 1 && (
              <Legend
                wrapperStyle={{ fontSize: 11, paddingTop: 12 }}
                iconType="plainline"
                iconSize={16}
              />
            )}
            {keys.map((k, i) => (
              <Line
                key={k}
                dataKey={k}
                type="monotone"
                stroke={PALETTE[i % PALETTE.length]}
                dot={false}
                strokeWidth={2}
                activeDot={{ r: 4 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      ) : null}
    </div>
  );
}
