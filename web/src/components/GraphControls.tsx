import type { EdgeField } from "./KnowledgeGraph";

interface FieldOption<T> {
  field: keyof T & string;
  label?: string;
  delimiter?: string;
}

interface Props<T> {
  options: readonly FieldOption<T>[];
  selected: (keyof T & string)[];
  onSelectedChange: (next: (keyof T & string)[]) => void;
  minShared: number;
  onMinSharedChange: (n: number) => void;
  maxNodes: number;
  onMaxNodesChange: (n: number) => void;
  showAll: boolean;
  onShowAllChange: (v: boolean) => void;
  /** Optional hub-filter pair — pass undefined to hide this control. */
  hubFilter?: {
    enabled: boolean;
    onEnabledChange: (v: boolean) => void;
    threshold: number;
    onThresholdChange: (n: number) => void;
  };
  /** Suppress the "Connect nodes by" field-checkbox section while keeping
   * every other control (min shared, max nodes, hub filter, disconnected
   * visibility) - for a page offering its own edge-field selector instead. */
  hideFieldSelector?: boolean;
  /** Optional node-size-by-frequency mode selector - pass undefined to hide
   * this control (only meaningful when nodes represent aggregated values
   * with a frequency, not one node per raw row). */
  nodeScale?: {
    mode: "none" | "linear" | "log";
    onModeChange: (mode: "none" | "linear" | "log") => void;
  };
}

export function GraphControls<T>({
  options,
  selected,
  onSelectedChange,
  minShared,
  onMinSharedChange,
  maxNodes,
  onMaxNodesChange,
  showAll,
  onShowAllChange,
  hubFilter,
  hideFieldSelector = false,
  nodeScale,
}: Props<T>) {
  const toggle = (field: keyof T & string) => {
    if (selected.includes(field)) {
      onSelectedChange(selected.filter((f) => f !== field));
    } else {
      onSelectedChange([...selected, field]);
    }
  };

  return (
    <div className="border border-slate-200 rounded bg-white p-3 mb-3 text-sm space-y-3">
      {!hideFieldSelector && (
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600 mb-1">
            Connect nodes by
          </label>
          <div className="flex flex-wrap gap-2">
            {options.map((o) => {
              const active = selected.includes(o.field);
              return (
                <button
                  key={String(o.field)}
                  onClick={() => toggle(o.field)}
                  className={
                    "px-2 py-1 rounded text-xs border " +
                    (active
                      ? "bg-accent text-white border-accent"
                      : "bg-white text-slate-700 border-slate-300 hover:bg-slate-100")
                  }
                >
                  {o.label ?? String(o.field)}
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div className={"flex flex-wrap items-end gap-4 " + (hideFieldSelector ? "" : "pt-1 border-t border-slate-100")}>
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600 mb-1">
            Min shared
          </label>
          <input
            type="number"
            min={1}
            max={100}
            value={minShared}
            onChange={(e) => onMinSharedChange(Math.max(1, parseInt(e.target.value || "1", 10)))}
            className="w-16 px-2 py-1 border border-slate-300 rounded text-sm tabular-nums"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600 mb-1">
            Max nodes
          </label>
          <input
            type="number"
            min={1}
            value={maxNodes}
            onChange={(e) => onMaxNodesChange(Math.max(1, parseInt(e.target.value || "60", 10)))}
            className="w-20 px-2 py-1 border border-slate-300 rounded text-sm tabular-nums"
          />
        </div>

        <label className="inline-flex items-center gap-2 text-slate-700 pb-1.5">
          <input
            type="checkbox"
            checked={showAll}
            onChange={(e) => onShowAllChange(e.target.checked)}
            className="accent-accent"
          />
          Disconnected Nodes Visibility
        </label>

        {nodeScale && (
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600 mb-1">
              Scale node
            </label>
            <select
              value={nodeScale.mode}
              onChange={(e) => nodeScale.onModeChange(e.target.value as "none" | "linear" | "log")}
              className="px-2 py-1 border border-slate-300 rounded text-sm"
            >
              <option value="none">Do not</option>
              <option value="linear">By frequency</option>
              <option value="log">By frequency (log)</option>
            </select>
          </div>
        )}

        {hubFilter && (
          <label className="inline-flex items-center gap-2 text-slate-700 pb-1.5">
            <input
              type="checkbox"
              checked={hubFilter.enabled}
              onChange={(e) => hubFilter.onEnabledChange(e.target.checked)}
              className="accent-accent"
            />
            Hub filter: drop concepts in &gt;
            <input
              type="number"
              min={1}
              max={99}
              value={hubFilter.threshold}
              disabled={!hubFilter.enabled}
              onChange={(e) =>
                hubFilter.onThresholdChange(Math.max(1, parseInt(e.target.value || "30", 10)))
              }
              className="w-14 px-1.5 py-0.5 border border-slate-300 rounded text-xs tabular-nums disabled:bg-slate-100 disabled:text-slate-400"
            />
            % of papers
          </label>
        )}
      </div>
    </div>
  );
}

export function buildEdgeFields<T>(
  options: readonly FieldOption<T>[],
  selected: readonly (keyof T & string)[],
): EdgeField<T>[] {
  return options
    .filter((o) => selected.includes(o.field))
    .map((o) => ({ field: o.field, delimiter: o.delimiter }));
}
