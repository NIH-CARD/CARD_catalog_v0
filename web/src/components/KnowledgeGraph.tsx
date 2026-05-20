import { useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  type Edge,
  type Node,
} from "reactflow";
import "reactflow/dist/style.css";
import { splitMulti } from "../lib/loadPublications";

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
  /** Drop nodes that have zero edges after thresholding. */
  hideDisconnected?: boolean;
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
  hideDisconnected = false,
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

    const pairs: { i: number; j: number; shared: number }[] = [];
    const degree = new Array<number>(N).fill(0);
    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        let shared = 0;
        for (let f = 0; f < edgeFields.length; f++) {
          for (const v of sets[i][f]) if (sets[j][f].has(v)) shared++;
        }
        if (shared >= minShared) {
          pairs.push({ i, j, shared });
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
        data: { label: String((r[nodeField] ?? "") || `#${origIdx}`) },
        position: {
          x: R * Math.cos((2 * Math.PI * layoutIdx) / Math.max(V, 1)),
          y: R * Math.sin((2 * Math.PI * layoutIdx) / Math.max(V, 1)),
        },
        style: {
          fontSize: 11,
          padding: 6,
          borderRadius: 6,
          background: "#fff",
          border: "1px solid #cbd5e1",
          width: 160,
        },
      };
    });

    const es: Edge[] = pairs.map(({ i, j, shared }) => ({
      id: `${i}-${j}`,
      source: String(i),
      target: String(j),
      style: {
        stroke: "#94a3b8",
        strokeOpacity: Math.min(0.7, 0.2 + shared * 0.1),
      },
    }));

    return { nodes: ns, edges: es, totalCandidates: N };
  }, [rows, nodeField, edgeFields, minShared, maxNodes, hideDisconnected]);

  return (
    <div className="h-[calc(100vh-16rem)] border border-slate-200 rounded bg-white">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={20} />
        <Controls />
      </ReactFlow>
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
