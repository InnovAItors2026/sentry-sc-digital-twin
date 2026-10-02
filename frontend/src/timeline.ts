import type { DailyPoint, GraphEdge, HealthStatus } from "./types";

export function horizonFromTimeline(daily: DailyPoint[]): number {
  if (!daily.length) return 1;
  return Math.max(...daily.map((d) => d.day), 1);
}

export function statusMapForDay(daily: DailyPoint[], day: number): Record<string, HealthStatus> {
  const map: Record<string, HealthStatus> = {};
  for (const d of daily) {
    if (d.day === day) map[d.node_id] = d.status;
  }
  return map;
}

export function pointsForDay(daily: DailyPoint[], day: number): DailyPoint[] {
  return daily.filter((d) => d.day === day);
}

/** Nodes that deviate from baseline or are unhealthy on this simulated day. */
export function impactedIdsForDay(
  scenarioDaily: DailyPoint[],
  baselineDaily: DailyPoint[],
  day: number
): Set<string> {
  const base = new Map<string, DailyPoint>();
  for (const d of baselineDaily) {
    if (d.day === day) base.set(d.node_id, d);
  }
  const ids = new Set<string>();
  for (const d of scenarioDaily) {
    if (d.day !== day) continue;
    const b = base.get(d.node_id);
    if (d.status === "warning" || d.status === "critical" || d.status === "unavailable") {
      ids.add(d.node_id);
      continue;
    }
    if (!b) continue;
    if (d.production + 1e-6 < b.production) ids.add(d.node_id);
    if (d.fulfilled + 1e-6 < b.fulfilled) ids.add(d.node_id);
    const bInv = Object.values(b.inventory_by_sku || {}).reduce((a, n) => a + n, 0);
    const sInv = Object.values(d.inventory_by_sku || {}).reduce((a, n) => a + n, 0);
    if (bInv > 10 && sInv + 1.0 < bInv * 0.85) ids.add(d.node_id);
    if (d.notes?.length) ids.add(d.node_id);
  }
  return ids;
}

/** Highlight routes that connect currently impacted nodes (path order is node ids, not route ids). */
export function hotRouteIds(graphEdges: GraphEdge[], impacted: Set<string>, path: string[]): Set<string> {
  const hot = new Set<string>();
  for (let i = 0; i < path.length - 1; i++) {
    const a = path[i];
    const b = path[i + 1];
    for (const e of graphEdges) {
      if ((e.source === a && e.target === b) || (e.source === b && e.target === a)) hot.add(e.id);
    }
  }
  for (const e of graphEdges) {
    if (impacted.has(e.source) && impacted.has(e.target)) hot.add(e.id);
  }
  return hot;
}

export function subtitleForPoint(d: DailyPoint | undefined, kind: string): string | null {
  if (!d) return null;
  if (kind === "factory") {
    return `Prod ${Math.round(d.production)} / plan ${Math.round(d.planned_production)}`;
  }
  if (kind === "warehouse") {
    const total = Object.values(d.inventory_by_sku || {}).reduce((a, n) => a + n, 0);
    return `On-hand ${Math.round(total)}`;
  }
  if (kind === "customer") {
    return `Filled ${Math.round(d.fulfilled)} · backlog ${Math.round(d.unfulfilled_backlog)}`;
  }
  return d.notes?.[0] ? d.notes[0].slice(0, 48) : null;
}
