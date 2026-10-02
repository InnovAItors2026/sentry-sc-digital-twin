"""Core supply-chain digital twin data model.

Extra fields beyond the Hackfest entity list exist only where material-flow
simulation requires them (SKU, BOM, output product, unit revenue).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class NodeType(str, Enum):
    SUPPLIER = "supplier"
    FACTORY = "factory"
    WAREHOUSE = "warehouse"
    CUSTOMER = "customer"


class DisruptionType(str, Enum):
    SUPPLIER_OUTAGE = "supplier_outage"
    FACTORY_SHUTDOWN = "factory_shutdown"
    TRANSPORTATION_DELAY = "transportation_delay"
    WAREHOUSE_DISRUPTION = "warehouse_disruption"
    DEMAND_SPIKE = "demand_spike"


class RecoveryType(str, Enum):
    RESTORE_SUPPLIER = "restore_supplier"
    ACTIVATE_ALTERNATIVE_SUPPLIER = "activate_alternative_supplier"
    EXPEDITE_ROUTE = "expedite_route"
    INCREASE_ROUTE_CAPACITY = "increase_route_capacity"
    REALLOCATE_INVENTORY = "reallocate_inventory"
    RESTORE_FACTORY = "restore_factory"


class NodeStatus(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    UNAVAILABLE = "unavailable"


class MaterialRequirement(BaseModel):
    sku: str
    qty_per_unit: float = Field(gt=0)


class Supplier(BaseModel):
    supplier_id: str
    name: str
    reliability_score: float = Field(ge=0, le=1)
    capacity_per_day: float = Field(ge=0)
    lead_time_days: int = Field(ge=0)
    unit_cost: float = Field(ge=0)
    available: bool = True
    risk_level: str = "medium"
    sku: str
    preferred_for_sku: bool = False

    @property
    def node_id(self) -> str:
        return self.supplier_id


class Factory(BaseModel):
    factory_id: str
    name: str
    production_capacity_per_day: float = Field(ge=0)
    current_production_per_day: float = Field(ge=0)
    required_materials: list[MaterialRequirement]
    available: bool = True
    output_sku: str = "FG-WIDGET"

    @property
    def node_id(self) -> str:
        return self.factory_id

    @property
    def bom(self) -> dict[str, float]:
        return {item.sku: item.qty_per_unit for item in self.required_materials}


class Warehouse(BaseModel):
    warehouse_id: str
    name: str
    current_inventory: dict[str, float] = Field(default_factory=dict)
    maximum_capacity: float = Field(gt=0)
    safety_stock: dict[str, float] = Field(default_factory=dict)
    available: bool = True

    @property
    def node_id(self) -> str:
        return self.warehouse_id

    @property
    def total_inventory(self) -> float:
        return float(sum(self.current_inventory.values()))


class TransportationRoute(BaseModel):
    route_id: str
    name: str
    source_node_id: str
    destination_node_id: str
    transit_time_days: int = Field(ge=0)
    capacity_per_day: float = Field(ge=0)
    cost_per_unit: float = Field(ge=0)
    available: bool = True

    @property
    def node_id(self) -> str:
        return self.route_id

    @model_validator(mode="after")
    def distinct_endpoints(self) -> TransportationRoute:
        if self.source_node_id == self.destination_node_id:
            raise ValueError("Route source and destination must differ")
        return self


class Customer(BaseModel):
    customer_id: str
    name: str
    daily_demand: float = Field(ge=0)
    priority: int = Field(ge=1, le=5)
    outstanding_orders: float = Field(ge=0, default=0)
    demand_sku: str = "FG-WIDGET"
    unit_revenue: float = Field(ge=0, default=75.0)

    @property
    def node_id(self) -> str:
        return self.customer_id


class Disruption(BaseModel):
    disruption_id: str | None = None
    event_type: DisruptionType
    target_node_id: str
    start_day: int = Field(ge=1)
    duration_days: int = Field(ge=1)
    capacity_factor: float | None = Field(default=None, ge=0, le=1)
    extra_transit_days: int | None = Field(default=None, ge=0)
    unavailable_inventory_pct: float | None = Field(default=None, ge=0, le=100)
    demand_increase_pct: float | None = Field(default=None, ge=0)
    source: str = "user_configured"

    @model_validator(mode="after")
    def type_specific_fields(self) -> Disruption:
        if self.event_type == DisruptionType.TRANSPORTATION_DELAY and self.extra_transit_days is None:
            raise ValueError("Transportation delay requires extra_transit_days")
        if self.event_type == DisruptionType.DEMAND_SPIKE and self.demand_increase_pct is None:
            raise ValueError("Demand spike requires demand_increase_pct")
        if (
            self.event_type == DisruptionType.WAREHOUSE_DISRUPTION
            and self.unavailable_inventory_pct is None
            and self.capacity_factor is None
        ):
            raise ValueError(
                "Warehouse disruption requires unavailable_inventory_pct or capacity_factor (downtime)"
            )
        return self


class RecoveryIntervention(BaseModel):
    intervention_id: str | None = None
    recovery_type: RecoveryType
    start_day: int = Field(ge=1)
    target_node_id: str | None = None
    alternative_supplier_id: str | None = None
    transit_days_saved: int | None = Field(default=None, ge=0)
    capacity_multiplier: float | None = Field(default=None, gt=0)
    sku: str | None = None
    quantity: float | None = Field(default=None, ge=0)
    source_node_id: str | None = None
    destination_node_id: str | None = None
    unit_premium: float = Field(default=0, ge=0)
    source: str = "user_configured"


class Shipment(BaseModel):
    shipment_id: str
    sku: str
    quantity: float
    origin_id: str
    destination_id: str
    route_id: str
    depart_day: int
    arrival_day: int
    unit_transport_cost: float = 0
    unit_product_cost: float = 0


class DailyNodeState(BaseModel):
    day: int
    node_id: str
    node_type: NodeType
    inventory_by_sku: dict[str, float] = Field(default_factory=dict)
    production: float = 0
    planned_production: float = 0
    received: float = 0
    shipped: float = 0
    demand: float = 0
    fulfilled: float = 0
    unfulfilled_backlog: float = 0
    stockout: bool = False
    safety_stock_violation: bool = False
    available: bool = True
    status: NodeStatus = NodeStatus.NORMAL
    notes: list[str] = Field(default_factory=list)


class SimulationEvent(BaseModel):
    day: int
    node_id: str
    category: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ImpactMetrics(BaseModel):
    total_demand: float
    total_units_delivered: float
    unfulfilled_demand: float
    service_level_pct: float | None
    stockout_days: int
    minimum_inventory: float | None
    production_shortfall: float
    total_transportation_cost: float
    estimated_disruption_cost: float | None
    average_delivery_delay: float | None
    affected_customer_count: int | None
    recovery_day: int | None
    lost_revenue: float | None = None
    excess_procurement_cost: float | None = None
    excess_transport_cost: float | None = None
    expedite_and_reallocation_cost: float = 0
    cost_notes: list[str] = Field(default_factory=list)


class AffectedNode(BaseModel):
    node_id: str
    node_type: str
    impact_summary: str
    reasons: list[str] = Field(default_factory=list)
    deviation_score: float = 0


class NetworkSnapshot(BaseModel):
    network_id: str = "demo-northwind-manufacturing"
    name: str = "Northwind Precision Manufacturing — synthetic twin"
    finished_good_sku: str = "FG-WIDGET"
    unit_revenue: float = 75.0
    suppliers: list[Supplier]
    factories: list[Factory]
    warehouses: list[Warehouse]
    routes: list[TransportationRoute]
    customers: list[Customer]
    assumptions: list[str] = Field(default_factory=list)

    @field_validator("routes")
    @classmethod
    def routes_reference_existing_nodes(cls, routes: list[TransportationRoute], info):
        return routes

    def node_ids(self) -> set[str]:
        ids = {s.supplier_id for s in self.suppliers}
        ids |= {f.factory_id for f in self.factories}
        ids |= {w.warehouse_id for w in self.warehouses}
        ids |= {c.customer_id for c in self.customers}
        return ids

    def get_node(self, node_id: str) -> Supplier | Factory | Warehouse | Customer | TransportationRoute | None:
        for collection in (self.suppliers, self.factories, self.warehouses, self.customers, self.routes):
            for item in collection:
                if item.node_id == node_id:
                    return item
        return None

    def node_type_of(self, node_id: str) -> NodeType | None:
        if any(s.supplier_id == node_id for s in self.suppliers):
            return NodeType.SUPPLIER
        if any(f.factory_id == node_id for f in self.factories):
            return NodeType.FACTORY
        if any(w.warehouse_id == node_id for w in self.warehouses):
            return NodeType.WAREHOUSE
        if any(c.customer_id == node_id for c in self.customers):
            return NodeType.CUSTOMER
        return None

    @model_validator(mode="after")
    def validate_graph(self) -> NetworkSnapshot:
        ids = self.node_ids()
        duplicates = []
        seen: set[str] = set()
        for nid in (
            [s.supplier_id for s in self.suppliers]
            + [f.factory_id for f in self.factories]
            + [w.warehouse_id for w in self.warehouses]
            + [c.customer_id for c in self.customers]
        ):
            if nid in seen:
                duplicates.append(nid)
            seen.add(nid)
        if duplicates:
            raise ValueError(f"Duplicate node ids: {duplicates}")
        for route in self.routes:
            if route.source_node_id not in ids:
                raise ValueError(f"Route {route.route_id} source {route.source_node_id} does not exist")
            if route.destination_node_id not in ids:
                raise ValueError(f"Route {route.route_id} destination {route.destination_node_id} does not exist")
        return self

    def outgoing_routes(self, node_id: str) -> list[TransportationRoute]:
        return [r for r in self.routes if r.source_node_id == node_id]

    def incoming_routes(self, node_id: str) -> list[TransportationRoute]:
        return [r for r in self.routes if r.destination_node_id == node_id]
