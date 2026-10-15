import { useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  Panel,
  Position,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "reactflow";
import "reactflow/dist/style.css";
import { HoverInfo } from "./HoverInfo";
import { splitMulti } from "../lib/loadPublications";
import { forceLayout } from "../lib/forceLayout";
import type { ColorLegend } from "../lib/graphColors";

interface EdgeShared {
  field: string;
  values: string[];
}
interface EdgeData {
  shared: number;
  sharedByField: EdgeShared[];
  sourceLabel: string;
  targetLabel: string;
}

interface DotNodeData {
  label: string;
  info: ReactNode;
  diameter: number;
  color: string;
  showLabel: boolean;
}

const DEFAULT_COLOR = "#64748b";
/** Labels are drawn for the most connected nodes only (all of them in a small graph). */
const LABEL_TOP_N = 10;
const LABEL_ALL_BELOW = 25;

// Both handles sit invisibly at the dot's center so straight edges meet in the middle.
const CENTER_HANDLE: CSSProperties = {
  top: "50%",
  left: "50%",
  transform: "translate(-50%, -50%)",
  width: 1,
  height: 1,
  minWidth: 0,
  minHeight: 0,
  border: 0,
  opacity: 0,
  pointerEvents: "none", // otherwise the handle sits on top of the dot and swallows hover
};

function DotNode({ data }: NodeProps<DotNodeData>) {
  const dot = (
    <div
      className="rounded-full border border-white shadow-sm"
      style={{ width: data.diameter, height: data.diameter, background: data.color }}
    />
  );
  return (
    <div className="relative" style={{ width: data.diameter, height: data.diameter }}>
      <Handle type="target" position={Position.Top} style={CENTER_HANDLE} />
      <HoverInfo content={data.info} pinnable>{dot}</HoverInfo>
      {data.showLabel && (
        <div
          className="absolute left-1/2 -translate-x-1/2 text-[10px] leading-tight text-slate-700 text-center pointer-events-none w-40"
          style={{ top: data.diameter + 2, textShadow: "0 0 3px #fff, 0 0 3px #fff" }}
        >
          {data.label}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} style={CENTER_HANDLE} />
    </div>
  );
}

const NODE_TYPES: NodeTypes = { dot: DotNode };

/** What the "min shared" threshold counts: fields when several are selected, values for a single one. */
export function sharedThresholdUnit(fieldCount: number): "fields" | "values" {
  return fieldCount >= 2 ? "fields" : "values";
}

export interface EdgeField<T> {
  field: keyof T & string;
  delimiter?: string;
}

interface Props<T> {
  rows: T[];
  /** Field that names each node (e.g. "Resource Name"). */
  nodeField: keyof T & string;
  /** Optional display label overriding nodeField (e.g. owner/repo instead of a full URL). */
  nodeLabel?: (row: T) => string;
  /** One or more fields whose shared values draw edges between nodes. */
  edgeFields: readonly EdgeField<T>[];
  /** Edge threshold. With 2+ edge fields: minimum number of FIELDS sharing at least one
   * value (capped at the field count). With a single field: minimum number of shared
   * VALUES in it - a field count would always be 1 there. See sharedThresholdUnit. */
  minShared?: number;
  /** Cap on nodes to keep the layout legible. */
  maxNodes?: number;
  /** Drop nodes that have zero edges after thresholding. Defaults to true. */
  hideDisconnected?: boolean;
  /** Optional per-row content rendered in a popover on node hover. */
  nodeInfo?: (row: T) => ReactNode;
  /** Optional lookup that turns an edge value (e.g. a URI) into structured metadata. */
  valueMeta?: (field: string, value: string) => ReactNode | null;
  /** Optional per-row size in px (e.g. frequency in a value-node graph, 70-200) -
   * omit to size nodes by their number of connections. */
  nodeSize?: (row: T) => number;
  /** Optional per-row node color, with its legend. */
  nodeColor?: (row: T) => string;
  colorLegend?: ColorLegend;
}

/**
 * In-browser shared-attribute graph, modeled on the legacy Streamlit knowledge graph:
 * each row is a dot; two rows are linked when they share values in at least
 * ``minShared`` of the selected fields. Force-directed layout, dot size by number of
 * connections, edge width by number of shared values, optional color (e.g. FAIR).
 */
export function KnowledgeGraph<T>({
  rows,
  nodeField,
  nodeLabel,
  edgeFields,
  minShared = 1,
  maxNodes = 300,
  hideDisconnected = true,
  nodeInfo,
  valueMeta,
  nodeSize,
  nodeColor,
  colorLegend,
}: Props<T>) {
  const [minConnections, setMinConnections] = useState(0);

  const { nodes, edges, totalCandidates, stats } = useMemo(() => {
    const sliced = rows.slice(0, maxNodes);
    const N = sliced.length;
    const byValues = sharedThresholdUnit(edgeFields.length) === "values";
    const threshold = byValues ? Math.max(1, minShared) : Math.max(1, Math.min(minShared, edgeFields.length));
    const labelFor = (idx: number) =>
      (nodeLabel ? nodeLabel(sliced[idx]) : String(sliced[idx][nodeField] ?? "")) || `#${idx}`;

    // Pre-build per-row, per-field sets of values
    const sets: Set<string>[][] = sliced.map((r) =>
      edgeFields.map(
        ({ field, delimiter }) =>
          new Set(
            splitMulti((r[field] ?? "") as unknown as string, delimiter),
          ),
      ),
    );

    let pairs: {
      i: number;
      j: number;
      shared: number;
      sharedByField: EdgeShared[];
    }[] = [];
    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        let shared = 0;
        const sharedByField: EdgeShared[] = [];
        for (let f = 0; f < edgeFields.length; f++) {
          const overlap: string[] = [];
          for (const v of sets[i][f]) if (sets[j][f].has(v)) overlap.push(v);
          if (overlap.length) {
            shared += overlap.length;
            sharedByField.push({ field: String(edgeFields[f].field), values: overlap });
          }
        }
        if ((byValues ? shared : sharedByField.length) >= threshold) pairs.push({ i, j, shared, sharedByField });
      }
    }

    // Visibility: degree on the full thresholded graph, as Streamlit's filter_graph_by_degree.
    const degree = new Array<number>(N).fill(0);
    for (const { i, j } of pairs) {
      degree[i]++;
      degree[j]++;
    }
    const minDegree = Math.max(hideDisconnected ? 1 : 0, minConnections);
    const visibleIdx = sliced.map((_, i) => i).filter((i) => degree[i] >= minDegree);
    const layoutIdx = new Map(visibleIdx.map((orig, k) => [orig, k]));
    pairs = pairs.filter(({ i, j }) => layoutIdx.has(i) && layoutIdx.has(j));
    const V = visibleIdx.length;

    const visibleDegree = new Array<number>(V).fill(0);
    for (const { i, j } of pairs) {
      visibleDegree[layoutIdx.get(i)!]++;
      visibleDegree[layoutIdx.get(j)!]++;
    }
    const maxDegree = Math.max(1, ...visibleDegree);
    const diameters = visibleIdx.map((orig, k) =>
      nodeSize ? nodeSize(sliced[orig]) / 5 : 8 + 22 * Math.sqrt(visibleDegree[k] / maxDegree),
    );
    const positions = forceLayout(
      V,
      pairs.map(({ i, j }) => ({ i: layoutIdx.get(i)!, j: layoutIdx.get(j)! })),
      diameters.map((d) => d / 2),
    );
    const ranked = visibleIdx
      .map((orig, k) => ({ orig, k, degree: visibleDegree[k] }))
      .sort((a, b) => b.degree - a.degree);
    const labelled = new Set(
      (V <= LABEL_ALL_BELOW ? ranked : ranked.slice(0, LABEL_TOP_N).filter((r) => r.degree > 0)).map((r) => r.k),
    );

    const ns: Node<DotNodeData>[] = visibleIdx.map((orig, k) => {
      const r = sliced[orig];
      const label = labelFor(orig);
      return {
        id: String(orig),
        type: "dot",
        data: {
          label,
          diameter: diameters[k],
          color: nodeColor ? nodeColor(r) : DEFAULT_COLOR,
          showLabel: labelled.has(k),
          info: (
            <div className="text-xs text-slate-700 space-y-1">
              {/* Dots carry no visible label, so the popover always names the node */}
              <div className="font-semibold text-slate-900">{label}</div>
              {nodeInfo?.(r)}
              <div className="text-slate-500">Connections: {visibleDegree[k]}</div>
            </div>
          ),
        },
        position: { x: positions[k].x - diameters[k] / 2, y: positions[k].y - diameters[k] / 2 },
      };
    });

    const es: Edge<EdgeData>[] = pairs.map(({ i, j, shared, sharedByField }) => ({
      id: `${i}-${j}`,
      source: String(i),
      target: String(j),
      type: "straight",
      data: {
        shared,
        sharedByField,
        sourceLabel: labelFor(i),
        targetLabel: labelFor(j),
      },
      style: {
        stroke: "#94a3b8",
        strokeOpacity: 0.45,
        strokeWidth: 0.8 + Math.min(shared - 1, 5) * 0.5,
      },
    }));

    // Connected components (isolated nodes count as their own), via union-find
    const parent = visibleIdx.map((_, k) => k);
    const find = (a: number): number => (parent[a] === a ? a : (parent[a] = find(parent[a])));
    for (const { i, j } of pairs) parent[find(layoutIdx.get(i)!)] = find(layoutIdx.get(j)!);
    const components = new Set(visibleIdx.map((_, k) => find(k))).size;

    return {
      nodes: ns,
      edges: es,
      totalCandidates: N,
      stats: {
        components,
        avgDegree: V ? (2 * pairs.length) / V : 0,
        top: ranked.slice(0, 10).filter((r) => r.degree > 0).map((r) => ({ label: labelFor(r.orig), degree: r.degree })),
      },
    };
  }, [rows, nodeField, nodeLabel, edgeFields, minShared, maxNodes, hideDisconnected, minConnections, nodeInfo, nodeSize, nodeColor]);

  const [hoverEdge, setHoverEdge] = useState<EdgeData | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [pinnedEdge, setPinnedEdge] = useState<EdgeData | null>(null);
  const [pinnedPos, setPinnedPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const activeEdge = pinnedEdge ?? hoverEdge;
  const activePos = pinnedEdge ? pinnedPos : hoverPos;

  return (
    <div className="border border-slate-200 rounded bg-white">
      {/* Canvas gets the fixed height; the stats footer sits below it instead of being clipped */}
      <div className="h-[calc(100vh-16rem)]">
      <ReactFlow
        // Remount when the drawn graph changes so fitView re-frames it
        key={`${nodes.length}:${edges.length}`}
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.08 }}
        minZoom={0.05}
        proOptions={{ hideAttribution: true }}
        onEdgeMouseEnter={(evt, edge) => {
          if (!edge.data) return;
          setHoverEdge(edge.data as EdgeData);
          setHoverPos({ x: evt.clientX, y: evt.clientY });
        }}
        onEdgeMouseMove={(evt) => {
          setHoverPos({ x: evt.clientX, y: evt.clientY });
        }}
        onEdgeMouseLeave={() => setHoverEdge(null)}
        onEdgeClick={(evt, edge) => {
          if (!edge.data) return;
          setPinnedEdge(edge.data as EdgeData);
          setPinnedPos({ x: evt.clientX, y: evt.clientY });
        }}
        onPaneClick={() => setPinnedEdge(null)}
      >
        <Background gap={20} />
        <Controls />
        {colorLegend && (
          <Panel position="top-right" className="bg-white/90 border border-slate-200 rounded px-2 py-1.5 text-[11px] text-slate-700">
            <div className="font-semibold mb-1">{colorLegend.title}</div>
            {colorLegend.items.map((it) => (
              <div key={it.label} className="flex items-center gap-1.5">
                <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ background: it.color }} />
                {it.label}
              </div>
            ))}
          </Panel>
        )}
      </ReactFlow>
      </div>
      {activeEdge &&
        createPortal(
          <div
            className={
              "fixed z-50 max-w-lg bg-white border border-slate-200 shadow-lg rounded p-3 text-xs text-slate-700 " +
              (pinnedEdge ? "pointer-events-auto max-h-[80vh] overflow-auto" : "pointer-events-none")
            }
            style={{ top: activePos.y + 12, left: activePos.x + 12 }}
          >
            <div className="flex items-start justify-between gap-3 mb-1">
              <div className="text-[10px] uppercase tracking-wide text-slate-500">
                Connection ({activeEdge.sharedByField.length} fields · {activeEdge.shared} values shared){pinnedEdge ? " · pinned" : ""}
              </div>
              {pinnedEdge && (
                <button
                  className="text-slate-400 hover:text-slate-700 text-xs leading-none -mt-0.5"
                  onClick={() => setPinnedEdge(null)}
                  aria-label="Close"
                >
                  ✕
                </button>
              )}
            </div>
            <div className="mb-2 text-slate-700">
              <span className="font-medium">{activeEdge.sourceLabel}</span>
              <span className="mx-1 text-slate-400">↔</span>
              <span className="font-medium">{activeEdge.targetLabel}</span>
            </div>
            {activeEdge.sharedByField.map((f) => (
              <div key={f.field} className="mb-2 last:mb-0">
                <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-0.5">
                  {f.field} ({f.values.length})
                </div>
                <ul className="space-y-1">
                  {f.values.map((v) => {
                    const meta = valueMeta ? valueMeta(f.field, v) : null;
                    return (
                      <li key={v} className="text-slate-700">
                        {meta ?? <span className="font-mono text-[10px]">{v}</span>}
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>,
          document.body,
        )}
      <div className="text-xs text-slate-500 px-3 py-1 flex flex-wrap items-center justify-between gap-2">
        <span className="tabular-nums">
          {nodes.length} nodes · {edges.length} connections · {stats.components} clusters · avg{" "}
          {stats.avgDegree.toFixed(1)} connections/node
          {nodes.length < totalCandidates && <> ({totalCandidates - nodes.length} hidden)</>}
        </span>
        <label className="inline-flex items-center gap-1.5">
          Min connections
          <input
            type="number"
            min={0}
            max={50}
            value={minConnections}
            onChange={(e) => setMinConnections(Math.max(0, parseInt(e.target.value || "0", 10)))}
            className="w-14 px-1.5 py-0.5 border border-slate-300 rounded tabular-nums"
          />
        </label>
        {rows.length > totalCandidates && (
          <span>
            showing first {totalCandidates} of {rows.length} — refine filters to draw the full set
          </span>
        )}
      </div>
      {stats.top.length > 0 && (
        <details className="text-xs text-slate-600 px-3 pb-2">
          <summary className="cursor-pointer select-none">Most connected</summary>
          <ol className="mt-1 list-decimal list-inside space-y-0.5">
            {stats.top.map((t) => (
              <li key={t.label}>
                {t.label} <span className="text-slate-400 tabular-nums">({t.degree})</span>
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}
