import { describe, expect, it } from "vitest";
import { fmtPct } from "./components/MetricCard";
import { hotRouteIds, impactedIdsForDay, statusMapForDay, subtitleForPoint } from "./timeline";
import type { DailyPoint, GraphEdge } from "./types";

describe("fmtPct", () => {
  it("formats percentages", () => {
    expect(fmtPct(87.36)).toBe("87.4%");
    expect(fmtPct(null)).toBe("n/a");
  });
});

function pt(partial: Partial<DailyPoint> & Pick<DailyPoint, "day" | "node_id">): DailyPoint {
  return {
    node_type: "warehouse",
    inventory_by_sku: {},
    production: 0,
    planned_production: 0,
    demand: 0,
    fulfilled: 0,
    unfulfilled_backlog: 0,
    stockout: false,
    safety_stock_violation: false,
    available: true,
    status: "normal",
    notes: [],
    ...partial,
  };
}

describe("timeline playback helpers", () => {
  it("maps status for a selected day only", () => {
    const daily = [
      pt({ day: 1, node_id: "SUP-001", node_type: "supplier", status: "unavailable" }),
      pt({ day: 2, node_id: "SUP-001", node_type: "supplier", status: "normal" }),
    ];
    expect(statusMapForDay(daily, 1)["SUP-001"]).toBe("unavailable");
    expect(statusMapForDay(daily, 2)["SUP-001"]).toBe("normal");
  });

  it("marks nodes that fall behind baseline production", () => {
    const baseline = [pt({ day: 5, node_id: "FAC-1", node_type: "factory", production: 40 })];
    const scenario = [pt({ day: 5, node_id: "FAC-1", node_type: "factory", production: 10 })];
    expect(impactedIdsForDay(scenario, baseline, 5).has("FAC-1")).toBe(true);
    expect(impactedIdsForDay(scenario, baseline, 4).size).toBe(0);
  });

  it("highlights routes between impacted nodes, not path node ids", () => {
    const edges: GraphEdge[] = [
      { id: "RTE-001", source: "SUP-001", target: "WH-001", label: "a", data: {} },
      { id: "RTE-099", source: "CUS-001", target: "CUS-002", label: "b", data: {} },
    ];
    const hot = hotRouteIds(edges, new Set(["SUP-001", "WH-001"]), ["SUP-001", "WH-001"]);
    expect(hot.has("RTE-001")).toBe(true);
    expect(hot.has("RTE-099")).toBe(false);
  });

  it("does not treat a single impacted endpoint as a hot route", () => {
    const edges: GraphEdge[] = [
      { id: "RTE-001", source: "SUP-001", target: "WH-001", label: "a", data: {} },
      { id: "RTE-FAC", source: "WH-001", target: "FAC-1", label: "b", data: {} },
    ];
    const hot = hotRouteIds(edges, new Set(["SUP-001"]), ["SUP-001"]);
    expect(hot.has("RTE-001")).toBe(false);
    expect(hot.has("RTE-FAC")).toBe(false);
  });

  it("builds factory subtitles from the day's production", () => {
    const sub = subtitleForPoint(
      pt({ day: 3, node_id: "FAC-1", node_type: "factory", production: 12.4, planned_production: 40 }),
      "factory"
    );
    expect(sub).toContain("12");
    expect(sub).toContain("40");
  });
});

