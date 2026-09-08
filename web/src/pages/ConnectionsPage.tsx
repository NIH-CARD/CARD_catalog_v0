import { useEffect, useMemo, useState } from "react";
import { marked } from "marked";
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
  buildValueNodes,
  publicationIdFor,
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

// Short form for the DAG edge labels, where DOMAIN_LABEL's full descriptions
// overflow the small (fontSize 10) space between nodes.
const DOMAIN_LABEL_SHORT: Record<Domain, string> = {
  publication: "Pub ID",
  resource: "Resource",
  concept: "Concept",
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

function DagNode({ data }: NodeProps<{ label: string; root?: boolean; onRemove?: () => void; columns?: string[] }>) {
  const shownColumns = data.columns ?? [];
  return (
    <div
      className={
        "flex flex-col justify-center px-4 py-1.5 rounded border text-sm text-center " +
        (data.root ? "bg-accent text-white border-accent font-semibold" : "bg-white border-slate-300")
      }
      style={{ minWidth: 150, minHeight: 44 }}
    >
      <Handle type="target" position={Position.Left} className="!opacity-0" />
      <div className="flex items-center justify-between gap-2 w-full">
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
      {shownColumns.length > 0 && (
        <div className={"mt-1 border-t " + (data.root ? "border-white/30" : "border-slate-200")}>
          {shownColumns.map((c, i) => (
            <div
              key={c}
              className={
                "text-[9px] leading-tight text-left font-normal truncate py-0.5 " +
                (i < shownColumns.length - 1 ? "border-b " : "") +
                (data.root ? "text-white/70 border-white/20" : "text-slate-400 border-slate-100")
              }
            >
              {c}
            </div>
          ))}
        </div>
      )}
      <Handle type="source" position={Position.Right} className="!opacity-0" />
    </div>
  );
}
interface AddTableNodeData {
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
  availableTables: string[];
  newTable: string;
  onTableChange: (table: string) => void;
  newDomain: Domain | "";
  onDomainChange: (domain: Domain) => void;
  domainsForNewTable: Domain[];
  domainLabel: Record<Domain, string>;
  newColumns: Set<string>;
  onToggleColumn: (field: string) => void;
  nativeColumns: { field: string }[];
  onAdd: () => void;
  loadingTable: string | null;
}

// Trailing "+" action in the DAG chain - hover reveals "JOIN TABLE" as a
// discovery hint; clicking opens a popover anchored right to this node (not a
// separate box elsewhere on the page) with the whole table/join-key/columns
// picker, so the entire "add a table" flow stays inside the DAG canvas.
function AddTableNode({ data }: NodeProps<AddTableNodeData>) {
  const [hovered, setHovered] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={data.onToggle}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        className={
          "nodrag flex items-center gap-1.5 rounded-full border text-[10px] font-semibold uppercase tracking-wide " +
          (data.open
            ? "bg-accent text-white border-accent px-3"
            : "bg-white text-slate-500 border-slate-300 border-dashed hover:border-accent hover:text-accent px-2")
        }
        style={{ height: 44 }}
      >
        <span className="text-sm font-normal leading-none normal-case">+</span>
        {(hovered || data.open) && <span className="whitespace-nowrap pr-0.5">Join table</span>}
      </button>
      {data.open && (
        <div
          className="nodrag nowheel absolute left-full top-0 ml-2 z-50 w-max max-w-2xl rounded border border-slate-300 bg-white p-3 text-left shadow-lg"
          style={{ cursor: "default" }}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-600">Join table</span>
            <button onClick={data.onClose} className="text-slate-400 hover:text-slate-600 text-xs leading-none" aria-label="Close">
              ✕
            </button>
          </div>
          {/* Horizontal row, same shape as the DAG canvas above it, instead of
              a tall vertical stack - fields sit side by side. */}
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="block text-[10px] text-slate-500 mb-1">Table</label>
              <select
                className="border border-slate-300 rounded px-2 py-1 text-xs"
                value={data.newTable}
                onChange={(e) => data.onTableChange(e.target.value)}
              >
                <option value="">Choose…</option>
                {data.availableTables.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            {data.newTable && (
              <div>
                <label className="block text-[10px] text-slate-500 mb-1">Join key</label>
                <select
                  className="border border-slate-300 rounded px-2 py-1 text-xs"
                  value={data.newDomain}
                  onChange={(e) => data.onDomainChange(e.target.value as Domain)}
                >
                  <option value="">Choose…</option>
                  {data.domainsForNewTable.map((d) => (
                    <option key={d} value={d}>{data.domainLabel[d]}</option>
                  ))}
                </select>
                {data.domainsForNewTable.length === 0 && (
                  <p className="text-[10px] text-amber-700 mt-1 max-w-[10rem]">No verified join key to Publications.</p>
                )}
              </div>
            )}
            {data.newTable && data.newDomain && (
              <div className="max-w-xs">
                <label className="block text-[10px] text-slate-500 mb-1">
                  Columns ({data.newColumns.size}/{data.nativeColumns.length})
                </label>
                <div className="flex flex-wrap gap-1 max-h-20 overflow-y-auto">
                  {data.nativeColumns.map((c) => {
                    const active = data.newColumns.has(c.field);
                    return (
                      <button
                        key={c.field}
                        onClick={() => data.onToggleColumn(c.field)}
                        className={
                          "px-1.5 py-0.5 rounded text-[10px] border " +
                          (active ? "bg-accent text-white border-accent" : "bg-white text-slate-400 border-slate-300 hover:bg-slate-100")
                        }
                      >
                        {c.field}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
            {data.newTable && data.newDomain && data.newColumns.size > 0 && (
              <button onClick={data.onAdd} className="bg-accent text-white text-xs px-2 py-1 rounded">
                Add to pipeline
              </button>
            )}
            {data.loadingTable && <span className="text-[10px] text-slate-500">Loading {data.loadingTable}…</span>}
          </div>
        </div>
      )}
    </div>
  );
}

const DAG_NODE_TYPES: NodeTypes = { dag: DagNode, add: AddTableNode };

function DagView({
  edges,
  onRemove,
  addNodeData,
}: {
  edges: DagEdge[];
  onRemove: (table: string) => void;
  addNodeData: AddTableNodeData;
}) {
  // Each edge narrows the *already-merged* result (chained INNER JOINs, not
  // independent joins off Publications) - the layout mirrors that: a single
  // left-to-right chain, not a fan-out of siblings.
  const nodes: Node[] = [
    {
      id: "Publications",
      type: "dag",
      position: { x: 0, y: 0 },
      data: { label: "Publications", root: true, columns: BASE_DISPLAY_COLUMNS },
    },
    ...edges.map((e, i) => ({
      id: e.table,
      type: "dag",
      position: { x: (i + 1) * 250, y: 0 },
      data: { label: e.table, onRemove: () => onRemove(e.table), columns: e.columns },
    })),
    {
      id: "__add__",
      type: "add",
      // Tighter gap than the 250 used between real nodes - that spacing is
      // sized for a full DagNode box, but the "+" pill is much narrower, so
      // the same gap would leave it looking disconnected from the chain.
      position: { x: edges.length * 250 + 175, y: 0 },
      data: addNodeData,
    },
  ];
  const flowEdges: Edge[] = edges.map((e, i) => ({
    id: e.table,
    source: i === 0 ? "Publications" : edges[i - 1].table,
    target: e.table,
    label: DOMAIN_LABEL_SHORT[e.domain],
    labelStyle: { fontSize: 10 },
    style: { stroke: "#94a3b8" },
  }));
  return (
    <div className="h-56 border border-slate-200 rounded-t bg-white">
      <ReactFlow
        nodes={nodes}
        edges={flowEdges}
        nodeTypes={DAG_NODE_TYPES}
        proOptions={{ hideAttribution: true }}
        // No fitView: it always centers the bounding box of all nodes in the
        // container, which pins "Publications" to the middle of the canvas
        // instead of the top-left corner. A fixed viewport keeps the chain
        // anchored top-left, growing rightward (pannable if it overflows),
        // which is the point - it invites adding another table rather than
        // looking "done", and reads top-to-bottom/left-to-right like the rest
        // of the page instead of floating mid-canvas.
        defaultViewport={{ x: 24, y: 16, zoom: 1 }}
        nodesDraggable={false}
      >
        <Background gap={20} />
        <Controls showInteractive={false} position="top-right" />
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
  const [addPopoverOpen, setAddPopoverOpen] = useState(false);

  const [view, setView] = useState<"table" | "graph">("table");
  // "" = default mode, one node per Publication (today's behavior unchanged).
  // Any other value = one node per distinct value of that field instead (see
  // buildValueNodes) - e.g. "Authors" gives one node per author.
  const [nodeFieldSelected, setNodeFieldSelected] = useState<string>("");
  // Single-select, only used in value-node mode ("Connect X by Y" reads as
  // one edge field, not several) - independent of `edgeSelected` below,
  // which stays multi-select for the default one-node-per-Publication mode.
  const [nodeGraphEdgeField, setNodeGraphEdgeField] = useState<string>("Resource Name");
  // How each node's box is sized in value-node mode - "none" keeps the fixed
  // default width; "linear"/"log" scale by how many Publications carry that
  // value. Log is the sensible default: a linear map lets one outlier value
  // (e.g. a hub author on hundreds of papers) dwarf every other box.
  const [nodeScaleMode, setNodeScaleMode] = useState<"none" | "linear" | "log">("log");
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
    setAddPopoverOpen(false);
  }

  function closeAddPopover() {
    setAddPopoverOpen(false);
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
      // Meaningless as an edge field in the plain row-graph (two Publications
      // never share this key) but the natural "same paper" co-occurrence key
      // once nodes are a different field's values (e.g. connect two Authors
      // by shared publication = they co-authored a paper) - see
      // buildValueNodes. Computed (PMC ID falling back to DOI, never a bare
      // PMID) rather than a specific identifier column, since PMID alone is
      // blank for ~3.3% of Publications (DOI-only rows).
      { field: "__publicationKey", label: "Same Publication" },
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

  const graphRows = useMemo(() => {
    const base = dropHubValues(wideRows, hubEnabled ? hubThresholdPct / 100 : 1, edgeSelected);
    // Attach once here, not per-consumer - a Publication's own resolved
    // identity key (PMC ID, falling back to DOI), used as the "Same
    // Publication" edge-field option in value-node mode.
    return base.map((row) => ({ ...row, __publicationKey: publicationIdFor(row) }));
  }, [wideRows, hubEnabled, hubThresholdPct, edgeSelected]);

  // Row mode: the existing multi-select checkboxes (edgeSelected). Value-node
  // mode: exactly the one field chosen in the "Connect X by Y" sentence -
  // that phrasing reads as a single edge field, not several combined.
  const graphEdgeFields = useMemo(() => {
    const fields = nodeFieldSelected ? (nodeGraphEdgeField ? [nodeGraphEdgeField] : []) : edgeSelected;
    return buildEdgeFields<Row>(graphFieldOptions, fields);
  }, [graphFieldOptions, nodeFieldSelected, nodeGraphEdgeField, edgeSelected]);

  // Value-node mode ("Connect <nodes> by <edges>"): one node per distinct
  // value of nodeFieldSelected instead of one per Publication - e.g. connect
  // Authors (nodes) by shared publication (edges) for a co-authorship graph.
  // "" (the default) keeps today's plain one-node-per-Publication behavior.
  const { graphNodeRows, graphNodeField, graphNodeSize } = useMemo(() => {
    if (!nodeFieldSelected) {
      return { graphNodeRows: graphRows, graphNodeField: "Title", graphNodeSize: undefined };
    }
    const delimiter = graphFieldOptions.find((o) => o.field === nodeFieldSelected)?.delimiter;
    const valueNodes = buildValueNodes(graphRows, nodeFieldSelected, delimiter, graphEdgeFields, "__publicationKey");

    if (nodeScaleMode === "none") {
      return { graphNodeRows: valueNodes, graphNodeField: "value", graphNodeSize: undefined };
    }
    const maxCount = Math.max(1, ...valueNodes.map((r) => r.count));
    const MIN_SIDE = 70;
    const MAX_SIDE = 200;
    const MIN_AREA = MIN_SIDE * MIN_SIDE;
    const MAX_AREA = MAX_SIDE * MAX_SIDE;
    const sizeFor = (row: Record<string, unknown>) => {
      const count = (row as { count: number }).count;
      // Log, not linear, is the default for the reason noted on the state
      // declaration above - offered as an explicit alternative, not forced,
      // since a linear map is sometimes exactly what's wanted (e.g. a
      // deliberately narrow, already-filtered set of values).
      const t = nodeScaleMode === "log" ? Math.log(count + 1) / Math.log(maxCount + 1) : count / maxCount;
      // Interpolate AREA (not side length) linearly with t, then take the
      // square root for the side - so a node twice as "big" by the chosen
      // metric actually covers twice the area, matching how people read
      // size-encoded quantities, instead of the side length (and therefore
      // the area) growing quadratically with t.
      return Math.sqrt(MIN_AREA + t * (MAX_AREA - MIN_AREA));
    };
    return { graphNodeRows: valueNodes, graphNodeField: "value", graphNodeSize: sizeFor };
  }, [nodeFieldSelected, graphRows, graphFieldOptions, graphEdgeFields, nodeScaleMode]);

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

  const addNodeData: AddTableNodeData = {
    open: addPopoverOpen,
    onToggle: () => setAddPopoverOpen((o) => !o),
    onClose: closeAddPopover,
    availableTables,
    newTable,
    onTableChange: (table) => {
      setNewTable(table);
      setNewDomain("");
      // Default to bringing in every column - unselect any that aren't wanted.
      setNewColumns(table ? new Set(nativeColumnsFor(table).map((c) => c.field)) : new Set());
    },
    newDomain,
    onDomainChange: setNewDomain,
    domainsForNewTable,
    domainLabel: DOMAIN_LABEL,
    newColumns,
    onToggleColumn: (field) =>
      setNewColumns((prev) => {
        const next = new Set(prev);
        if (next.has(field)) next.delete(field);
        else next.add(field);
        return next;
      }),
    nativeColumns: newTable ? nativeColumnsFor(newTable) : [],
    onAdd: addEdge,
    loadingTable,
  };

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
          <DagView edges={dagEdges} onRemove={removeEdge} addNodeData={addNodeData} />
          {/* Same card as the DAG above (border-t-0 / rounded-b vs. DagView's
              rounded-t) - the SQL is just a verbal restatement of that same
              pipeline, styled like a read-only terminal to read as output,
              not an editable field. */}
          <details className="border border-t-0 border-slate-200 rounded-b overflow-hidden">
            <summary className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500 bg-slate-100 cursor-pointer select-none">
              Generated SQL (read-only — for reading/verifying the pipeline above)
            </summary>
            <pre className="m-0 px-3 py-3 text-xs font-mono leading-relaxed text-emerald-700 bg-slate-50 whitespace-pre-wrap overflow-x-auto">
              {sql}
            </pre>
          </details>
        </div>

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
              <div
                className="md-prose px-3 pb-3 text-xs text-slate-700 overflow-x-auto"
                dangerouslySetInnerHTML={{ __html: marked(frozen.report, { async: false }) as string }}
              />
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
            <div className="border border-slate-200 rounded bg-white p-3 mb-3 text-sm flex items-center gap-2 flex-wrap">
              <span className="text-slate-700">Connect</span>
              <select
                value={nodeFieldSelected}
                onChange={(e) => setNodeFieldSelected(e.target.value)}
                className="px-2 py-1 border border-slate-300 rounded text-sm"
              >
                <option value="">Publications</option>
                {graphFieldOptions.map((o) => (
                  <option key={o.field} value={o.field}>
                    {o.label}
                  </option>
                ))}
              </select>
              {nodeFieldSelected && (
                <>
                  <span className="text-slate-700">by</span>
                  <select
                    value={nodeGraphEdgeField}
                    onChange={(e) => setNodeGraphEdgeField(e.target.value)}
                    className="px-2 py-1 border border-slate-300 rounded text-sm"
                  >
                    {graphFieldOptions.map((o) => (
                      <option key={o.field} value={o.field}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </>
              )}
            </div>
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
              hideFieldSelector={!!nodeFieldSelected}
              nodeScale={
                nodeFieldSelected ? { mode: nodeScaleMode, onModeChange: setNodeScaleMode } : undefined
              }
              hubFilter={{
                enabled: hubEnabled,
                onEnabledChange: setHubEnabled,
                threshold: hubThresholdPct,
                onThresholdChange: setHubThresholdPct,
              }}
            />
            <KnowledgeGraph<Row>
              rows={graphNodeRows}
              nodeField={graphNodeField}
              edgeFields={graphEdgeFields}
              minShared={minShared}
              maxNodes={maxNodes}
              hideDisconnected={!showAll}
              nodeSize={graphNodeSize}
              nodeInfo={(row) =>
                nodeFieldSelected ? (
                  <div className="text-xs text-slate-700">
                    {(row as { count?: number }).count?.toLocaleString()} publication(s)
                  </div>
                ) : (
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
                )
              }
            />
          </>
        )}
      </div>
    </PageShell>
  );
}
