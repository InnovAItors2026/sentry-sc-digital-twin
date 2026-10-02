import { useCallback, useMemo, useRef } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import EntityNode from "./EntityNode";
import type { GraphEdge, GraphNode, HealthStatus } from "../types";

const nodeTypes = { entity: EntityNode };

function columnOf(n: GraphNode): number {
  if (n.type === "supplier") return 0;
  if (n.id === "WH-001") return 280;
  if (n.type === "factory") return 560;
  if (n.type === "warehouse") return 840;
  return 1120;
}

function layout(nodes: GraphNode[]): Node[] {
  const counts: Record<string, number> = {};
  return nodes.map((n) => {
    const col = String(columnOf(n));
    counts[col] = (counts[col] || 0) + 1;
    const y = (counts[col] - 1) * 120;
    let subtitle = "";
    if (n.type === "supplier") subtitle = `SKU ${(n.data as { sku?: string }).sku || ""}`;
    if (n.type === "warehouse") {
      const inv = (n.data as { total_inventory?: number }).total_inventory;
      subtitle = inv != null ? `On-hand ${Math.round(inv)}` : "";
    }
    if (n.type === "factory") subtitle = `Cap ${(n.data as { production_capacity_per_day?: number }).production_capacity_per_day}/d`;
    if (n.type === "customer") subtitle = `Demand ${(n.data as { daily_demand?: number }).daily_demand}/d`;
    return {
      id: n.id,
      type: "entity",
      position: { x: columnOf(n), y },
      data: { ...n.data, kind: n.type, label: n.label, id: n.id, subtitle },
    };
  });
}

interface Props {
  graphNodes: GraphNode[];
  graphEdges: GraphEdge[];
  selectedId?: string | null;
  onSelect?: (id: string) => void;
  statusByNode?: Record<string, HealthStatus>;
  affectedIds?: Set<string>;
  affectedEdges?: Set<string>;
  daySubtitles?: Record<string, string>;
}

export default function NetworkGraph({
  graphNodes,
  graphEdges,
  selectedId,
  onSelect,
  statusByNode,
  affectedIds,
  affectedEdges,
  daySubtitles,
}: Props) {
  const nodes = useMemo(() => {
    return layout(graphNodes).map((n) => ({
      ...n,
      selected: n.id === selectedId,
      data: {
        ...n.data,
        status: statusByNode?.[n.id] || "normal",
        affected: affectedIds?.has(n.id) || false,
        subtitle: daySubtitles?.[n.id] ?? n.data.subtitle,
      },
    }));
  }, [graphNodes, selectedId, statusByNode, affectedIds, daySubtitles]);

  const edges: Edge[] = useMemo(
    () =>
      graphEdges.map((e) => {
        // Use precomputed route ids only. Touching one impacted node is not enough —
        // that painted a star around every factory/customer instead of the cascade path.
        const hot = Boolean(affectedEdges?.has(e.id));
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          label: e.id,
          animated: hot,
          style: {
            stroke: hot ? "#fb7185" : "#64748b",
            strokeWidth: hot ? 2.4 : 1.4,
          },
        };
      }),
    [graphEdges, affectedEdges]
  );

  const fitted = useRef(false);
  const onInit = useCallback((instance: ReactFlowInstance) => {
    if (fitted.current) return;
    fitted.current = true;
    instance.fitView();
  }, []);

  const onNodeClick = useCallback(
    (_: unknown, node: Node) => {
      onSelect?.(node.id);
    },
    [onSelect]
  );

  return (
    <div className="h-full w-full rounded-xl overflow-hidden border border-white/10 bg-ink-950">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        onInit={onInit}
        minZoom={0.4}
        maxZoom={1.6}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1e293b" gap={18} />
        <Controls className="!bg-ink-800 !border-white/10 !fill-slate-200" />
        <MiniMap
          className="!bg-ink-800 !border-white/10"
          nodeColor={(n) => {
            const k = String(n.data?.kind);
            if (k === "supplier") return "#38bdf8";
            if (k === "factory") return "#a78bfa";
            if (k === "warehouse") return "#fbbf24";
            return "#34d399";
          }}
        />
      </ReactFlow>
    </div>
  );
}
