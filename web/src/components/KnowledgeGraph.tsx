import { useMemo, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import ReactFlow, {
  Background,
  Controls,
  Handle,
  Position,
  type Edge,
  type Node,
  type NodeProps,
  type NodeTypes,
} from "reactflow";
import "reactflow/dist/style.css";
import { HoverInfo } from "./HoverInfo";
import { splitMulti } from "../lib/loadPublications";

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

interface CardNodeData {
  label: string;
  info?: ReactNode;
}

function CardNode({ data }: NodeProps<CardNodeData>) {
  const body = (
    <div
      className="px-2 py-1 text-[11px] bg-white border border-slate-300 rounded text-center break-words"
      style={{ width: 160 }}
    >
      {data.label}
    </div>
  );
  return (
    <>
      <Handle type="target" position={Position.Top} className="!opacity-0" />
      {data.info ? <HoverInfo content={data.info}>{body}</HoverInfo> : body}
      <Handle type="source" position={Position.Bottom} className="!opacity-0" />
    </>
  );
}

const NODE_TYPES: NodeTypes = { card: CardNode };

export interface EdgeField<T> {
  field: keyof T & string;
  delimiter?: string;
}

interface Props<T> {
  rows: T[];
  /** Field that names each node (e.g. "Resource Name"). */
  nodeField: keyof T & string;
  /** One or more fields whose shared values draw edges between nodes. */
  edgeFields: readonly EdgeField<T>[];
  /** Minimum number of shared values (across all edge fields) needed to draw an edge. */
  minShared?: number;
  /** Cap on nodes to keep the layout legible. */
  maxNodes?: number;
  /** Drop nodes that have zero edges after thresholding. Defaults to true. */
  hideDisconnected?: boolean;
  /** Optional per-row content rendered in a popover on node hover. */
  nodeInfo?: (row: T) => ReactNode;
  /** Optional lookup that turns an edge value (e.g. a URI) into structured metadata. */
  valueMeta?: (field: string, value: string) => ReactNode | null;
}

/**
 * In-browser shared-attribute graph. Each row becomes a node; an edge is drawn
 * when two rows share at least ``minShared`` values across the chosen edge
 * fields. Position is a deterministic circle layout — good enough for v1.
 */
export function KnowledgeGraph<T>({
  rows,
  nodeField,
  edgeFields,
  minShared = 1,
  maxNodes = 60,
  hideDisconnected = true,
  nodeInfo,
  valueMeta,
}: Props<T>) {
  const { nodes, edges, totalCandidates } = useMemo(() => {
    const sliced = rows.slice(0, maxNodes);
    const N = sliced.length;

    // Pre-build per-row, per-field sets of values
    const sets: Set<string>[][] = sliced.map((r) =>
      edgeFields.map(
        ({ field, delimiter }) =>
          new Set(
            splitMulti((r[field] ?? "") as unknown as string, delimiter),
          ),
      ),
    );

    const pairs: {
      i: number;
      j: number;
      shared: number;
      sharedByField: EdgeShared[];
    }[] = [];
    const degree = new Array<number>(N).fill(0);
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
        if (shared >= minShared) {
          pairs.push({ i, j, shared, sharedByField });
          degree[i]++;
          degree[j]++;
        }
      }
    }

    const keep = (idx: number) => !hideDisconnected || degree[idx] > 0;
    const visibleIdx = sliced
      .map((_, i) => i)
      .filter(keep);
    const V = visibleIdx.length;
    const R = Math.max(160, V * 14);

    const ns: Node[] = visibleIdx.map((origIdx, layoutIdx) => {
      const r = sliced[origIdx];
      return {
        id: String(origIdx),
        type: "card",
        data: {
          label: String((r[nodeField] ?? "") || `#${origIdx}`),
          info: nodeInfo ? nodeInfo(r) : undefined,
        },
        position: {
          x: R * Math.cos((2 * Math.PI * layoutIdx) / Math.max(V, 1)),
          y: R * Math.sin((2 * Math.PI * layoutIdx) / Math.max(V, 1)),
        },
      };
    });

    const labelFor = (idx: number) =>
      String((sliced[idx][nodeField] ?? "") || `#${idx}`);
    const es: Edge<EdgeData>[] = pairs.map(({ i, j, shared, sharedByField }) => ({
      id: `${i}-${j}`,
      source: String(i),
      target: String(j),
      data: {
        shared,
        sharedByField,
        sourceLabel: labelFor(i),
        targetLabel: labelFor(j),
      },
      style: {
        stroke: "#94a3b8",
        strokeOpacity: Math.min(0.7, 0.2 + shared * 0.1),
      },
    }));

    return { nodes: ns, edges: es, totalCandidates: N };
  }, [rows, nodeField, edgeFields, minShared, maxNodes, hideDisconnected, nodeInfo]);

  const [hoverEdge, setHoverEdge] = useState<EdgeData | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [pinnedEdge, setPinnedEdge] = useState<EdgeData | null>(null);
  const [pinnedPos, setPinnedPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const activeEdge = pinnedEdge ?? hoverEdge;
  const activePos = pinnedEdge ? pinnedPos : hoverPos;

  return (
    <div className="h-[calc(100vh-16rem)] border border-slate-200 rounded bg-white">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        fitView
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
      </ReactFlow>
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
                Connection ({activeEdge.shared} shared){pinnedEdge ? " · pinned" : ""}
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
      <div className="text-xs text-slate-500 px-3 py-1 flex items-center justify-between">
        <span>
          {nodes.length} nodes, {edges.length} edges
          {hideDisconnected && nodes.length < totalCandidates && (
            <> ({totalCandidates - nodes.length} disconnected hidden)</>
          )}
        </span>
        {rows.length > totalCandidates && (
          <span>
            showing first {totalCandidates} of {rows.length} — refine filters to draw the full set
          </span>
        )}
      </div>
    </div>
  );
}
