import { describe, expect, it } from "vitest";
import {
  alternativeSupplierId,
  buildRecoveryPayload,
  recoveriesForEvent,
} from "./recoveryTargets";
import type { NetworkResponse } from "./types";

const net = {
  finished_good_sku: "FG-WIDGET",
  suppliers: [
    { supplier_id: "SUP-001", sku: "COMP-A", preferred_for_sku: true, name: "Alpha" },
    { supplier_id: "SUP-002", sku: "COMP-A", preferred_for_sku: false, name: "Beta" },
    { supplier_id: "SUP-003", sku: "COMP-B", preferred_for_sku: true, name: "Gamma" },
  ],
  warehouses: [
    { warehouse_id: "WH-002", current_inventory: { "FG-WIDGET": 400 } },
    { warehouse_id: "WH-003", current_inventory: { "FG-WIDGET": 120 } },
  ],
  routes: [{ route_id: "RTE-007" }],
} as unknown as NetworkResponse;

describe("recoveriesForEvent", () => {
  it("hides route recoveries on a supplier outage", () => {
    const ids = recoveriesForEvent("supplier_outage").map((r) => r.id);
    expect(ids).toContain("activate_alternative_supplier");
    expect(ids).toContain("restore_supplier");
    expect(ids).not.toContain("expedite_route");
    expect(ids).not.toContain("restore_factory");
  });

  it("offers only route recoveries for transportation delay", () => {
    const ids = recoveriesForEvent("transportation_delay").map((r) => r.id);
    expect(ids).toEqual(["", "expedite_route", "increase_route_capacity"]);
  });
});

describe("buildRecoveryPayload", () => {
  it("uses the selected supplier and same-SKU alternate, not hardcoded Alpha/Beta", () => {
    const { payload, error } = buildRecoveryPayload({
      recovery: "activate_alternative_supplier",
      recoveryDay: 5,
      target: "SUP-001",
      eventType: "supplier_outage",
      net,
    });
    expect(error).toBeNull();
    expect(payload).toMatchObject({
      target_node_id: "SUP-001",
      alternative_supplier_id: "SUP-002",
    });
  });

  it("refuses activate-alternate when no shared SKU exists", () => {
    const { payload, error } = buildRecoveryPayload({
      recovery: "activate_alternative_supplier",
      recoveryDay: 5,
      target: "SUP-003",
      eventType: "supplier_outage",
      net,
    });
    expect(payload).toBeNull();
    expect(error).toMatch(/No other supplier/);
  });

  it("expedites the selected route instead of RTE-001", () => {
    const { payload } = buildRecoveryPayload({
      recovery: "expedite_route",
      recoveryDay: 4,
      target: "RTE-007",
      eventType: "transportation_delay",
      net,
    });
    expect(payload?.target_node_id).toBe("RTE-007");
  });

  it("increases capacity on the selected route instead of RTE-002", () => {
    const { payload } = buildRecoveryPayload({
      recovery: "increase_route_capacity",
      recoveryDay: 4,
      target: "RTE-007",
      eventType: "transportation_delay",
      net,
    });
    expect(payload?.target_node_id).toBe("RTE-007");
  });

  it("reallocates from the disrupted warehouse, not WH-002/WH-003 hardcoded pair", () => {
    const { payload } = buildRecoveryPayload({
      recovery: "reallocate_inventory",
      recoveryDay: 2,
      target: "WH-003",
      eventType: "warehouse_disruption",
      net,
    });
    expect(payload?.source_node_id).toBe("WH-003");
    expect(payload?.destination_node_id).toBe("WH-002");
    expect(payload?.sku).toBe("FG-WIDGET");
  });

  it("restores the disruption target, not a leftover supplier id on factory events", () => {
    const { payload } = buildRecoveryPayload({
      recovery: "restore_factory",
      recoveryDay: 6,
      target: "FAC-002",
      eventType: "factory_shutdown",
      net,
    });
    expect(payload).toMatchObject({ recovery_type: "restore_factory", target_node_id: "FAC-002" });
  });
});

describe("alternativeSupplierId", () => {
  it("prefers the non-preferred same-SKU supplier", () => {
    expect(alternativeSupplierId(net, "SUP-001")).toBe("SUP-002");
  });
});
