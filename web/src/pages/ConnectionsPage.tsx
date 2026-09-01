import { useEffect, useMemo, useState } from "react";
import ReactFlow, { Background, Controls, Handle, Position, type Edge, type Node, type NodeTypes, type NodeProps } from "reactflow";
import "reactflow/dist/style.css";
import { createColumnHelper } from "@tanstack/react-table";
import { AnalysisPanel } from "../components/AnalysisPanel";
import { DataTable } from "../components/DataTable";
import { ExportButton } from "../components/ExportButton";
import { Facet } from "../components/FacetPanel";
import { GraphControls, buildEdgeFields } from "../components/GraphControls";
import { KnowledgeGraph } from "../components/KnowledgeGraph";
import { PageShell } from "../components/PageShell";
import {
  validDomainsFor,
  facetColumnsFor,
  nativeColumnsFor,
  mergedFieldKey,
  buildWideRows,
  generateSql,
  toFacetFilters,
  dropHubValues,
  buildValueCountsReport,
  buildMacroSummary,
  buildBaselineSummary,
  type DagEdge,
  type Domain,
  type ValueCountsColumn,
  type MacroSummaryColumn,
  type BaselineColumn,
  type ConnectionsStats,
} from "../lib/connectionsGraph";
import { matchesFacet } from "../lib/filter";
import { publicationYearFrom } from "../lib/loadPublications";
import { loadPublications, loadSciLitePmcTypeCounts, loadConnectionsStats } from "../lib/loaders";
import { findTable, TABLE_REGISTRY } from "../lib/tableRegistry";

type Row = Record<string, unknown>;

const DOMAIN_LABEL: Record<Domain, string> = {
  publication: "Publication (PMC ID or DOI)",
  resource: "Resource Name",
  concept: "Concept (gene/bioentity)",
};

const MERGEABLE_TABLES = TABLE_REGISTRY.map((t) => t.name).filter((n) => n !== "Publications");

function downloadMarkdown(filename: string, content: string) {
  const blob = new Blob([content], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

async function loadRawTable(table: string): Promise<Row[]> {
  if (table === "SciLite Annotations") {
    return loadSciLitePmcTypeCounts() as unknown as Promise<Row[]>;
  }
  const meta = findTable(table);
  return meta ? (meta.loadRows() as unknown as Promise<Row[]>) : Promise.resolve([]);
}

// --- DAG visualization -------------------------------------------------

function DagNode({ data }: NodeProps<{ label: string; root?: boolean; onRemove?: () => void }>) {
  return (
    <div
      className={
        "px-3 py-2 rounded border text-xs text-center " +
        (data.root ? "bg-accent text-white border-accent font-semibold" : "bg-white border-slate-300")
      }
      style={{ minWidth: 120 }}
    >
      <Handle type="target" position={Position.Left} className="!opacity-0" />
      <div className="flex items-center justify-between gap-2">
        <span>{data.label}</span>
        {data.onRemove && (
          <button
            onClick={data.onRemove}
            className="text-slate-400 hover:text-red-600 leading-none"
            aria-label={`Remove ${data.label}`}
          >
            ✕
          </button>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="!opacity-0" />
    </div>
  );
}
const DAG_NODE_TYPES: NodeTypes = { dag: DagNode };

function DagView({ edges, onRemove }: { edges: DagEdge[]; onRemove: (table: string) => void }) {
  // Each edge narrows the *already-merged* result (chained INNER JOINs, not
  // independent joins off Publications) - the layout mirrors that: a single
  // left-to-right chain, not a fan-out of siblings.
  const nodes: Node[] = [
    { id: "Publications", type: "dag", position: { x: 0, y: 0 }, data: { label: "Publications", root: true } },
    ...edges.map((e, i) => ({
      id: e.table,
      type: "dag",
      position: { x: (i + 1) * 220, y: 0 },
      data: { label: e.table, onRemove: () => onRemove(e.table) },
    })),
  ];
  const flowEdges: Edge[] = edges.map((e, i) => ({
    id: e.table,
    source: i === 0 ? "Publications" : edges[i - 1].table,
    target: e.table,
    label: DOMAIN_LABEL[e.domain],
    labelStyle: { fontSize: 10 },
    style: { stroke: "#94a3b8" },
  }));
  return (
    <div className="h-56 border border-slate-200 rounded bg-white">
      <ReactFlow nodes={nodes} edges={flowEdges} nodeTypes={DAG_NODE_TYPES} fitView proOptions={{ hideAttribution: true }}>
        <Background gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

// --- Wide-table columns --------------------------------------------------

const wideCol = createColumnHelper<Row>();
const BASE_DISPLAY_COLUMNS = ["Title", "Resource Name", "Authors", "Publication Year"];

function buildWideColumns(edges: DagEdge[]) {
  const cols = BASE_DISPLAY_COLUMNS.map((field) =>
    wideCol.accessor((row) => row[field] as string, { id: field, header: field }),
  );
  for (const edge of edges) {
    for (const field of edge.columns) {
      const key = mergedFieldKey(edge.table, field);
      cols.push(wideCol.accessor((row) => row[key] as string, { id: key, header: key }));
    }
  }
  return cols;
}

export function ConnectionsPage() {
  const [pubRows, setPubRows] = useState<Row[] | null>(null);
  const [rawByTable, setRawByTable] = useState<Record<string, Row[]>>({});
  const [stats, setStats] = useState<ConnectionsStats | null>(null);
  const [loadingTable, setLoadingTable] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [dagEdges, setDagEdges] = useState<DagEdge[]>([]);
  const [facetSelections, setFacetSelections] = useState<Record<string, Record<string, Set<string>>>>({});

  // "Add a table" form state.
  const [newTable, setNewTable] = useState<string>("");
  const [newDomain, setNewDomain] = useState<Domain | "">("");
  const [newColumns, setNewColumns] = useState<Set<string>>(new Set());

  const [view, setView] = useState<"table" | "graph">("table");
  const [edgeSelected, setEdgeSelected] = useState<string[]>(["Resource Name"]);
  const [minShared, setMinShared] = useState(1);
  const [maxNodes, setMaxNodes] = useState(60);
  const [showAll, setShowAll] = useState(false);
  const [hubEnabled, setHubEnabled] = useState(false);
  const [hubThresholdPct, setHubThresholdPct] = useState(30);

  useEffect(() => {
    loadPublications()
      .then((rows) =>
        setPubRows(
          (rows as unknown as Row[]).map((r) => ({
            ...r,
            "Publication Year": publicationYearFrom(r["Publication Date"] as string),
          })),
        ),
      )
      .catch((e: Error) => setError(`Failed to load Publications: ${e.message}`));
    loadConnectionsStats().then(setStats);
  }, []);

  useEffect(() => {
    for (const edge of dagEdges) {
      if (rawByTable[edge.table] || loadingTable === edge.table) continue;
      setLoadingTable(edge.table);
      setError(null);
      loadRawTable(edge.table)
        .then((rows) => setRawByTable((prev) => ({ ...prev, [edge.table]: rows })))
        .catch((e: Error) => setError(`Failed to load ${edge.table}: ${e.message}`))
        .finally(() => setLoadingTable(null));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dagEdges]);

  function addEdge() {
    if (!newTable || !newDomain || newColumns.size === 0) return;
    setDagEdges((prev) => [...prev, { table: newTable, domain: newDomain, columns: Array.from(newColumns) }]);
    setNewTable("");
    setNewDomain("");
    setNewColumns(new Set());
  }

  function removeEdge(table: string) {
    setDagEdges((prev) => prev.filter((e) => e.table !== table));
    setRawByTable((prev) => {
      const next = { ...prev };
      delete next[table];
      return next;
    });
  }

  const filteredPubRows = useMemo(() => {
    if (!pubRows) return [];
    const selections = facetSelections.Publications;
    if (!selections) return pubRows;
    const columns = facetColumnsFor("Publications");
    return pubRows.filter((row) =>
      columns.every((c) => {
        const selected = selections[c.field];
        if (!selected || selected.size === 0) return true;
        return matchesFacet(row, { field: c.field, multivalue: c.multivalue, delimiter: c.delimiter }, selected);
      }),
    );
  }, [pubRows, facetSelections]);

  const filteredRawByTable = useMemo(() => {
    const out: Record<string, Row[]> = {};
    for (const edge of dagEdges) {
      const rows = rawByTable[edge.table] ?? [];
      const selections = facetSelections[edge.table];
      const columns = facetColumnsFor(edge.table);
      if (!selections || columns.length === 0) {
        out[edge.table] = rows;
        continue;
      }
      out[edge.table] = rows.filter((row) =>
        columns.every((c) => {
          const selected = selections[c.field];
          if (!selected || selected.size === 0) return true;
          return matchesFacet(row, { field: c.field, multivalue: c.multivalue, delimiter: c.delimiter }, selected);
        }),
      );
    }
    return out;
  }, [dagEdges, rawByTable, facetSelections]);

  const wideRows = useMemo(
    () => buildWideRows(filteredPubRows, dagEdges, filteredRawByTable),
    [filteredPubRows, dagEdges, filteredRawByTable],
  );

  const sql = useMemo(() => {
    const pubFilters = toFacetFilters(facetSelections.Publications);
    const edgeFilters = Object.fromEntries(
      dagEdges.map((e) => [e.table, toFacetFilters(facetSelections[e.table])]),
    );
    return generateSql(dagEdges, pubFilters, edgeFilters);
  }, [dagEdges, facetSelections]);
  const wideColumns = useMemo(() => buildWideColumns(dagEdges), [dagEdges]);

  // Graph edge options: Publications' own connectable columns + Resource Name,
  // plus every merged-in column - all now just plain columns of one wide table.
  const graphFieldOptions = useMemo(() => {
    const opts: { field: string; label: string; delimiter?: string }[] = [
      { field: "Resource Name", label: "Resource Name", delimiter: ";" },
      ...nativeColumnsFor("Publications").map((c) => ({ field: c.field, label: c.field, delimiter: c.delimiter })),
    ];
    for (const edge of dagEdges) {
      for (const field of edge.columns) {
        // Always ";" here, regardless of the source column's own delimiter
        // (e.g. Datasets' dataset_keywords is comma-delimited at the source)
        // - joinedValue() re-aggregates every merged column with "; ", so
        // that's the only delimiter that's ever actually present once a
        // column lands in the wide table.
        opts.push({ field: mergedFieldKey(edge.table, field), label: mergedFieldKey(edge.table, field), delimiter: ";" });
      }
    }
    return opts;
  }, [dagEdges]);

  const graphRows = useMemo(
    () => dropHubValues(wideRows, hubEnabled ? hubThresholdPct / 100 : 1, edgeSelected),
    [wideRows, hubEnabled, hubThresholdPct, edgeSelected],
  );

  // A quantity (e.g. Code Repositories' FAIR Score) vs. a category - drives
  // both valueCountsColumns and macroColumns below, from the same
  // classification the precomputed baseline stats already use, so a numeric
  // column reads as mean/variance everywhere in the report, not just in the
  // full-catalog baseline section.
  function isNumericField(table: string, field: string): boolean {
    return stats?.[table]?.columns[field]?.kind === "numeric";
  }

  // Title is free text (near-unique per row) - not worth a value-counts breakdown.
  const valueCountsColumns = useMemo(() => {
    const cols: ValueCountsColumn[] = [
      { field: "Title", skip: true },
      { field: "Resource Name", delimiter: ";" },
      { field: "Authors", delimiter: ";" },
      { field: "Publication Year", numeric: isNumericField("Publications", "Publication Year") },
    ];
    for (const edge of dagEdges) {
      // Always ";" - see graphFieldOptions' comment above for why the
      // source column's own delimiter (e.g. dataset_keywords' comma) is
      // never the right one to split a merged wide-table column by.
      for (const field of edge.columns) {
        cols.push({
          field: mergedFieldKey(edge.table, field),
          delimiter: ";",
          numeric: isNumericField(edge.table, field),
        });
      }
    }
    return cols;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dagEdges, stats]);

  // The "at a glance" subset summary - every merged column from every edge
  // (not just each edge's first column), so it lines up 1:1 with
  // buildBaselineSummary's full-catalog numbers for the same fields and a
  // genuine subset-vs-baseline contrast is possible. Title is still excluded
  // (free text, not in valueCountsColumns' skip-aware loop below either).
  const macroColumns = useMemo(() => {
    const cols: MacroSummaryColumn[] = [
      { field: "Resource Name", delimiter: ";" },
      { field: "Publication Year", numeric: isNumericField("Publications", "Publication Year") },
    ];
    for (const edge of dagEdges) {
      // Always ";" - see graphFieldOptions' comment above.
      for (const field of edge.columns) {
        cols.push({
          field: mergedFieldKey(edge.table, field),
          delimiter: ";",
          numeric: isNumericField(edge.table, field),
        });
      }
    }
    return cols;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dagEdges, stats]);

  // Same table+field scope as macroColumns, just table-qualified - so the
  // baseline lines up 1:1 with the "At a Glance" subset summary below it and
  // tracks whatever the DAG actually is at freeze time, not a fixed list.
  const baselineColumns = useMemo(() => {
    const cols: BaselineColumn[] = [
      { table: "Publications", field: "Resource Name" },
      { table: "Publications", field: "Publication Year" },
    ];
    for (const edge of dagEdges) {
      for (const field of edge.columns) cols.push({ table: edge.table, field });
    }
    return cols;
  }, [dagEdges]);

  const [frozen, setFrozen] = useState<{ rows: Row[]; report: string } | null>(null);

  function freezeTable() {
    const query = `## Query\n\n\`\`\`sql\n${sql}\n\`\`\``;
    const baseline = buildBaselineSummary(stats, baselineColumns);
    const macro = buildMacroSummary(wideRows, macroColumns);
    const counts = buildValueCountsReport(wideRows, valueCountsColumns, dagEdges.map((e) => e.table));
    const report = [query, baseline, macro, counts].filter(Boolean).join("\n\n");
    setFrozen({ rows: wideRows, report });
  }

  const availableTables = MERGEABLE_TABLES.filter((t) => !dagEdges.some((e) => e.table === t));
  const domainsForNewTable = newTable ? validDomainsFor("Publications", newTable) : [];

  return (
    <PageShell
      title="Connections"
      count={`${wideRows.length.toLocaleString()} Publications row${wideRows.length === 1 ? "" : "s"} · ${dagEdges.length} table${dagEdges.length === 1 ? "" : "s"} merged in`}
      rail={
        <aside className="w-72 border-r border-slate-200 bg-slate-50 px-3 py-4 overflow-y-auto shrink-0">
          <h2 className="text-sm font-semibold text-slate-700 mb-3">Filters</h2>
          <details open className="mb-3">
            <summary className="text-xs font-semibold uppercase tracking-wide text-slate-600 mb-1 cursor-pointer select-none">
              Publications
            </summary>
            {!pubRows ? (
              <p className="text-xs text-slate-400 italic pl-1">Loading…</p>
            ) : (
              facetColumnsFor("Publications").map((c) => (
                <Facet<Row>
                  key={c.field}
                  spec={{ field: c.field, multivalue: c.multivalue, delimiter: c.delimiter }}
                  rows={pubRows}
                  selected={facetSelections.Publications?.[c.field] ?? new Set()}
                  onChange={(next) =>
                    setFacetSelections((prev) => ({ ...prev, Publications: { ...prev.Publications, [c.field]: next } }))
                  }
                />
              ))
            )}
          </details>
          {dagEdges.map((edge) => (
            <details key={edge.table} open className="mb-3">
              <summary className="text-xs font-semibold uppercase tracking-wide text-slate-600 mb-1 cursor-pointer select-none">
                {edge.table}
              </summary>
              {!rawByTable[edge.table] ? (
                <p className="text-xs text-slate-400 italic pl-1">Loading…</p>
              ) : (
                facetColumnsFor(edge.table).map((c) => (
                  <Facet<Row>
                    key={c.field}
                    spec={{ field: c.field, multivalue: c.multivalue, delimiter: c.delimiter }}
                    rows={rawByTable[edge.table]}
                    selected={facetSelections[edge.table]?.[c.field] ?? new Set()}
                    onChange={(next) =>
                      setFacetSelections((prev) => ({ ...prev, [edge.table]: { ...prev[edge.table], [c.field]: next } }))
                    }
                  />
                ))
              )}
            </details>
          ))}
        </aside>
      }
    >
      <div className="space-y-3">
        {error && (
          <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-3">{error}</div>
        )}

        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600 mb-2">
            Pipeline — Publications is always the base
          </label>
          <DagView edges={dagEdges} onRemove={removeEdge} />
        </div>

        <div className="border border-slate-200 rounded bg-white p-3">
          <label className="block text-xs font-semibold uppercase tracking-wide text-slate-600 mb-2">
            Merge a table in
          </label>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="block text-[10px] text-slate-500 mb-1">Table</label>
              <select
                className="border border-slate-300 rounded px-2 py-1.5 text-sm"
                value={newTable}
                onChange={(e) => {
                  setNewTable(e.target.value);
                  setNewDomain("");
                  setNewColumns(new Set());
                }}
              >
                <option value="">Choose…</option>
                {availableTables.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            {newTable && (
              <div>
                <label className="block text-[10px] text-slate-500 mb-1">Join key</label>
                <select
                  className="border border-slate-300 rounded px-2 py-1.5 text-sm"
                  value={newDomain}
                  onChange={(e) => setNewDomain(e.target.value as Domain)}
                >
                  <option value="">Choose…</option>
                  {domainsForNewTable.map((d) => (
                    <option key={d} value={d}>{DOMAIN_LABEL[d]}</option>
                  ))}
                </select>
                {domainsForNewTable.length === 0 && (
                  <p className="text-[10px] text-amber-700 mt-1">No verified join key to Publications.</p>
                )}
              </div>
            )}
            {newTable && newDomain && (
              <div>
                <label className="block text-[10px] text-slate-500 mb-1">Columns to bring in</label>
                <div className="flex flex-wrap gap-1 max-w-md">
                  {nativeColumnsFor(newTable).map((c) => {
                    const active = newColumns.has(c.field);
                    return (
                      <button
                        key={c.field}
                        onClick={() =>
                          setNewColumns((prev) => {
                            const next = new Set(prev);
                            if (next.has(c.field)) next.delete(c.field);
                            else next.add(c.field);
                            return next;
                          })
                        }
                        className={
                          "px-2 py-0.5 rounded text-xs border " +
                          (active ? "bg-accent text-white border-accent" : "bg-white text-slate-700 border-slate-300 hover:bg-slate-100")
                        }
                      >
                        {c.field}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
            {newTable && newDomain && newColumns.size > 0 && (
              <button onClick={addEdge} className="bg-accent text-white text-sm px-3 py-1.5 rounded">
                Add to pipeline
              </button>
            )}
            {loadingTable && <span className="text-xs text-slate-500">Loading {loadingTable}…</span>}
          </div>
        </div>

        <details className="border border-slate-200 rounded bg-white">
          <summary className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-600 cursor-pointer select-none">
            Generated SQL (read-only — for reading/verifying the pipeline above)
          </summary>
          <pre className="px-3 pb-3 text-xs text-slate-700 whitespace-pre-wrap overflow-x-auto">{sql}</pre>
        </details>

        <div className="flex items-center justify-between gap-3">
          <div className="inline-flex rounded border border-slate-200 overflow-hidden text-sm">
            {(["table", "graph"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={"px-3 py-1.5 " + (view === v ? "bg-accent text-white" : "bg-white text-slate-700 hover:bg-slate-100")}
              >
                {v === "table" ? "📋 Table" : "🕸️ Graph"}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={freezeTable}
              className="px-3 py-1.5 text-sm rounded border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
            >
              ❄️ Freeze table + value counts report
            </button>
            {view === "table" && <ExportButton rows={wideRows} filename="publications_merged" />}
          </div>
        </div>

        {frozen && (
          <div className="border border-slate-200 rounded bg-white">
            <div className="flex items-center justify-between px-3 py-2 border-b border-slate-100">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                Frozen snapshot — {frozen.rows.length.toLocaleString()} rows
              </span>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => downloadMarkdown("cross_table_report.md", frozen.report)}
                  className="text-xs text-accent hover:underline"
                >
                  ↓ Download report.md
                </button>
                <button onClick={() => setFrozen(null)} className="text-xs text-slate-400 hover:text-slate-700">
                  ✕ Unfreeze
                </button>
              </div>
            </div>
            <details className="border-b border-slate-100">
              <summary className="px-3 py-2 text-xs text-slate-600 cursor-pointer select-none">
                Value counts report
              </summary>
              <pre className="px-3 pb-3 text-xs text-slate-700 whitespace-pre-wrap overflow-x-auto">{frozen.report}</pre>
            </details>
            <div className="p-3">
              <AnalysisPanel<{ report: string }>
                type="cross_table"
                filtered={[{ report: frozen.report }]}
                total={frozen.rows.length}
                prepare={(rows) => rows}
              />
            </div>
          </div>
        )}

        {view === "table" ? (
          <DataTable<Row> rows={wideRows} columns={wideColumns} empty="No Publications match the current filters." />
        ) : (
          <>
            <GraphControls<Row>
              options={graphFieldOptions}
              selected={edgeSelected}
              onSelectedChange={setEdgeSelected}
              minShared={minShared}
              onMinSharedChange={setMinShared}
              maxNodes={maxNodes}
              onMaxNodesChange={setMaxNodes}
              showAll={showAll}
              onShowAllChange={setShowAll}
              hubFilter={{
                enabled: hubEnabled,
                onEnabledChange: setHubEnabled,
                threshold: hubThresholdPct,
                onThresholdChange: setHubThresholdPct,
              }}
            />
            <KnowledgeGraph<Row>
              rows={graphRows}
              nodeField="Title"
              edgeFields={buildEdgeFields<Row>(graphFieldOptions, edgeSelected)}
              minShared={minShared}
              maxNodes={maxNodes}
              hideDisconnected={!showAll}
              nodeInfo={(row) => (
                <div className="space-y-0.5">
                  {[...BASE_DISPLAY_COLUMNS, ...dagEdges.flatMap((e) => e.columns.map((c) => mergedFieldKey(e.table, c)))]
                    .filter((f) => typeof row[f] === "string" && (row[f] as string).trim())
                    .slice(0, 6)
                    .map((f) => (
                      <div key={f}>
                        <span className="text-[10px] uppercase text-slate-500">{f}: </span>
                        <span className="text-xs text-slate-700">{row[f] as string}</span>
                      </div>
                    ))}
                </div>
              )}
            />
          </>
        )}
      </div>
    </PageShell>
  );
}
