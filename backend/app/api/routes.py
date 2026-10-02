"""REST API for the digital twin and simulation engine."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.adapters.recovery import RecoveryOptimizationAdapter
from app.adapters.risk import RiskPredictionAdapter
from app.api.schemas import (
    CompareRequest,
    CompareResponse,
    HealthResponse,
    NetworkResponse,
    ScenarioCreateRequest,
    ScenarioSummary,
    SimulateResponse,
)
from app.domain.models import Disruption
from app.simulation.engine import DiscreteTimeSimulator
from app.store import store

router = APIRouter()
simulator = DiscreteTimeSimulator()
risk_adapter = RiskPredictionAdapter()
recovery_adapter = RecoveryOptimizationAdapter()


def _graph(net) -> tuple[list, list]:
    nodes = []
    for s in net.suppliers:
        nodes.append(
            {
                "id": s.supplier_id,
                "type": "supplier",
                "label": s.name,
                "data": s.model_dump(),
            }
        )
    for f in net.factories:
        nodes.append({"id": f.factory_id, "type": "factory", "label": f.name, "data": f.model_dump()})
    for w in net.warehouses:
        nodes.append(
            {
                "id": w.warehouse_id,
                "type": "warehouse",
                "label": w.name,
                "data": {**w.model_dump(), "total_inventory": w.total_inventory},
            }
        )
    for c in net.customers:
        nodes.append({"id": c.customer_id, "type": "customer", "label": c.name, "data": c.model_dump()})
    edges = [
        {
            "id": r.route_id,
            "source": r.source_node_id,
            "target": r.destination_node_id,
            "label": r.name,
            "data": r.model_dump(),
        }
        for r in net.routes
    ]
    return nodes, edges


def _inventory_overview(net) -> list[dict]:
    rows = []
    for w in net.warehouses:
        rows.append(
            {
                "warehouse_id": w.warehouse_id,
                "name": w.name,
                "total_inventory": w.total_inventory,
                "maximum_capacity": w.maximum_capacity,
                "utilization_pct": round(100.0 * w.total_inventory / w.maximum_capacity, 1),
                "by_sku": w.current_inventory,
            }
        )
    return rows


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="sentry-sc-simulation", version="0.1.0")


@router.get("/network", response_model=NetworkResponse)
def get_network() -> NetworkResponse:
    net = store.baseline_network
    nodes, edges = _graph(net)
    return NetworkResponse(
        network_id=net.network_id,
        name=net.name,
        finished_good_sku=net.finished_good_sku,
        unit_revenue=net.unit_revenue,
        counts={
            "suppliers": len(net.suppliers),
            "factories": len(net.factories),
            "warehouses": len(net.warehouses),
            "routes": len(net.routes),
            "customers": len(net.customers),
        },
        suppliers=net.suppliers,
        factories=net.factories,
        warehouses=net.warehouses,
        routes=net.routes,
        customers=net.customers,
        graph_nodes=nodes,
        graph_edges=edges,
        assumptions=net.assumptions,
        inventory_overview=_inventory_overview(net),
        overall_status="normal",
    )


@router.get("/network/{node_id}")
def get_node(node_id: str):
    net = store.baseline_network
    node = net.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
    return {
        "node": node.model_dump(),
        "node_type": net.node_type_of(node_id).value if net.node_type_of(node_id) else "route",
        "incoming": [r.model_dump() for r in net.incoming_routes(node_id)],
        "outgoing": [r.model_dump() for r in net.outgoing_routes(node_id)],
    }


@router.get("/scenarios", response_model=list[ScenarioSummary])
def list_scenarios() -> list[ScenarioSummary]:
    return [
        ScenarioSummary(
            scenario_id=s.scenario_id,
            name=s.name,
            horizon_days=s.horizon_days,
            disruption_count=len(s.disruptions),
            recovery_count=len(s.recoveries),
            simulated=s.results is not None,
            notes=s.notes,
        )
        for s in store.list_scenarios()
    ]


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: str):
    rec = store.get(scenario_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return {
        "scenario_id": rec.scenario_id,
        "name": rec.name,
        "horizon_days": rec.horizon_days,
        "disruptions": [d.model_dump() for d in rec.disruptions],
        "recoveries": [r.model_dump() for r in rec.recoveries],
        "notes": rec.notes,
        "simulated": rec.results is not None,
    }


@router.post("/scenarios", response_model=ScenarioSummary, status_code=201)
def create_scenario(body: ScenarioCreateRequest) -> ScenarioSummary:
    disruptions: list[Disruption] = list(body.disruptions)
    recoveries = list(body.recoveries)
    for pred in body.ingested_predictions:
        try:
            disruptions.append(risk_adapter.to_disruption(pred))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body.ingested_recoveries:
        try:
            recoveries.extend(
                recovery_adapter.to_interventions({"interventions": body.ingested_recoveries})
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    rec = store.create(body.name, body.horizon_days, disruptions, recoveries, body.notes)
    return ScenarioSummary(
        scenario_id=rec.scenario_id,
        name=rec.name,
        horizon_days=rec.horizon_days,
        disruption_count=len(rec.disruptions),
        recovery_count=len(rec.recoveries),
        simulated=False,
        notes=rec.notes,
    )


@router.post("/scenarios/{scenario_id}/simulate", response_model=SimulateResponse)
def simulate(scenario_id: str) -> SimulateResponse:
    rec = store.get(scenario_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    try:
        # Always simulate against a fresh copy of the baseline twin.
        results = simulator.run_with_baseline(
            store.baseline_network,
            rec.horizon_days,
            rec.disruptions,
            rec.recoveries,
            scenario_id=rec.scenario_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store.save_results(scenario_id, results)
    return SimulateResponse(**results)


@router.get("/scenarios/{scenario_id}/results", response_model=SimulateResponse)
def results(scenario_id: str) -> SimulateResponse:
    rec = store.get(scenario_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    if rec.results is None:
        raise HTTPException(status_code=404, detail="Scenario has not been simulated")
    return SimulateResponse(**rec.results)


@router.get("/scenarios/{scenario_id}/timeline")
def timeline(scenario_id: str):
    rec = store.get(scenario_id)
    if rec is None or rec.results is None:
        raise HTTPException(status_code=404, detail="Simulated scenario not found")
    return {
        "scenario_id": scenario_id,
        "daily_timeline": rec.results["daily_timeline"],
        "baseline_daily_timeline": rec.results["baseline_daily_timeline"],
        "events": rec.results["events"],
    }


@router.get("/scenarios/{scenario_id}/affected-nodes")
def affected(scenario_id: str):
    rec = store.get(scenario_id)
    if rec is None or rec.results is None:
        raise HTTPException(status_code=404, detail="Simulated scenario not found")
    return {
        "scenario_id": scenario_id,
        "affected_nodes": rec.results["affected_nodes"],
        "propagation_path": rec.results.get("propagation_path", []),
    }


@router.post("/scenarios/compare", response_model=CompareResponse)
def compare(body: CompareRequest) -> CompareResponse:
    rows = []
    for sid in body.scenario_ids:
        rec = store.get(sid)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"Scenario {sid} not found")
        if rec.results is None:
            results = simulator.run_with_baseline(
                store.baseline_network,
                rec.horizon_days,
                rec.disruptions,
                rec.recoveries,
                scenario_id=rec.scenario_id,
            )
            store.save_results(sid, results)
        else:
            results = rec.results
        m = results["scenario_metrics"]
        rows.append(
            {
                "scenario_id": sid,
                "name": rec.name,
                "service_level_pct": m.get("service_level_pct"),
                "estimated_disruption_cost": m.get("estimated_disruption_cost"),
                "production_shortfall": m.get("production_shortfall"),
                "unfulfilled_demand": m.get("unfulfilled_demand"),
                "average_delivery_delay": m.get("average_delivery_delay"),
                "recovery_day": m.get("recovery_day"),
                "affected_customer_count": m.get("affected_customer_count"),
                "total_transportation_cost": m.get("total_transportation_cost"),
            }
        )
    trade_offs = []
    if len(rows) >= 2:
        best_service = max(rows, key=lambda r: r["service_level_pct"] or 0)
        lowest_cost = min(rows, key=lambda r: r["estimated_disruption_cost"] if r["estimated_disruption_cost"] is not None else 1e18)
        trade_offs.append(
            f"{best_service['name']} preserves the highest modeled service level "
            f"({best_service['service_level_pct']}%)."
        )
        trade_offs.append(
            f"{lowest_cost['name']} has the lowest modeled disruption cost "
            f"(${lowest_cost['estimated_disruption_cost']})."
        )
        trade_offs.append(
            "Higher service can require more expensive alternate supply or expedite premiums. "
            "The model does not certify that an intervention is operationally feasible beyond checked constraints."
        )
    return CompareResponse(scenarios=rows, trade_offs=trade_offs)
