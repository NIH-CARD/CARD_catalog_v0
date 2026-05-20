import { Facet } from "./FacetPanel";
import type { FacetSpec } from "../types";

interface Props<T> {
  specs: readonly FacetSpec<T>[];
  rows: T[];
  selections: Record<string, Set<string>>;
  onFacetChange: (field: string, next: Set<string>) => void;
  totalSelected: number;
  onClearAll: () => void;
  error?: string | null;
}

export function FilterRail<T>({
  specs,
  rows,
  selections,
  onFacetChange,
  totalSelected,
  onClearAll,
  error,
}: Props<T>) {
  return (
    <aside className="w-72 border-r border-slate-200 bg-slate-50 px-3 py-4 overflow-y-auto">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-slate-700">Filters</h2>
        {totalSelected > 0 && (
          <button
            className="text-xs text-accent hover:underline"
            onClick={onClearAll}
          >
            clear all ({totalSelected})
          </button>
        )}
      </div>

      {error && (
        <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded p-2 mb-4">
          {error}
        </div>
      )}

      {specs.map((spec) => (
        <Facet<T>
          key={String(spec.field)}
          spec={spec}
          rows={rows}
          selected={selections[spec.field] ?? new Set()}
          onChange={(next) => onFacetChange(String(spec.field), next)}
        />
      ))}
    </aside>
  );
}
