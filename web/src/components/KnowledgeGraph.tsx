import { useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  type Edge,
  type Node,
} from "reactflow";
import "reactflow/dist/style.css";
import { splitMulti } from "../lib/loadPublications";

interface Props<T> {
  rows: T[];
  /** Field that names each node (e.g. "Resource Name"). */
  nodeField: keyof T & string;
  /** Multivalue field used to draw edges between nodes that share any value. */
  edgeField: keyof T & string;
  /** Cap on nodes to keep the layout legible. */
  maxNodes?: number;
}

/**
 * Build a simple shared-attribute graph in-browser. Each row becomes a node;
 * two rows that share at least one value of ``edgeField`` get an edge.
 * Position is a deterministic circle layout — good enough for a v1 stub.
 */
export function KnowledgeGraph<T>({
  rows,
  nodeField,
  edgeField,
  maxNodes = 60,
}: Props<T>) {
  const { nodes, edges } = useMemo(() => {
    const sliced = rows.slice(0, maxNodes);
    const N = sliced.length;
    const R = Math.max(160, N * 14);

    const ns: Node[] = sliced.map((r, i) => ({
      id: String(i),
      data: { label: String((r[nodeField] ?? "") || `#${i}`) },
      position: {
        x: R * Math.cos((2 * Math.PI * i) / Math.max(N, 1)),
        y: R * Math.sin((2 * Math.PI * i) / Math.max(N, 1)),
      },
      style: {
        fontSize: 11,
        padding: 6,
        borderRadius: 6,
        background: "#fff",
        border: "1px solid #cbd5e1",
        width: 160,
      },
    }));

    const sets = sliced.map(
      (r) => new Set(splitMulti((r[edgeField] ?? "") as unknown as string)),
    );
    const es: Edge[] = [];
    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        let shared = 0;
        for (const v of sets[i]) if (sets[j].has(v)) shared++;
        if (shared > 0) {
          es.push({
            id: `${i}-${j}`,
            source: String(i),
            target: String(j),
            style: {
              stroke: "#94a3b8",
              strokeOpacity: Math.min(0.7, 0.2 + shared * 0.1),
            },
          });
        }
      }
    }

    return { nodes: ns, edges: es };
  }, [rows, nodeField, edgeField, maxNodes]);

  return (
    <div className="h-[calc(100vh-14rem)] border border-slate-200 rounded bg-white">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={20} />
        <Controls />
      </ReactFlow>
      {rows.length > nodes.length && (
        <div className="text-xs text-slate-500 px-3 py-1">
          Showing first {nodes.length} of {rows.length} — refine filters to draw the full set.
        </div>
      )}
    </div>
  );
}
