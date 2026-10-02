"""Helpers for constructing small deterministic networks."""

from app.domain.models import (
    Customer,
    Factory,
    MaterialRequirement,
    NetworkSnapshot,
    Supplier,
    TransportationRoute,
    Warehouse,
)


def linear_network(
    *,
    supplier_capacity: float = 100,
    lead_time: int = 1,
    factory_capacity: float = 50,
    factory_materials: float = 200,
    warehouse_comp: float = 400,
    warehouse_fg: float = 80,
    transit: int = 1,
    demand: float = 40,
    alt_supplier: bool = False,
) -> NetworkSnapshot:
    suppliers = [
        Supplier(
            supplier_id="SUP-A",
            name="Primary",
            reliability_score=0.8,
            capacity_per_day=supplier_capacity,
            lead_time_days=lead_time,
            unit_cost=10,
            available=True,
            risk_level="medium",
            sku="COMP-A",
            preferred_for_sku=True,
        )
    ]
    if alt_supplier:
        suppliers.append(
            Supplier(
                supplier_id="SUP-B",
                name="Alternate",
                reliability_score=0.9,
                capacity_per_day=80,
                lead_time_days=1,
                unit_cost=16,
                available=True,
                risk_level="low",
                sku="COMP-A",
                preferred_for_sku=False,
            )
        )
    routes = [
        TransportationRoute(
            route_id="R-SUP",
            name="Sup→WH",
            source_node_id="SUP-A",
            destination_node_id="WH-1",
            transit_time_days=transit,
            capacity_per_day=500,
            cost_per_unit=1.0,
        ),
        TransportationRoute(
            route_id="R-MAT",
            name="WH→FAC",
            source_node_id="WH-1",
            destination_node_id="FAC-1",
            transit_time_days=1,
            capacity_per_day=500,
            cost_per_unit=0.5,
        ),
        TransportationRoute(
            route_id="R-FG",
            name="FAC→FG",
            source_node_id="FAC-1",
            destination_node_id="WH-FG",
            transit_time_days=1,
            capacity_per_day=200,
            cost_per_unit=0.5,
        ),
        TransportationRoute(
            route_id="R-CUS",
            name="FG→CUS",
            source_node_id="WH-FG",
            destination_node_id="CUS-1",
            transit_time_days=1,
            capacity_per_day=200,
            cost_per_unit=0.8,
        ),
    ]
    if alt_supplier:
        routes.insert(
            1,
            TransportationRoute(
                route_id="R-SUPB",
                name="Alt→WH",
                source_node_id="SUP-B",
                destination_node_id="WH-1",
                transit_time_days=1,
                capacity_per_day=200,
                cost_per_unit=1.2,
            ),
        )
    return NetworkSnapshot(
        network_id="test-linear",
        name="test",
        finished_good_sku="FG-WIDGET",
        unit_revenue=50.0,
        assumptions=["test network"],
        suppliers=suppliers,
        factories=[
            Factory(
                factory_id="FAC-1",
                name="Plant",
                production_capacity_per_day=factory_capacity,
                current_production_per_day=factory_capacity,
                required_materials=[MaterialRequirement(sku="COMP-A", qty_per_unit=1.0)],
                output_sku="FG-WIDGET",
            )
        ],
        warehouses=[
            Warehouse(
                warehouse_id="WH-1",
                name="Materials",
                current_inventory={"COMP-A": warehouse_comp, "FG-WIDGET": 0},
                maximum_capacity=10000,
                safety_stock={"COMP-A": 20},
            ),
            Warehouse(
                warehouse_id="WH-FG",
                name="FG",
                current_inventory={"FG-WIDGET": warehouse_fg, "COMP-A": 0},
                maximum_capacity=5000,
                safety_stock={"FG-WIDGET": 10},
            ),
        ],
        routes=routes,
        customers=[
            Customer(
                customer_id="CUS-1",
                name="Buyer",
                daily_demand=demand,
                priority=1,
                outstanding_orders=0,
                unit_revenue=50.0,
            )
        ],
    )
