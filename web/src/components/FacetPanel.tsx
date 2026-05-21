import { useMemo, useState } from "react";
import { splitMulti } from "../lib/loadPublications";
import type { FacetSpec } from "../types";

interface Props<T> {
  spec: FacetSpec<T>;
  rows: T[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
}

export function Facet<T>({
  spec,
  rows,
  selected,
  onChange,
}: Props<T>) {
  const [query, setQuery] = useState("");

  const display = (v: string) => spec.displayLabel?.(v) ?? v;

  const counts = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of rows) {
      const raw = (r[spec.field] ?? "") as unknown as string;
      const values = spec.multivalue
        ? splitMulti(raw, spec.delimiter)
        : raw
          ? [String(raw).trim()]
          : [];
      for (const v of values) {
        if (!v) continue;
        m.set(v, (m.get(v) ?? 0) + 1);
      }
    }
    return Array.from(m.entries())
      .map(([value, count]) => ({ value, count }))
      .sort((a, b) => b.count - a.count);
  }, [rows, spec]);

  const filteredCounts = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return counts;
    return counts.filter(({ value }) => {
      if (value.toLowerCase().includes(needle)) return true;
      const label = display(value);
      return label !== value && label.toLowerCase().includes(needle);
    });
    // display intentionally not in deps — it's derived from spec which is in deps
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [counts, query, spec]);

  const visible = query.trim() ? filteredCounts : filteredCounts.slice(0, 100);

  const toggle = (value: string) => {
    const next = new Set(selected);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    onChange(next);
  };

  return (
    <div className="mb-3 border border-slate-200 rounded bg-white p-3">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          {spec.label ?? String(spec.field)}
        </h3>
        {selected.size > 0 && (
          <button
            className="text-[10px] text-accent hover:underline"
            onClick={() => onChange(new Set())}
          >
            clear
          </button>
        )}
      </div>

      {counts.length > 5 && (
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`Search ${counts.length.toLocaleString()} values…`}
          className="w-full mb-1 px-2 py-1 text-xs border border-slate-200 rounded focus:outline-none focus:border-accent"
        />
      )}

      <ul className="space-y-1 max-h-72 overflow-y-auto">
        {visible.map(({ value, count }) => {
          const active = selected.has(value);
          const label = display(value);
          return (
            <li key={value}>
              <button
                onClick={() => toggle(value)}
                title={label !== value ? value : undefined}
                className={
                  "w-full flex items-center justify-between text-left px-2 py-1 rounded text-sm " +
                  (active
                    ? "bg-accent text-white"
                    : "hover:bg-slate-100 text-slate-700")
                }
              >
                <span className="truncate pr-2">{label}</span>
                <span
                  className={
                    "text-xs tabular-nums " +
                    (active ? "text-white/90" : "text-slate-500")
                  }
                >
                  {count.toLocaleString()}
                </span>
              </button>
            </li>
          );
        })}
        {query.trim() && filteredCounts.length === 0 && (
          <li className="text-xs text-slate-500 pl-2 pt-1 italic">No matches</li>
        )}
      </ul>
    </div>
  );
}
