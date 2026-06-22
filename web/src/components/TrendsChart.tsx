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
type BreakdownField = "none" | "Resource Name" | "Diseases Included" | "Coarse Data Modality";
type ChartType = "bar" | "line";

const PALETTE = [
  "#6366f1", "#10b981", "#f59e0b", "#ef4444", "#3b82f6",
  "#8b5cf6", "#14b8a6", "#f97316", "#ec4899", "#84cc16",
  "#64748b",
];

const MAX_SERIES = 10;

function parsePeriod(dateStr: string, gran: Granularity): string | null {
  if (!dateStr?.trim()) return null;
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return null;
  const y = d.getFullYear();
  if (gran === "year") return `${y}`;
  if (gran === "quarter") return `${y} Q${Math.floor(d.getMonth() / 3) + 1}`;
  return dateStr; // "Mon YYYY" is already the right format
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
  gran: Granularity,
  breakBy: BreakdownField,
): { data: Record<string, string | number>[]; keys: string[]; multivalueWarning: boolean } {
  if (breakBy === "none") {
    const counts = new Map<string, number>();
    for (const row of rows) {
      const p = parsePeriod(row["Publication Date"], gran);
      if (p) counts.set(p, (counts.get(p) ?? 0) + 1);
    }
    const sorted = [...counts.keys()].sort(
      (a, b) => periodSortKey(a, gran) - periodSortKey(b, gran),
    );
    return {
      data: sorted.map((p) => ({ period: p, Papers: counts.get(p)! })),
      keys: ["Papers"],
      multivalueWarning: false,
    };
  }

  const delim = breakBy === "Coarse Data Modality" ? "," : ";";
  // period → value → count
  const matrix = new Map<string, Map<string, number>>();
  const totals = new Map<string, number>();

  for (const row of rows) {
    const p = parsePeriod(row["Publication Date"], gran);
    if (!p) continue;
    const raw = (row as unknown as Record<string, string>)[breakBy] ?? "";
    const values =
      breakBy === "Resource Name"
        ? [raw || "(none)"]
        : raw
            .split(delim)
            .map((v) => v.trim())
            .filter(Boolean);
    const effective = values.length > 0 ? values : ["(none)"];

    const periodMap = matrix.get(p) ?? new Map<string, number>();
    for (const v of effective) {
      periodMap.set(v, (periodMap.get(v) ?? 0) + 1);
      totals.set(v, (totals.get(v) ?? 0) + 1);
    }
    matrix.set(p, periodMap);
  }

  const topKeys = [...totals.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, MAX_SERIES)
    .map(([k]) => k);
  const hasOther = totals.size > MAX_SERIES;

  const sorted = [...matrix.keys()].sort(
    (a, b) => periodSortKey(a, gran) - periodSortKey(b, gran),
  );

  const data = sorted.map((p) => {
    const pm = matrix.get(p)!;
    const entry: Record<string, string | number> = { period: p };
    for (const k of topKeys) entry[k] = pm.get(k) ?? 0;
    if (hasOther) {
      let other = 0;
      for (const [k, v] of pm) if (!topKeys.includes(k)) other += v;
      entry["Other"] = other;
    }
    return entry;
  });

  const keys = hasOther ? [...topKeys, "Other"] : topKeys;
  return { data, keys, multivalueWarning: breakBy !== "Resource Name" };
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
  filters?: TrendsFilterProps;
}

function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div>
      <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600 mb-1">
        {label}
      </label>
      <div className="inline-flex rounded border border-slate-200 overflow-hidden text-sm">
        {options.map((o) => (
          <button
            key={o.value}
            onClick={() => onChange(o.value)}
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

export function TrendsChart({ rows, filters }: Props) {
  const [gran, setGran] = useState<Granularity>("month");
  const [breakBy, setBreakBy] = useState<BreakdownField>("none");
  const [chartType, setChartType] = useState<ChartType>("bar");

  const { data, keys, multivalueWarning } = useMemo(
    () => buildChartData(rows, gran, breakBy),
    [rows, gran, breakBy],
  );

  const isStacked = chartType === "bar" && keys.length > 1;

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
            <option value="Diseases Included">Disease</option>
            <option value="Coarse Data Modality">Coarse Modality</option>
          </select>
        </div>

        <SegmentedControl
          label="Chart type"
          value={chartType}
          onChange={setChartType}
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
          Papers with multiple values in this field are counted once per value — series totals may
          exceed paper count.
        </p>
      )}

      {data.length === 0 ? (
        <p className="py-10 text-center text-sm text-slate-500">
          No dated publications in the current filter.
        </p>
      ) : chartType === "bar" ? (
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
            <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#64748b" }} width={36} />
            <Tooltip
              contentStyle={{ fontSize: 12, borderColor: "#e2e8f0", borderRadius: 6 }}
              cursor={{ fill: "#f1f5f9" }}
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
                stackId={isStacked ? "a" : undefined}
                fill={PALETTE[i % PALETTE.length]}
                radius={isStacked ? undefined : [2, 2, 0, 0]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      ) : (
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
            <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#64748b" }} width={36} />
            <Tooltip contentStyle={{ fontSize: 12, borderColor: "#e2e8f0", borderRadius: 6 }} />
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
      )}
    </div>
  );
}
