import type { NetworkResponse } from "./types";

export const RECOVERY_OPTIONS = [
  { id: "", label: "None", eventTypes: ["*"] },
  {
    id: "activate_alternative_supplier",
    label: "Activate alternative supplier",
    eventTypes: ["supplier_outage"],
  },
  { id: "restore_supplier", label: "Restore supplier", eventTypes: ["supplier_outage"] },
  { id: "restore_factory", label: "Restore factory", eventTypes: ["factory_shutdown"] },
  { id: "expedite_route", label: "Expedite this route", eventTypes: ["transportation_delay"] },
  {
    id: "increase_route_capacity",
    label: "Increase this route’s capacity",
    eventTypes: ["transportation_delay"],
  },
  {
    id: "reallocate_inventory",
    label: "Reallocate from this warehouse",
    eventTypes: ["warehouse_disruption"],
  },
] as const;

export type RecoveryId = (typeof RECOVERY_OPTIONS)[number]["id"];

type SupplierRow = {
  supplier_id: string;
  sku?: string;
  preferred_for_sku?: boolean;
  name?: string;
};

type WarehouseRow = {
  warehouse_id: string;
  current_inventory?: Record<string, number>;
};

export function recoveriesForEvent(eventType: string) {
  return RECOVERY_OPTIONS.filter((r) => r.eventTypes.includes("*") || r.eventTypes.includes(eventType));
}

export function alternativeSupplierId(net: Pick<NetworkResponse, "suppliers">, primaryId: string): string | null {
  const suppliers = net.suppliers as SupplierRow[];
  const primary = suppliers.find((s) => s.supplier_id === primaryId);
  if (!primary?.sku) return null;
  const alts = suppliers.filter((s) => s.supplier_id !== primaryId && s.sku === primary.sku);
  const nonPreferred = alts.find((s) => !s.preferred_for_sku);
  return (nonPreferred ?? alts[0])?.supplier_id ?? null;
}

export function otherWarehouseId(net: Pick<NetworkResponse, "warehouses">, sourceId: string): string | null {
  const warehouses = net.warehouses as WarehouseRow[];
  const other = warehouses.find((w) => w.warehouse_id !== sourceId);
  return other?.warehouse_id ?? null;
}

export function skuForReallocate(
  net: Pick<NetworkResponse, "warehouses" | "finished_good_sku">,
  sourceId: string
): string {
  const warehouses = net.warehouses as WarehouseRow[];
  const inv = warehouses.find((w) => w.warehouse_id === sourceId)?.current_inventory;
  if (inv) {
    const [best] = Object.entries(inv).sort((a, b) => b[1] - a[1]);
    if (best && best[1] > 0) return best[0];
  }
  return net.finished_good_sku;
}

export function buildRecoveryPayload(opts: {
  recovery: string;
  recoveryDay: number;
  target: string;
  eventType: string;
  net: Pick<NetworkResponse, "suppliers" | "warehouses" | "finished_good_sku" | "routes">;
}): { payload: Record<string, unknown> | null; error: string | null; summary: string | null } {
  const { recovery, recoveryDay, target, eventType, net } = opts;
  if (!recovery) return { payload: null, error: null, summary: null };

  const allowed = recoveriesForEvent(eventType).some((r) => r.id === recovery);
  if (!allowed) {
    return { payload: null, error: "That recovery does not apply to the selected disruption type.", summary: null };
  }

  if (recovery === "activate_alternative_supplier") {
    const alt = alternativeSupplierId(net, target);
    if (!alt) {
      return {
        payload: null,
        error: `No other supplier in the twin shares a SKU with ${target}.`,
        summary: null,
      };
    }
    return {
      payload: {
        recovery_type: recovery,
        start_day: recoveryDay,
        target_node_id: target,
        alternative_supplier_id: alt,
      },
      error: null,
      summary: `Activate ${alt} as alternate for ${target}`,
    };
  }

  if (recovery === "restore_supplier" || recovery === "restore_factory") {
    return {
      payload: { recovery_type: recovery, start_day: recoveryDay, target_node_id: target },
      error: null,
      summary: `Restore ${target} from day ${recoveryDay}`,
    };
  }

  if (recovery === "expedite_route") {
    return {
      payload: {
        recovery_type: recovery,
        start_day: recoveryDay,
        target_node_id: target,
        transit_days_saved: 1,
        unit_premium: 0.5,
      },
      error: null,
      summary: `Expedite ${target} (−1 transit day)`,
    };
  }

  if (recovery === "increase_route_capacity") {
    return {
      payload: {
        recovery_type: recovery,
        start_day: recoveryDay,
        target_node_id: target,
        capacity_multiplier: 1.5,
      },
      error: null,
      summary: `Raise ${target} capacity ×1.5`,
    };
  }

  if (recovery === "reallocate_inventory") {
    const dest = otherWarehouseId(net, target);
    if (!dest) {
      return { payload: null, error: "Need a second warehouse to reallocate into.", summary: null };
    }
    const sku = skuForReallocate(net, target);
    const onHand = ((net.warehouses as WarehouseRow[]).find((w) => w.warehouse_id === target)?.current_inventory?.[
      sku
    ] ?? 0) as number;
    const quantity = Math.max(1, Math.round(Math.min(80, onHand * 0.2 || 80)));
    return {
      payload: {
        recovery_type: recovery,
        start_day: recoveryDay,
        source_node_id: target,
        destination_node_id: dest,
        sku,
        quantity,
        unit_premium: 1.5,
      },
      error: null,
      summary: `Move ${quantity} ${sku} ${target} → ${dest}`,
    };
  }

  return { payload: null, error: `Unknown recovery ${recovery}`, summary: null };
}
