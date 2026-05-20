import { useMemo } from "react";
import { splitMulti } from "../lib/loadPublications";
import type { FacetSpec } from "../types";

interface Props<T> {
  spec: FacetSpec<T>;
  rows: T[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  maxShown?: number;
}

export function Facet<T>({
  spec,
  rows,
  selected,
  onChange,
  maxShown = 12,
}: Props<T>) {
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

  const visible = counts.slice(0, maxShown);

  const toggle = (value: string) => {
    const next = new Set(selected);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    onChange(next);
  };

  return (
    <div className="mb-6">
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
      <ul className="space-y-1">
        {visible.map(({ value, count }) => {
          const active = selected.has(value);
          return (
            <li key={value}>
              <button
                onClick={() => toggle(value)}
                className={
                  "w-full flex items-center justify-between text-left px-2 py-1 rounded text-sm " +
                  (active
                    ? "bg-accent text-white"
                    : "hover:bg-slate-100 text-slate-700")
                }
              >
                <span className="truncate pr-2">{value}</span>
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
        {counts.length > visible.length && (
          <li className="text-xs text-slate-500 pl-2 pt-1">
            +{counts.length - visible.length} more…
          </li>
        )}
      </ul>
    </div>
  );
}
