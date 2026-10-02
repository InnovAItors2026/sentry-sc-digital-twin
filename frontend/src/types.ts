export type NodeKind = "supplier" | "factory" | "warehouse" | "customer";
export type HealthStatus = "normal" | "warning" | "critical" | "unavailable";

export interface GraphNode {
  id: string;
  type: NodeKind;
  label: string;
  data: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  data: Record<string, unknown>;
}

export interface NetworkResponse {
  network_id: string;
  name: string;
  finished_good_sku: string;
  unit_revenue: number;
  counts: Record<string, number>;
  suppliers: Record<string, unknown>[];
  factories: Record<string, unknown>[];
  warehouses: Record<string, unknown>[];
  routes: Record<string, unknown>[];
  customers: Record<string, unknown>[];
  graph_nodes: GraphNode[];
  graph_edges: GraphEdge[];
  assumptions: string[];
  inventory_overview: {
    warehouse_id: string;
    name: string;
    total_inventory: number;
    maximum_capacity: number;
    utilization_pct: number;
    by_sku: Record<string, number>;
  }[];
  overall_status: string;
}

export interface ScenarioSummary {
  scenario_id: string;
  name: string;
  horizon_days: number;
  disruption_count: number;
  recovery_count: number;
  simulated: boolean;
  notes?: string | null;
}

export interface Metrics {
  total_demand: number;
  total_units_delivered: number;
  unfulfilled_demand: number;
  service_level_pct: number | null;
  stockout_days: number;
  minimum_inventory: number | null;
  production_shortfall: number;
  total_transportation_cost: number;
  estimated_disruption_cost: number | null;
  average_delivery_delay: number | null;
  affected_customer_count: number | null;
  recovery_day: number | null;
  lost_revenue?: number | null;
  excess_procurement_cost?: number | null;
  excess_transport_cost?: number | null;
  expedite_and_reallocation_cost?: number;
  cost_notes?: string[];
}

export interface DailyPoint {
  day: number;
  node_id: string;
  node_type: string;
  inventory_by_sku: Record<string, number>;
  production: number;
  planned_production: number;
  demand: number;
  fulfilled: number;
  unfulfilled_backlog: number;
  stockout: boolean;
  safety_stock_violation: boolean;
  available: boolean;
  status: HealthStatus;
  notes: string[];
}

export interface SimulateResponse {
  scenario_id: string;
  baseline_metrics: Metrics;
  scenario_metrics: Metrics;
  affected_nodes: {
    node_id: string;
    node_type: string;
    impact_summary: string;
    reasons: string[];
    deviation_score: number;
  }[];
  daily_timeline: DailyPoint[];
  baseline_daily_timeline: DailyPoint[];
  events: { day: number; node_id: string; category: string; message: string }[];
  assumptions: string[];
  feasibility: { recovery_type: string; feasible_in_model: boolean; reasons: string[]; claim: string }[];
  horizon_days: number;
  propagation_path: string[];
}

export interface CompareResponse {
  scenarios: Record<string, unknown>[];
  trade_offs: string[];
}
