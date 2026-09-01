import { useMemo, useState } from "react";
import { splitMulti } from "../../lib/loadPublications";
import type { ColumnMeta } from "../../lib/tableRegistry";

type Row = Record<string, unknown>;

interface Props {
  rows: readonly Row[];
  column: ColumnMeta;
  onSelect: (value: string) => void;
}

/** Single-select searchable value list — same "Search N values…" UX as the
 * existing per-page FilterRail/Facet, but picking one value (a seed) rather
 * than toggling a multi-select filter set. */
export function ValuePicker({ rows, column, onSelect }: Props) {
  const [query, setQuery] = useState("");

  const counts = useMemo(() => {
    const m = new Map<string, number>();
    for (const row of rows) {
      const raw = row[column.field];
      if (typeof raw !== "string") continue;
      const values = column.multivalue ? splitMulti(raw, column.delimiter) : raw.trim() ? [raw.trim()] : [];
      const seenInRow = new Set<string>();
      for (const v of values) {
        if (!v || seenInRow.has(v)) continue;
        seenInRow.add(v);
        m.set(v, (m.get(v) ?? 0) + 1);
      }
    }
    return Array.from(m.entries())
      .map(([value, count]) => ({ value, count }))
      .sort((a, b) => b.count - a.count);
  }, [rows, column]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return counts;
    return counts.filter(({ value }) => value.toLowerCase().includes(needle));
  }, [counts, query]);

  const visible = query.trim() ? filtered : filtered.slice(0, 100);

  return (
    <div>
      {counts.length > 5 && (
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`Search ${counts.length.toLocaleString()} values…`}
          className="w-full mb-2 px-2 py-1.5 text-sm border border-slate-200 rounded focus:outline-none focus:border-accent"
        />
      )}
      <ul className="space-y-1 max-h-80 overflow-y-auto border border-slate-200 rounded bg-white">
        {visible.map(({ value, count }) => (
          <li key={value}>
            <button
              onClick={() => onSelect(value)}
              className="w-full flex items-center justify-between text-left px-3 py-1.5 text-sm hover:bg-slate-100"
            >
              <span className="truncate pr-2 text-slate-700">{value}</span>
              <span className="text-xs tabular-nums text-slate-500">{count.toLocaleString()}</span>
            </button>
          </li>
        ))}
        {visible.length === 0 && (
          <li className="text-xs text-slate-500 px-3 py-2 italic">No values</li>
        )}
      </ul>
    </div>
  );
}
