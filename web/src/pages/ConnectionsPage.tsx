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
  joinOptionsFor,
  mergeableColumnsFor,
  connectionsColumns,
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
  type JoinOption,
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

const ALL_TABLES = TABLE_REGISTRY.map((t) => t.name);

/** A table the chain can start from, and how its rows are shown, labeled and summarized. */
interface BaseConfig {
  /** Singular noun for one row, e.g. "cell line". */
  entity: string;
  /** Columns shown for the base table in the DAG node, wide table and node popover. */
  display: string[];
  /** Graph node label in row mode. */
  labelField: string;
  /** One-value-per-row identity, used for "Same <entity>" edges and the SQL GROUP BY. */
  idField: string;
  /** Graph fields beyond the table's curated connectable columns. */
  extraGraphFields: string[];
  defaultEdgeField: string;
  /** Base columns in the freeze report's summary and baseline. */
  summary: { field: string; delimiter?: string }[];
}

const BASES: Record<string, BaseConfig> = {
  Publications: {
    entity: "publication",
    display: ["Title", "Resource Name", "Authors", "Publication Year"],
    labelField: "Title",
    idField: "PMID",
    extraGraphFields: ["Resource Name"],
    defaultEdgeField: "Resource Name",
    summary: [{ field: "Resource Name", delimiter: ";" }, { field: "Publication Year" }],
  },
  "Human Cellular Models": {
    entity: "cell line",
    display: ["Product Code", "Gene", "Gene Variant", "Condition"],
    labelField: "Product Code",
    idField: "Product Code",
    extraGraphFields: ["Gene"],
    defaultEdgeField: "Gene",
    summary: [{ field: "Gene" }, { field: "Condition" }],
  },
  Resources: {
    entity: "resource",
    display: ["Resource Name", "Resource Type", "Diseases Included", "Coarse Data Modality"],
    labelField: "Resource Name",
    idField: "Resource Name",
    extraGraphFields: [],
    defaultEdgeField: "Diseases Included",
    summary: [{ field: "Resource Type" }, { field: "Diseases Included", delimiter: ";" }],
  },
};

function plural(entity: string, n: number): string {
  return n === 1 ? entity : `${entity}s`;
}

/** Encodes a JoinOption as a <select> value. */
function joinOptionKey(o: JoinOption): string {
  return o.via ? `${o.domain}|${o.via}` : o.domain;
}

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
  if (table === "Publications") {
    const rows = (await loadPublications()) as unknown as Row[];
    return rows.map((r) => ({ ...r, "Publication Year": publicationYearFrom(r["Publication Date"] as string) }));
  }
  if (table === "SciLite Annotations") {
    return loadSciLitePmcTypeCounts() as unknown as Promise<Row[]>;
  }
  const meta = findTable(table);
  return meta ? (meta.loadRows() as unknown as Promise<Row[]>) : Promise.resolve([]);
}

// --- DAG visualization -------------------------------------------------

const DAG_NODE_WIDTH = 190;
// Node pitch: leaves room for an edge label like "Pub ID (chained)" between boxes.
const DAG_NODE_GAP = 300;

function DagNode({ data }: NodeProps<{ label: string; root?: boolean; onRemove?: () => void; columns?: string[] }>) {
  // Cap the list so a table with many columns doesn't grow its box past the canvas.
  const MAX_SHOWN = 4;
  const allColumns = data.columns ?? [];
  const shownColumns = allColumns.length > MAX_SHOWN ? [...allColumns.slice(0, MAX_SHOWN - 1), `+${allColumns.length - MAX_SHOWN + 1} more`] : allColumns;
  return (
    <div
      className={
        "flex flex-col justify-center px-4 py-1.5 rounded border text-sm text-center " +
        (data.root ? "bg-accent text-white border-accent font-semibold" : "bg-white border-slate-300")
      }
      // Fixed width (titles wrap) so the "+" and the next box can be placed without overlapping it.
      style={{ width: DAG_NODE_WIDTH, minHeight: 44 }}
    >
      <Handle type="target" position={Position.Left} className="!opacity-0" />
      <div className="flex items-center justify-between gap-2 w-full">
        <span className="leading-tight break-words min-w-0">{data.label}</span>
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
              title={c.startsWith("+") ? allColumns.slice(MAX_SHOWN - 1).join(", ") : c}
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
  newJoin: string;
  onJoinChange: (key: string) => void;
  joinOptions: JoinOption[];
  domainLabel: Record<Domain, string>;
  baseTable: string;
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
                  value={data.newJoin}
                  onChange={(e) => data.onJoinChange(e.target.value)}
                >
                  <option value="">Choose…</option>
                  {data.joinOptions.map((o) => (
                    <option key={joinOptionKey(o)} value={joinOptionKey(o)}>
                      {data.domainLabel[o.domain]}
                      {o.via ? ` via ${o.via}` : ""}
                    </option>
                  ))}
                </select>
                {data.joinOptions.length === 0 && (
                  <p className="text-[10px] text-amber-700 mt-1 max-w-[10rem]">
                    No verified join key to {data.baseTable} or the tables merged so far.
                  </p>
                )}
              </div>
            )}
            {data.newTable && data.newJoin && (
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
            {data.newTable && data.newJoin && data.newColumns.size > 0 && (
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
  baseTable,
  edges,
  onRemove,
  addNodeData,
}: {
  baseTable: string;
  edges: DagEdge[];
  onRemove: (table: string) => void;
  addNodeData: AddTableNodeData;
}) {
  // Each edge narrows the *already-merged* result (chained INNER JOINs, not
  // independent joins off Publications) - the layout mirrors that: a single
  // left-to-right chain, not a fan-out of siblings.
  const nodes: Node[] = [
    {
      id: "__base__",
      type: "dag",
      position: { x: 0, y: 0 },
      data: { label: baseTable, root: true, columns: BASES[baseTable].display },
    },
    ...edges.map((e, i) => ({
      id: e.table,
      type: "dag",
      position: { x: (i + 1) * DAG_NODE_GAP, y: 0 },
      data: { label: e.table, onRemove: () => onRemove(e.table), columns: e.columns },
    })),
    {
      id: "__add__",
      type: "add",
      // Tighter gap than DAG_NODE_GAP between real nodes - that spacing is
      // sized for a full DagNode box, but the "+" pill is much narrower, so
      // the same gap would leave it looking disconnected from the chain.
      position: { x: edges.length * DAG_NODE_GAP + DAG_NODE_WIDTH + 16, y: 0 },
      data: addNodeData,
    },
  ];
  const flowEdges: Edge[] = edges.map((e, i) => ({
    id: e.table,
    source: i === 0 ? "__base__" : edges[i - 1].table,
    target: e.table,
    label: DOMAIN_LABEL_SHORT[e.domain] + (e.via ? " (chained)" : ""),
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
/** Merged cells can hold thousands of joined values - clamp to three lines, full text on hover. */
function clampedCell(info: { getValue: () => unknown }) {
  const text = String(info.getValue() ?? "");
  if (!text) return null;
  return (
    <p className="text-xs line-clamp-3 max-w-xs break-words" title={text.length > 2000 ? `${text.slice(0, 2000)}…` : text}>
      {text}
    </p>
  );
}

function buildWideColumns(baseTable: string, edges: DagEdge[]) {
  const cols = BASES[baseTable].display.map((field) =>
    wideCol.accessor((row) => row[field] as string, { id: field, header: field, cell: clampedCell }),
  );
  for (const edge of edges) {
    for (const field of edge.columns) {
      const key = mergedFieldKey(edge.table, field);
      cols.push(wideCol.accessor((row) => row[key] as string, { id: key, header: key, cell: clampedCell }));
    }
  }
  return cols;
}

export function ConnectionsPage() {
  const [baseTable, setBaseTable] = useState<string>("Publications");
  const base = BASES[baseTable];
  const [pubRows, setPubRows] = useState<Row[] | null>(null);
  const [rawByTable, setRawByTable] = useState<Record<string, Row[]>>({});
  const [stats, setStats] = useState<ConnectionsStats | null>(null);
  const [loadingTable, setLoadingTable] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [dagEdges, setDagEdges] = useState<DagEdge[]>([]);
  const [facetSelections, setFacetSelections] = useState<Record<string, Record<string, Set<string>>>>({});

  // "Add a table" form state.
  const [newTable, setNewTable] = useState<string>("");
  const [newJoin, setNewJoin] = useState<string>("");
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
  const [maxNodes, setMaxNodes] = useState(300);
  const [showAll, setShowAll] = useState(false);
  const [hubEnabled, setHubEnabled] = useState(false);
  const [hubThresholdPct, setHubThresholdPct] = useState(30);

  useEffect(() => {
    loadConnectionsStats().then(setStats);
  }, []);

  useEffect(() => {
    setPubRows(null);
    loadRawTable(baseTable)
      .then(setPubRows)
      .catch((e: Error) => setError(`Failed to load ${baseTable}: ${e.message}`));
  }, [baseTable]);

  /** Start over from another table - every merge, filter and graph choice refers to the old base. */
  function changeBase(table: string) {
    setBaseTable(table);
    setDagEdges([]);
    setRawByTable({});
    setFacetSelections({});
    setFrozen(null);
    setNodeFieldSelected("");
    setNodeGraphEdgeField(BASES[table].defaultEdgeField);
    setEdgeSelected([BASES[table].defaultEdgeField]);
    closeAddPopover();
  }

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
    const join = joinOptions.find((o) => joinOptionKey(o) === newJoin);
    if (!newTable || !join || newColumns.size === 0) return;
    setDagEdges((prev) => [...prev, { table: newTable, domain: join.domain, via: join.via, columns: Array.from(newColumns) }]);
    setNewTable("");
    setNewJoin("");
    setNewColumns(new Set());
    setAddPopoverOpen(false);
  }

  function closeAddPopover() {
    setAddPopoverOpen(false);
    setNewTable("");
    setNewJoin("");
    setNewColumns(new Set());
  }

  function removeEdge(table: string) {
    // Later edges joined via one of this table's columns lose their key, so they go too.
    setDagEdges((prev) => {
      const kept: DagEdge[] = [];
      for (const e of prev) {
        if (e.table === table) continue;
        if (e.via && !kept.some((k) => e.via!.startsWith(`${k.table}: `))) continue;
        kept.push(e);
      }
      return kept;
    });
    setRawByTable((prev) => {
      const next = { ...prev };
      delete next[table];
      return next;
    });
  }

  const filteredPubRows = useMemo(() => {
    if (!pubRows) return [];
    const selections = facetSelections[baseTable];
    if (!selections) return pubRows;
    const columns = facetColumnsFor(baseTable);
    return pubRows.filter((row) =>
      columns.every((c) => {
        const selected = selections[c.field];
        if (!selected || selected.size === 0) return true;
        return matchesFacet(row, { field: c.field, multivalue: c.multivalue, delimiter: c.delimiter }, selected);
      }),
    );
  }, [pubRows, facetSelections, baseTable]);

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
    () => buildWideRows(filteredPubRows, dagEdges, filteredRawByTable, baseTable),
    [filteredPubRows, dagEdges, filteredRawByTable, baseTable],
  );

  const sql = useMemo(() => {
    const pubFilters = toFacetFilters(facetSelections[baseTable]);
    const edgeFilters = Object.fromEntries(
      dagEdges.map((e) => [e.table, toFacetFilters(facetSelections[e.table])]),
    );
    return generateSql(dagEdges, pubFilters, edgeFilters, baseTable, BASES[baseTable].idField);
  }, [dagEdges, facetSelections, baseTable]);
  const wideColumns = useMemo(() => buildWideColumns(baseTable, dagEdges), [baseTable, dagEdges]);

  // Graph edge options: Publications' own connectable columns + Resource Name,
  // plus every merged-in column - all now just plain columns of one wide table.
  const graphFieldOptions = useMemo(() => {
    const meta = (field: string) => connectionsColumns(baseTable).find((c) => c.field === field);
    const opts: { field: string; label: string; delimiter?: string }[] = [
      ...BASES[baseTable].extraGraphFields.map((field) => ({
        field,
        label: field,
        delimiter: meta(field)?.multivalue ? meta(field)?.delimiter ?? ";" : undefined,
      })),
      // Meaningless as an edge field in the plain row-graph (two Publications
      // never share this key) but the natural "same paper" co-occurrence key
      // once nodes are a different field's values (e.g. connect two Authors
      // by shared publication = they co-authored a paper) - see
      // buildValueNodes. Computed (PMC ID falling back to DOI, never a bare
      // PMID) rather than a specific identifier column, since PMID alone is
      // blank for ~3.3% of Publications (DOI-only rows).
      { field: "__publicationKey", label: `Same ${BASES[baseTable].entity}` },
      ...nativeColumnsFor(baseTable).map((c) => ({ field: c.field, label: c.field, delimiter: c.delimiter })),
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
  }, [dagEdges, baseTable]);

  const graphRows = useMemo(() => {
    const base = dropHubValues(wideRows, hubEnabled ? hubThresholdPct / 100 : 1, edgeSelected);
    // Attach once here, not per-consumer - a Publication's own resolved
    // identity key (PMC ID, falling back to DOI), used as the "Same
    // Publication" edge-field option in value-node mode.
    // Other bases have a plain one-value identity column.
    return base.map((row) => ({
      ...row,
      __publicationKey: baseTable === "Publications" ? publicationIdFor(row) : String(row[BASES[baseTable].idField] ?? ""),
    }));
  }, [wideRows, hubEnabled, hubThresholdPct, edgeSelected, baseTable]);

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
      return { graphNodeRows: graphRows, graphNodeField: BASES[baseTable].labelField, graphNodeSize: undefined };
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
  }, [nodeFieldSelected, graphRows, graphFieldOptions, graphEdgeFields, nodeScaleMode, baseTable]);

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
    const cols: ValueCountsColumn[] =
      baseTable === "Publications"
        ? [
            { field: "Title", skip: true },
            { field: "Resource Name", delimiter: ";" },
            { field: "Authors", delimiter: ";" },
            { field: "Publication Year", numeric: isNumericField("Publications", "Publication Year") },
          ]
        : BASES[baseTable].summary.map((c) => ({ ...c, numeric: isNumericField(baseTable, c.field) }));
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
  }, [dagEdges, stats, baseTable]);

  // The "at a glance" subset summary - every merged column from every edge
  // (not just each edge's first column), so it lines up 1:1 with
  // buildBaselineSummary's full-catalog numbers for the same fields and a
  // genuine subset-vs-baseline contrast is possible. Title is still excluded
  // (free text, not in valueCountsColumns' skip-aware loop below either).
  const macroColumns = useMemo(() => {
    const cols: MacroSummaryColumn[] = BASES[baseTable].summary.map((c) => ({
      ...c,
      numeric: isNumericField(baseTable, c.field),
    }));
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
  }, [dagEdges, stats, baseTable]);

  // Same table+field scope as macroColumns, just table-qualified - so the
  // baseline lines up 1:1 with the "At a Glance" subset summary below it and
  // tracks whatever the DAG actually is at freeze time, not a fixed list.
  const baselineColumns = useMemo(() => {
    const cols: BaselineColumn[] = BASES[baseTable].summary.map((c) => ({ table: baseTable, field: c.field }));
    for (const edge of dagEdges) {
      for (const field of edge.columns) cols.push({ table: edge.table, field });
    }
    return cols;
  }, [dagEdges, baseTable]);

  const [frozen, setFrozen] = useState<{ rows: Row[]; report: string } | null>(null);

  function freezeTable() {
    const query = `## Query\n\n\`\`\`sql\n${sql}\n\`\`\``;
    const baseline = buildBaselineSummary(stats, baselineColumns);
    const macro = buildMacroSummary(wideRows, macroColumns);
    const counts = buildValueCountsReport(
      wideRows,
      valueCountsColumns,
      dagEdges.map((e) => e.table),
      15,
      baseTable === "Publications" ? "Publications" : `${baseTable} rows`,
    );
    const report = [query, baseline, macro, counts].filter(Boolean).join("\n\n");
    setFrozen({ rows: wideRows, report });
  }

  const availableTables = ALL_TABLES.filter((t) => t !== baseTable && !dagEdges.some((e) => e.table === t));
  const joinOptions = newTable ? joinOptionsFor(baseTable, newTable, dagEdges) : [];
  const newJoinDomain = joinOptions.find((o) => joinOptionKey(o) === newJoin)?.domain;

  const addNodeData: AddTableNodeData = {
    open: addPopoverOpen,
    onToggle: () => setAddPopoverOpen((o) => !o),
    onClose: closeAddPopover,
    availableTables,
    newTable,
    onTableChange: (table) => {
      setNewTable(table);
      setNewJoin("");
      setNewColumns(new Set());
    },
    newJoin,
    onJoinChange: (key) => {
      setNewJoin(key);
      const domain = joinOptions.find((o) => joinOptionKey(o) === key)?.domain;
      // Default to bringing in every column - unselect any that aren't wanted.
      setNewColumns(domain ? new Set(mergeableColumnsFor(newTable, domain).map((c) => c.field)) : new Set());
    },
    joinOptions,
    domainLabel: DOMAIN_LABEL,
    baseTable,
    newColumns,
    onToggleColumn: (field) =>
      setNewColumns((prev) => {
        const next = new Set(prev);
        if (next.has(field)) next.delete(field);
        else next.add(field);
        return next;
      }),
    nativeColumns: newTable && newJoinDomain ? mergeableColumnsFor(newTable, newJoinDomain) : [],
    onAdd: addEdge,
    loadingTable,
  };

  return (
    <PageShell
      title="Connections"
      count={`${wideRows.length.toLocaleString()} ${plural(base.entity, wideRows.length)} · ${dagEdges.length} table${dagEdges.length === 1 ? "" : "s"} merged in`}
      rail={
        <aside className="w-72 border-r border-slate-200 bg-slate-50 px-3 py-4 overflow-y-auto shrink-0">
          <h2 className="text-sm font-semibold text-slate-700 mb-3">Filters</h2>
          <details open className="mb-3">
            <summary className="text-xs font-semibold uppercase tracking-wide text-slate-600 mb-1 cursor-pointer select-none">
              {baseTable}
            </summary>
            {!pubRows ? (
              <p className="text-xs text-slate-400 italic pl-1">Loading…</p>
            ) : (
              facetColumnsFor(baseTable).map((c) => (
                <Facet<Row>
                  key={c.field}
                  spec={{ field: c.field, multivalue: c.multivalue, delimiter: c.delimiter }}
                  rows={pubRows}
                  selected={facetSelections[baseTable]?.[c.field] ?? new Set()}
                  onChange={(next) =>
                    setFacetSelections((prev) => ({ ...prev, [baseTable]: { ...prev[baseTable], [c.field]: next } }))
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
          <div className="flex items-center gap-2 mb-2">
            <label htmlFor="base-table" className="text-xs font-semibold uppercase tracking-wide text-slate-600">
              Pipeline — start from
            </label>
            <select
              id="base-table"
              value={baseTable}
              onChange={(e) => changeBase(e.target.value)}
              className="px-2 py-0.5 border border-slate-300 rounded text-xs"
            >
              {Object.keys(BASES).map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            {dagEdges.length > 0 && <span className="text-[10px] text-slate-400">changing it clears the merges</span>}
          </div>
          <DagView baseTable={baseTable} edges={dagEdges} onRemove={removeEdge} addNodeData={addNodeData} />
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
            {view === "table" && <ExportButton rows={wideRows} filename={`${baseTable.toLowerCase().replace(/\s+/g, "_")}_merged`} />}
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
          <DataTable<Row> rows={wideRows} columns={wideColumns} empty={`No ${plural(base.entity, 0)} match the current filters.`} />
        ) : (
          <>
            <div className="border border-slate-200 rounded bg-white p-3 mb-3 text-sm flex items-center gap-2 flex-wrap">
              <span className="text-slate-700">Connect</span>
              <select
                value={nodeFieldSelected}
                onChange={(e) => setNodeFieldSelected(e.target.value)}
                className="px-2 py-1 border border-slate-300 rounded text-sm"
              >
                <option value="">{baseTable}</option>
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
              edgeFieldCount={graphEdgeFields.length}
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
                    {(row as { count?: number }).count?.toLocaleString()} {base.entity}(s)
                  </div>
                ) : (
                  <div className="space-y-0.5">
                    {[...base.display, ...dagEdges.flatMap((e) => e.columns.map((c) => mergedFieldKey(e.table, c)))]
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
