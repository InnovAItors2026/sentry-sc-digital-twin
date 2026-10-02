from app.domain.models import Disruption, RecoveryIntervention
from app.simulation.engine import DiscreteTimeSimulator
from tests.conftest import linear_network


sim = DiscreteTimeSimulator()


def _inv_values(result):
    for d in result["daily"]:
        for qty in d.inventory_by_sku.values():
            yield qty


def test_no_disruption_marks_no_affected_nodes():
    net = linear_network()
    compared = sim.run_with_baseline(net, 8, [])
    assert compared["affected_nodes"] == []
    assert compared["propagation_path"] == []


def test_inventory_never_negative():
    net = linear_network()
    result = sim.run(net, 20, [Disruption(event_type="supplier_outage", target_node_id="SUP-A", start_day=2, duration_days=8)])
    assert all(q >= -1e-9 for q in _inv_values(result))


def test_production_constrained_by_materials():
    net = linear_network(warehouse_comp=0, factory_materials=0, supplier_capacity=0)
    result = sim.run(net, 6)
    later = [d for d in result["daily"] if d.node_id == "FAC-1" and d.day >= 3]
    assert later
    assert all(d.production <= d.planned_production + 1e-6 for d in later)
    starved = [d for d in later if d.production + 1e-6 < d.planned_production]
    assert starved, "Factory should starve once BOM inventory is exhausted"


def test_transport_delay_shifts_arrival():
    net = linear_network(warehouse_fg=0, warehouse_comp=800, demand=10)
    base = sim.run(net, 12, [])
    delayed = sim.run(
        net,
        12,
        [
            Disruption(
                event_type="transportation_delay",
                target_node_id="R-CUS",
                start_day=1,
                duration_days=12,
                extra_transit_days=3,
            )
        ],
    )
    base_arrivals = [d.day for d in base["daily"] if d.node_id == "CUS-1" and d.fulfilled > 0]
    delay_arrivals = [d.day for d in delayed["daily"] if d.node_id == "CUS-1" and d.fulfilled > 0]
    if base_arrivals and delay_arrivals:
        assert min(delay_arrivals) >= min(base_arrivals)


def test_supplier_outage_stops_preferred_replenishment():
    net = linear_network(supplier_capacity=100, warehouse_comp=50)
    outage = sim.run(
        net,
        10,
        [Disruption(event_type="supplier_outage", target_node_id="SUP-A", start_day=1, duration_days=10, capacity_factor=0)],
    )
    assert outage["procurement_units_by_supplier"].get("SUP-A", 0) == 0


def test_demand_spike_increases_total_demand():
    net = linear_network(demand=40)
    base = sim.run(net, 10, [])
    spiked = sim.run(
        net,
        10,
        [
            Disruption(
                event_type="demand_spike",
                target_node_id="CUS-1",
                start_day=1,
                duration_days=10,
                demand_increase_pct=50,
            )
        ],
    )
    assert spiked["metrics"].total_demand > base["metrics"].total_demand * 1.2


def test_factory_shutdown_reduces_production():
    net = linear_network()
    base = sim.run(net, 8, [])
    shut = sim.run(
        net,
        8,
        [
            Disruption(
                event_type="factory_shutdown",
                target_node_id="FAC-1",
                start_day=1,
                duration_days=8,
                capacity_factor=0.0,
            )
        ],
    )
    base_prod = sum(d.production for d in base["daily"] if d.node_id == "FAC-1")
    shut_prod = sum(d.production for d in shut["daily"] if d.node_id == "FAC-1")
    assert shut_prod < base_prod * 0.2


def test_warehouse_downtime_defers_inbound():
    net = linear_network()
    result = sim.run(
        net,
        6,
        [
            Disruption(
                event_type="warehouse_disruption",
                target_node_id="WH-1",
                start_day=1,
                duration_days=3,
                capacity_factor=0.0,
            )
        ],
    )
    assert any(e.category == "delay" or "downtime" in e.message.lower() for e in result["events"])
    down_days = [d for d in result["daily"] if d.node_id == "WH-1" and d.day <= 3]
    assert any(not d.available for d in down_days)


def test_activate_alternative_supplier_restores_some_flow():
    net = linear_network(alt_supplier=True, warehouse_comp=40, supplier_capacity=100)
    disrupted = sim.run(
        net,
        16,
        [Disruption(event_type="supplier_outage", target_node_id="SUP-A", start_day=1, duration_days=16, capacity_factor=0)],
    )
    recovered = sim.run(
        net,
        16,
        [Disruption(event_type="supplier_outage", target_node_id="SUP-A", start_day=1, duration_days=16, capacity_factor=0)],
        [
            RecoveryIntervention(
                recovery_type="activate_alternative_supplier",
                start_day=1,
                target_node_id="SUP-A",
                alternative_supplier_id="SUP-B",
            )
        ],
    )
    assert recovered["procurement_units_by_supplier"].get("SUP-B", 0) > 0
    assert recovered["procurement_units_by_supplier"].get("SUP-A", 0) == 0
    rec_prod = sum(d.production for d in recovered["daily"] if d.node_id == "FAC-1")
    dis_prod = sum(d.production for d in disrupted["daily"] if d.node_id == "FAC-1")
    assert rec_prod >= dis_prod


def test_baseline_unchanged_when_disrupted_scenario_runs():
    net = linear_network()
    snapshot = net.model_dump()
    sim.run_with_baseline(
        net,
        10,
        [Disruption(event_type="supplier_outage", target_node_id="SUP-A", start_day=2, duration_days=5)],
    )
    assert net.model_dump() == snapshot
    assert net.suppliers[0].available is True
    assert net.suppliers[0].capacity_per_day == 100


def test_two_baselines_are_identical():
    net = linear_network()
    a = sim.run(net, 12, [])
    b = sim.run(net, 12, [])
    assert a["metrics"].model_dump() == b["metrics"].model_dump()
    assert [d.model_dump() for d in a["daily"]] == [d.model_dump() for d in b["daily"]]


def test_cascading_outage_impacts_factory_and_customer():
    net = linear_network(warehouse_comp=30, warehouse_fg=20, demand=40, factory_capacity=50)
    compared = sim.run_with_baseline(
        net,
        18,
        [Disruption(event_type="supplier_outage", target_node_id="SUP-A", start_day=1, duration_days=18, capacity_factor=0)],
    )
    affected_ids = {n["node_id"] for n in compared["affected_nodes"]}
    assert "FAC-1" in affected_ids or any(
        d["production"] < d["planned_production"] - 1e-6
        for d in compared["daily_timeline"]
        if d["node_id"] == "FAC-1"
    )
    assert compared["scenario_metrics"]["unfulfilled_demand"] >= compared["baseline_metrics"]["unfulfilled_demand"]
    assert compared["scenario_metrics"]["service_level_pct"] <= compared["baseline_metrics"]["service_level_pct"] + 1e-6


def test_service_level_formula():
    net = linear_network(demand=10, warehouse_fg=500)
    result = sim.run(net, 5, [])
    m = result["metrics"]
    if m.total_demand:
        expected = m.total_units_delivered / m.total_demand * 100
        assert abs(m.service_level_pct - expected) < 0.05


def test_disconnected_supplier_does_not_crash():
    net = linear_network()
    net.routes = [r for r in net.routes if r.route_id != "R-SUP"]
    result = sim.run(net, 6, [])
    assert result["metrics"].total_demand > 0


def test_reallocate_inventory_moves_stock():
    net = linear_network(warehouse_fg=100)
    result = sim.run(
        net,
        3,
        recoveries=[
            RecoveryIntervention(
                recovery_type="reallocate_inventory",
                start_day=1,
                sku="FG-WIDGET",
                quantity=25,
                source_node_id="WH-FG",
                destination_node_id="WH-1",
                unit_premium=2.0,
            )
        ],
    )
    assert result["extra_intervention_cost"] >= 0
    assert any("Reallocated" in e.message for e in result["events"])


def test_expedite_route_accrues_premium():
    net = linear_network(warehouse_fg=200, demand=40)
    base = sim.run(net, 5)
    expedited = sim.run(
        net,
        5,
        recoveries=[
            RecoveryIntervention(
                recovery_type="expedite_route",
                start_day=1,
                target_node_id="R-CUS",
                transit_days_saved=1,
                unit_premium=2.0,
            )
        ],
    )
    assert expedited["extra_intervention_cost"] > 0
    assert expedited["extra_intervention_cost"] >= base["extra_intervention_cost"]
    compared = sim.run_with_baseline(
        net,
        5,
        recoveries=[
            RecoveryIntervention(
                recovery_type="expedite_route",
                start_day=1,
                target_node_id="R-CUS",
                transit_days_saved=1,
                unit_premium=2.0,
            )
        ],
    )
    assert compared["scenario_metrics"]["expedite_and_reallocation_cost"] > 0
    assert compared["scenario_metrics"]["estimated_disruption_cost"] is not None


def test_restore_supplier_overrides_outage():
    net = linear_network(warehouse_comp=10, supplier_capacity=80)
    out = sim.run(
        net,
        10,
        [Disruption(event_type="supplier_outage", target_node_id="SUP-A", start_day=1, duration_days=10, capacity_factor=0)],
    )
    restored = sim.run(
        net,
        10,
        [Disruption(event_type="supplier_outage", target_node_id="SUP-A", start_day=1, duration_days=10, capacity_factor=0)],
        [RecoveryIntervention(recovery_type="restore_supplier", start_day=3, target_node_id="SUP-A")],
    )
    assert any(d.available for d in restored["daily"] if d.node_id == "SUP-A" and d.day >= 3)
    assert not any(d.available for d in out["daily"] if d.node_id == "SUP-A")
    assert restored["procurement_units_by_supplier"].get("SUP-A", 0) > out["procurement_units_by_supplier"].get("SUP-A", 0)


def test_restore_factory_overrides_shutdown():
    net = linear_network(warehouse_comp=400, warehouse_fg=20, demand=40)
    shut = sim.run(
        net,
        8,
        [Disruption(event_type="factory_shutdown", target_node_id="FAC-1", start_day=1, duration_days=8, capacity_factor=0)],
    )
    restored = sim.run(
        net,
        8,
        [Disruption(event_type="factory_shutdown", target_node_id="FAC-1", start_day=1, duration_days=8, capacity_factor=0)],
        [RecoveryIntervention(recovery_type="restore_factory", start_day=2, target_node_id="FAC-1")],
    )
    shut_prod = sum(d.production for d in shut["daily"] if d.node_id == "FAC-1")
    rest_prod = sum(d.production for d in restored["daily"] if d.node_id == "FAC-1")
    assert rest_prod > shut_prod
    assert any(d.available for d in restored["daily"] if d.node_id == "FAC-1" and d.day >= 2)


def test_increase_route_capacity_ships_more_than_constrained_baseline():
    net = linear_network(warehouse_fg=400, demand=80, factory_capacity=80)
    for r in net.routes:
        if r.route_id == "R-CUS":
            r.capacity_per_day = 10
    constrained = sim.run(net, 6)
    boosted = sim.run(
        net,
        6,
        recoveries=[
            RecoveryIntervention(
                recovery_type="increase_route_capacity",
                start_day=1,
                target_node_id="R-CUS",
                capacity_multiplier=5.0,
            )
        ],
    )
    assert boosted["metrics"].total_units_delivered > constrained["metrics"].total_units_delivered
