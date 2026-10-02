"""Discrete-time supply-chain simulator.

Daily sequence (deterministic):
1. Apply disruption then recovery modifiers for the day.
2. Land in-transit shipments whose arrival_day == t (defer one day if destination is down or over capacity).
3. Add customer demand to backlog; fulfill from on-hand customer receipts.
4. Produce at factories from on-hand BOM inventory.
5. Push finished goods factory → FG warehouses.
6. Push FG warehouses → DCs and customers (priority order).
7. Push materials warehouses → factories (cover ~3 days of BOM).
8. Pull from suppliers into materials warehouses (preferred sourcing rules).
"""

from __future__ import annotations

import copy
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.domain.models import (
    AffectedNode,
    Customer,
    DailyNodeState,
    Disruption,
    DisruptionType,
    Factory,
    ImpactMetrics,
    NetworkSnapshot,
    NodeStatus,
    NodeType,
    RecoveryIntervention,
    RecoveryType,
    Shipment,
    SimulationEvent,
    Supplier,
    TransportationRoute,
    Warehouse,
)


@dataclass
class DayModifiers:
    supplier_capacity_factor: dict[str, float]
    supplier_available: dict[str, bool]
    factory_capacity_factor: dict[str, float]
    factory_available: dict[str, bool]
    route_extra_transit: dict[str, int]
    route_capacity_factor: dict[str, float]
    route_available: dict[str, bool]
    warehouse_available: dict[str, bool]
    demand_multiplier: dict[str, float]
    alt_suppliers_enabled: set[str]
    route_expedite_premium: dict[str, float] = field(default_factory=dict)
    reallocation_cost: float = 0.0
    expedite_premium_accrued: float = 0.0


@dataclass
class RunState:
    inventories: dict[str, dict[str, float]]
    frozen: dict[str, dict[str, float]]
    pipeline: list[Shipment]
    backlog: dict[str, float]
    fulfilled_total: dict[str, float]
    demand_total: dict[str, float]
    delay_days_weighted: dict[str, float]
    delay_units: dict[str, float]
    production_actual: dict[str, float]
    production_planned: dict[str, float]
    transport_cost: float = 0.0
    procurement_cost: float = 0.0
    procurement_units_by_supplier: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    shipment_seq: int = 0
    frozen_applied: set[str] = field(default_factory=set)
    events: list[SimulationEvent] = field(default_factory=list)
    extra_intervention_cost: float = 0.0
    customer_receipt_lots: dict[str, list[tuple[int, float]]] = field(default_factory=lambda: defaultdict(list))

    def inv(self, node_id: str, sku: str) -> float:
        return self.inventories.setdefault(node_id, {}).get(sku, 0.0)

    def add_inv(self, node_id: str, sku: str, qty: float) -> None:
        bucket = self.inventories.setdefault(node_id, {})
        bucket[sku] = bucket.get(sku, 0.0) + qty
        if bucket[sku] < -1e-9:
            raise RuntimeError(f"Negative inventory at {node_id} sku {sku}: {bucket[sku]}")
        if abs(bucket[sku]) < 1e-9:
            bucket[sku] = 0.0

    def take_inv(self, node_id: str, sku: str, qty: float) -> float:
        available = max(0.0, self.inv(node_id, sku) - self.frozen.get(node_id, {}).get(sku, 0.0))
        taken = min(available, qty)
        if taken > 0:
            self.add_inv(node_id, sku, -taken)
        return taken


class DiscreteTimeSimulator:
    COVER_DAYS = 3.0

    def run(
        self,
        network: NetworkSnapshot,
        horizon_days: int,
        disruptions: list[Disruption] | None = None,
        recoveries: list[RecoveryIntervention] | None = None,
        scenario_id: str = "adhoc",
    ) -> dict[str, Any]:
        if horizon_days < 1:
            raise ValueError("horizon_days must be >= 1")
        net = NetworkSnapshot.model_validate(copy.deepcopy(network.model_dump()))
        disruptions = disruptions or []
        recoveries = recoveries or []
        self._validate_targets(net, disruptions, recoveries)

        state = self._initial_state(net)
        daily: list[DailyNodeState] = []
        feasibility = self._check_recovery_feasibility(net, recoveries, state)

        for day in range(1, horizon_days + 1):
            mods = self._modifiers(net, day, disruptions, recoveries, state)
            state.extra_intervention_cost += mods.reallocation_cost
            self._receive(net, state, day, mods)
            customer_stats = self._customers(net, state, day, mods)
            factory_stats = self._produce(net, state, day, mods)
            route_remaining = {
                r.route_id: r.capacity_per_day * mods.route_capacity_factor.get(r.route_id, 1.0)
                for r in net.routes
            }
            self._ship_finished_goods(net, state, day, mods, route_remaining)
            self._ship_to_customers_and_dc(net, state, day, mods, route_remaining)
            self._ship_materials_to_factories(net, state, day, mods, route_remaining)
            self._pull_from_suppliers(net, state, day, mods, route_remaining)
            state.extra_intervention_cost += mods.expedite_premium_accrued
            daily.extend(self._snapshot_day(net, state, day, mods, customer_stats, factory_stats))

        metrics = self._metrics(net, state, daily, horizon_days)
        return {
            "scenario_id": scenario_id,
            "horizon_days": horizon_days,
            "metrics": metrics,
            "daily": daily,
            "events": state.events,
            "pipeline_remaining": state.pipeline,
            "procurement_units_by_supplier": dict(state.procurement_units_by_supplier),
            "procurement_cost": state.procurement_cost,
            "extra_intervention_cost": state.extra_intervention_cost,
            "feasibility": feasibility,
            "assumptions": list(net.assumptions),
            "network": net,
        }

    def run_with_baseline(
        self,
        network: NetworkSnapshot,
        horizon_days: int,
        disruptions: list[Disruption] | None = None,
        recoveries: list[RecoveryIntervention] | None = None,
        scenario_id: str = "adhoc",
    ) -> dict[str, Any]:
        baseline = self.run(network, horizon_days, [], [], scenario_id=f"{scenario_id}-baseline")
        scenario = self.run(network, horizon_days, disruptions, recoveries, scenario_id=scenario_id)
        scenario_metrics = self._relative_costs(network, baseline, scenario)
        affected, path = self._affected(network, baseline["daily"], scenario["daily"], scenario["events"])
        recovery_day = self._recovery_day(baseline["daily"], scenario["daily"], disruptions or [], horizon_days)
        scenario_metrics.recovery_day = recovery_day
        scenario_metrics.affected_customer_count = len(
            [n for n in affected if n.node_type == NodeType.CUSTOMER.value]
        )
        return {
            "scenario_id": scenario_id,
            "baseline_metrics": baseline["metrics"].model_dump(),
            "scenario_metrics": scenario_metrics.model_dump(),
            "affected_nodes": [n.model_dump() for n in affected],
            "propagation_path": path,
            "daily_timeline": [d.model_dump() for d in scenario["daily"]],
            "baseline_daily_timeline": [d.model_dump() for d in baseline["daily"]],
            "events": [e.model_dump() for e in scenario["events"]],
            "assumptions": scenario["assumptions"],
            "feasibility": scenario["feasibility"],
            "horizon_days": horizon_days,
        }

    def _validate_targets(
        self,
        net: NetworkSnapshot,
        disruptions: list[Disruption],
        recoveries: list[RecoveryIntervention],
    ) -> None:
        ids = net.node_ids()
        route_ids = {r.route_id for r in net.routes}
        for d in disruptions:
            if d.event_type == DisruptionType.TRANSPORTATION_DELAY:
                if d.target_node_id not in route_ids:
                    raise ValueError(f"Unknown route {d.target_node_id}")
            elif d.target_node_id not in ids:
                raise ValueError(f"Unknown disruption target {d.target_node_id}")
            ntype = net.node_type_of(d.target_node_id)
            if d.event_type == DisruptionType.SUPPLIER_OUTAGE and ntype != NodeType.SUPPLIER:
                raise ValueError("supplier_outage target must be a supplier")
            if d.event_type == DisruptionType.FACTORY_SHUTDOWN and ntype != NodeType.FACTORY:
                raise ValueError("factory_shutdown target must be a factory")
            if d.event_type == DisruptionType.WAREHOUSE_DISRUPTION and ntype != NodeType.WAREHOUSE:
                raise ValueError("warehouse_disruption target must be a warehouse")
            if d.event_type == DisruptionType.DEMAND_SPIKE and ntype != NodeType.CUSTOMER:
                raise ValueError("demand_spike target must be a customer")
        for r in recoveries:
            if r.recovery_type == RecoveryType.EXPEDITE_ROUTE and r.target_node_id not in route_ids:
                raise ValueError(f"Unknown route {r.target_node_id}")
            if r.recovery_type == RecoveryType.INCREASE_ROUTE_CAPACITY and r.target_node_id not in route_ids:
                raise ValueError(f"Unknown route {r.target_node_id}")

    def _initial_state(self, net: NetworkSnapshot) -> RunState:
        inventories: dict[str, dict[str, float]] = {}
        for s in net.suppliers:
            inventories[s.supplier_id] = {s.sku: 0.0}
        for f in net.factories:
            inventories[f.factory_id] = {f.output_sku: 0.0}
            for sku, qty_each in f.bom.items():
                # Cover a few production days so plants can run while inbound materials are in transit.
                inventories[f.factory_id][sku] = f.current_production_per_day * qty_each * self.COVER_DAYS
        for w in net.warehouses:
            inventories[w.warehouse_id] = {k: float(v) for k, v in w.current_inventory.items()}
        for c in net.customers:
            inventories[c.customer_id] = {c.demand_sku: 0.0}
        backlog = {c.customer_id: float(c.outstanding_orders) for c in net.customers}
        return RunState(
            inventories=inventories,
            frozen=defaultdict(dict),
            pipeline=[],
            backlog=backlog,
            fulfilled_total=defaultdict(float),
            demand_total=defaultdict(float),
            delay_days_weighted=defaultdict(float),
            delay_units=defaultdict(float),
            production_actual=defaultdict(float),
            production_planned=defaultdict(float),
        )

    def _active(self, day: int, start: int, duration: int | None) -> bool:
        if duration is None:
            return day >= start
        return start <= day < start + duration

    def _modifiers(
        self,
        net: NetworkSnapshot,
        day: int,
        disruptions: list[Disruption],
        recoveries: list[RecoveryIntervention],
        state: RunState,
    ) -> DayModifiers:
        mods = DayModifiers(
            supplier_capacity_factor={s.supplier_id: 1.0 for s in net.suppliers},
            supplier_available={s.supplier_id: s.available for s in net.suppliers},
            factory_capacity_factor={f.factory_id: 1.0 for f in net.factories},
            factory_available={f.factory_id: f.available for f in net.factories},
            route_extra_transit={r.route_id: 0 for r in net.routes},
            route_capacity_factor={r.route_id: 1.0 for r in net.routes},
            route_available={r.route_id: r.available for r in net.routes},
            warehouse_available={w.warehouse_id: w.available for w in net.warehouses},
            demand_multiplier={c.customer_id: 1.0 for c in net.customers},
            alt_suppliers_enabled=set(),
            route_expedite_premium={},
        )
        for d in disruptions:
            if not self._active(day, d.start_day, d.duration_days):
                continue
            tid = d.target_node_id
            if d.event_type == DisruptionType.SUPPLIER_OUTAGE:
                factor = 0.0 if d.capacity_factor is None else d.capacity_factor
                mods.supplier_capacity_factor[tid] = factor
                if factor == 0:
                    mods.supplier_available[tid] = False
                state.events.append(
                    SimulationEvent(
                        day=day,
                        node_id=tid,
                        category="disruption",
                        message=f"Supplier capacity factor {factor} applied",
                    )
                )
            elif d.event_type == DisruptionType.FACTORY_SHUTDOWN:
                factor = 0.0 if d.capacity_factor is None else d.capacity_factor
                mods.factory_capacity_factor[tid] = factor
                if factor == 0:
                    mods.factory_available[tid] = False
                state.events.append(
                    SimulationEvent(
                        day=day,
                        node_id=tid,
                        category="disruption",
                        message=f"Factory production factor {factor} applied",
                    )
                )
            elif d.event_type == DisruptionType.TRANSPORTATION_DELAY:
                extra = d.extra_transit_days or 0
                mods.route_extra_transit[tid] = extra
                if d.capacity_factor is not None:
                    mods.route_capacity_factor[tid] = d.capacity_factor
                    if d.capacity_factor == 0:
                        mods.route_available[tid] = False
                state.events.append(
                    SimulationEvent(
                        day=day,
                        node_id=tid,
                        category="disruption",
                        message=f"Route extra transit {extra} day(s)",
                    )
                )
            elif d.event_type == DisruptionType.WAREHOUSE_DISRUPTION:
                if d.capacity_factor is not None and d.capacity_factor == 0:
                    mods.warehouse_available[tid] = False
                    state.events.append(
                        SimulationEvent(day=day, node_id=tid, category="disruption", message="Warehouse operational downtime")
                    )
                if d.unavailable_inventory_pct:
                    key = f"{d.disruption_id or id(d)}:{tid}"
                    if key not in state.frozen_applied:
                        pct = d.unavailable_inventory_pct / 100.0
                        for sku, qty in list(state.inventories.get(tid, {}).items()):
                            freeze = qty * pct
                            state.frozen[tid][sku] = state.frozen[tid].get(sku, 0.0) + freeze
                        state.frozen_applied.add(key)
                        state.events.append(
                            SimulationEvent(
                                day=day,
                                node_id=tid,
                                category="disruption",
                                message=f"{d.unavailable_inventory_pct}% of on-hand inventory frozen as unavailable",
                            )
                        )
            elif d.event_type == DisruptionType.DEMAND_SPIKE:
                mods.demand_multiplier[tid] = 1.0 + (d.demand_increase_pct or 0) / 100.0
                state.events.append(
                    SimulationEvent(
                        day=day,
                        node_id=tid,
                        category="disruption",
                        message=f"Demand multiplied by {mods.demand_multiplier[tid]:.2f}",
                    )
                )

        # Unfreeze warehouse stock after disruption windows end.
        for d in disruptions:
            if d.event_type != DisruptionType.WAREHOUSE_DISRUPTION:
                continue
            if d.unavailable_inventory_pct and day == d.start_day + d.duration_days:
                tid = d.target_node_id
                state.frozen[tid] = {}
                state.events.append(
                    SimulationEvent(day=day, node_id=tid, category="recovery", message="Frozen warehouse inventory released")
                )

        mods.reallocation_cost = 0.0
        mods.expedite_premium_accrued = 0.0
        for rec in recoveries:
            if day < rec.start_day:
                continue
            if rec.recovery_type == RecoveryType.RESTORE_SUPPLIER and rec.target_node_id:
                mods.supplier_available[rec.target_node_id] = True
                mods.supplier_capacity_factor[rec.target_node_id] = 1.0
            elif rec.recovery_type == RecoveryType.RESTORE_FACTORY and rec.target_node_id:
                mods.factory_available[rec.target_node_id] = True
                mods.factory_capacity_factor[rec.target_node_id] = 1.0
            elif rec.recovery_type == RecoveryType.ACTIVATE_ALTERNATIVE_SUPPLIER:
                if rec.alternative_supplier_id:
                    mods.alt_suppliers_enabled.add(rec.alternative_supplier_id)
                    if day == rec.start_day:
                        state.events.append(
                            SimulationEvent(
                                day=day,
                                node_id=rec.alternative_supplier_id,
                                category="recovery",
                                message="Alternative supplier activated for sourcing",
                            )
                        )
            elif rec.recovery_type == RecoveryType.EXPEDITE_ROUTE and rec.target_node_id:
                saved = rec.transit_days_saved or 1
                mods.route_extra_transit[rec.target_node_id] = min(
                    mods.route_extra_transit.get(rec.target_node_id, 0), -saved
                )
                mods.route_available[rec.target_node_id] = True
                if rec.unit_premium:
                    mods.route_expedite_premium[rec.target_node_id] = rec.unit_premium
            elif rec.recovery_type == RecoveryType.INCREASE_ROUTE_CAPACITY and rec.target_node_id:
                mult = rec.capacity_multiplier or 1.5
                mods.route_capacity_factor[rec.target_node_id] = max(
                    mods.route_capacity_factor.get(rec.target_node_id, 1.0), mult
                )
            elif rec.recovery_type == RecoveryType.REALLOCATE_INVENTORY and day == rec.start_day:
                src = rec.source_node_id
                dst = rec.destination_node_id
                sku = rec.sku or net.finished_good_sku
                qty = rec.quantity or 0
                if src and dst and qty > 0:
                    moved = state.take_inv(src, sku, qty)
                    state.add_inv(dst, sku, moved)
                    cost = moved * rec.unit_premium
                    mods.reallocation_cost += cost
                    state.events.append(
                        SimulationEvent(
                            day=day,
                            node_id=dst,
                            category="recovery",
                            message=f"Reallocated {moved:.1f} {sku} from {src} to {dst}",
                            details={"requested": qty, "moved": moved, "premium": cost},
                        )
                    )
        return mods

    def _check_recovery_feasibility(
        self, net: NetworkSnapshot, recoveries: list[RecoveryIntervention], state: RunState
    ) -> list[dict[str, Any]]:
        results = []
        ids = net.node_ids()
        route_ids = {r.route_id for r in net.routes}
        suppliers = {s.supplier_id: s for s in net.suppliers}
        for rec in recoveries:
            ok = True
            reasons: list[str] = []
            if rec.recovery_type == RecoveryType.ACTIVATE_ALTERNATIVE_SUPPLIER:
                alt = suppliers.get(rec.alternative_supplier_id or "")
                primary = suppliers.get(rec.target_node_id or "")
                if not alt:
                    ok, reasons = False, ["Alternative supplier id is not in the network"]
                elif primary and alt.sku != primary.sku:
                    ok, reasons = False, [f"SKU mismatch: primary {primary.sku} vs alternative {alt.sku}"]
                else:
                    reasons = ["SKU matches. Capacity, lead time, and unit cost remain those of the alternative."]
            elif rec.recovery_type in {RecoveryType.EXPEDITE_ROUTE, RecoveryType.INCREASE_ROUTE_CAPACITY}:
                if rec.target_node_id not in route_ids:
                    ok, reasons = False, ["Route does not exist"]
                else:
                    reasons = ["Route exists. Transit/capacity change is applied only in this scenario."]
            elif rec.recovery_type == RecoveryType.REALLOCATE_INVENTORY:
                if rec.source_node_id not in ids or rec.destination_node_id not in ids:
                    ok, reasons = False, ["Source or destination node missing"]
                else:
                    reasons = [
                        "Move occurs only if source has unfrozen inventory on the start day; destination capacity is enforced on receipt."
                    ]
            elif rec.recovery_type == RecoveryType.RESTORE_SUPPLIER:
                ok = rec.target_node_id in suppliers
                reasons = ["Restore overrides outage modifiers from start_day"] if ok else ["Unknown supplier"]
            elif rec.recovery_type == RecoveryType.RESTORE_FACTORY:
                ok = any(f.factory_id == rec.target_node_id for f in net.factories)
                reasons = ["Restore overrides shutdown modifiers from start_day"] if ok else ["Unknown factory"]
            results.append(
                {
                    "recovery_type": rec.recovery_type.value,
                    "feasible_in_model": ok,
                    "reasons": reasons,
                    "claim": "Model-checked constraints only; not a real-world feasibility certificate.",
                }
            )
        return results

    def _receive(self, net: NetworkSnapshot, state: RunState, day: int, mods: DayModifiers) -> None:
        remaining: list[Shipment] = []
        warehouse_ids = {w.warehouse_id for w in net.warehouses}
        customer_ids = {c.customer_id for c in net.customers}
        for ship in state.pipeline:
            if ship.arrival_day != day:
                remaining.append(ship)
                continue
            dest = ship.destination_id
            if dest in warehouse_ids and not mods.warehouse_available.get(dest, True):
                ship.arrival_day = day + 1
                remaining.append(ship)
                state.events.append(
                    SimulationEvent(
                        day=day,
                        node_id=dest,
                        category="delay",
                        message=f"Inbound shipment of {ship.quantity:.1f} {ship.sku} deferred; warehouse unavailable",
                    )
                )
                continue
            if dest in warehouse_ids:
                wh = next(w for w in net.warehouses if w.warehouse_id == dest)
                current = sum(state.inventories.get(dest, {}).values())
                if current + ship.quantity > wh.maximum_capacity + 1e-6:
                    ship.arrival_day = day + 1
                    remaining.append(ship)
                    continue
            state.add_inv(dest, ship.sku, ship.quantity)
            if dest in customer_ids:
                state.customer_receipt_lots[dest].append((ship.depart_day, ship.quantity))
        state.pipeline = remaining

    def _customers(
        self, net: NetworkSnapshot, state: RunState, day: int, mods: DayModifiers
    ) -> dict[str, dict[str, float]]:
        stats: dict[str, dict[str, float]] = {}
        for c in sorted(net.customers, key=lambda x: x.priority):
            demand_today = c.daily_demand * mods.demand_multiplier.get(c.customer_id, 1.0)
            state.demand_total[c.customer_id] += demand_today
            state.backlog[c.customer_id] += demand_today
            on_hand = state.inv(c.customer_id, c.demand_sku)
            fulfill = min(on_hand, state.backlog[c.customer_id])
            if fulfill > 0:
                state.take_inv(c.customer_id, c.demand_sku, fulfill)
                state.backlog[c.customer_id] -= fulfill
                state.fulfilled_total[c.customer_id] += fulfill
                remaining_fulfill = fulfill
                lots = state.customer_receipt_lots[c.customer_id]
                while remaining_fulfill > 1e-9 and lots:
                    dep, qty = lots[0]
                    used = min(qty, remaining_fulfill)
                    delay = max(0, day - dep)
                    state.delay_days_weighted[c.customer_id] += delay * used
                    state.delay_units[c.customer_id] += used
                    remaining_fulfill -= used
                    if used >= qty - 1e-9:
                        lots.pop(0)
                    else:
                        lots[0] = (dep, qty - used)
            stats[c.customer_id] = {
                "demand": demand_today,
                "fulfilled": fulfill,
                "backlog": state.backlog[c.customer_id],
            }
        return stats

    def _produce(
        self, net: NetworkSnapshot, state: RunState, day: int, mods: DayModifiers
    ) -> dict[str, dict[str, float]]:
        stats: dict[str, dict[str, float]] = {}
        for f in net.factories:
            planned = f.current_production_per_day * mods.factory_capacity_factor.get(f.factory_id, 1.0)
            if not mods.factory_available.get(f.factory_id, True):
                planned = 0.0
            planned = min(planned, f.production_capacity_per_day * mods.factory_capacity_factor.get(f.factory_id, 1.0))
            state.production_planned[f.factory_id] += planned
            if planned <= 0:
                stats[f.factory_id] = {"planned": 0, "actual": 0}
                continue
            max_from_bom = planned
            blocking_sku = None
            blocking_have = 0.0
            blocking_need = 0.0
            for sku, qty_each in f.bom.items():
                have = state.inv(f.factory_id, sku)
                can = have / qty_each if qty_each > 0 else planned
                if can < max_from_bom:
                    max_from_bom = can
                    blocking_sku = sku
                    blocking_have = have
                    blocking_need = planned * qty_each
            actual = max(0.0, max_from_bom)
            if actual + 1e-9 < planned and blocking_sku:
                state.events.append(
                    SimulationEvent(
                        day=day,
                        node_id=f.factory_id,
                        category="production_constraint",
                        message=(
                            f"{f.name} production decreased because required material {blocking_sku} "
                            f"inventory ({blocking_have:.1f}) fell below the quantity needed "
                            f"({blocking_need:.1f}) for planned production of {planned:.1f} units."
                        ),
                        details={
                            "planned": planned,
                            "actual": actual,
                            "blocking_sku": blocking_sku,
                        },
                    )
                )
            for sku, qty_each in f.bom.items():
                state.take_inv(f.factory_id, sku, actual * qty_each)
            state.add_inv(f.factory_id, f.output_sku, actual)
            state.production_actual[f.factory_id] += actual
            stats[f.factory_id] = {"planned": planned, "actual": actual}
        return stats

    def _create_shipment(
        self,
        state: RunState,
        route: TransportationRoute,
        sku: str,
        qty: float,
        day: int,
        extra_transit: int,
        unit_product_cost: float = 0.0,
        transit_override: int | None = None,
    ) -> Shipment:
        state.shipment_seq += 1
        transit = route.transit_time_days if transit_override is None else transit_override
        transit = max(0, transit + extra_transit)
        # Arrivals land at the start of a future day so the daily sequence stays causal.
        arrival = day + max(1, transit)
        ship = Shipment(
            shipment_id=f"SHP-{state.shipment_seq:06d}",
            sku=sku,
            quantity=qty,
            origin_id=route.source_node_id,
            destination_id=route.destination_node_id,
            route_id=route.route_id,
            depart_day=day,
            arrival_day=arrival,
            unit_transport_cost=route.cost_per_unit,
            unit_product_cost=unit_product_cost,
        )
        state.pipeline.append(ship)
        state.transport_cost += qty * route.cost_per_unit
        return ship

    def _ship_on_route(
        self,
        net: NetworkSnapshot,
        state: RunState,
        route: TransportationRoute,
        sku: str,
        qty: float,
        day: int,
        mods: DayModifiers,
        route_remaining: dict[str, float],
        unit_product_cost: float = 0.0,
    ) -> float:
        if qty <= 1e-9:
            return 0.0
        if not mods.route_available.get(route.route_id, True):
            return 0.0
        cap = max(0.0, route_remaining.get(route.route_id, 0.0))
        send = min(qty, cap)
        send = state.take_inv(route.source_node_id, sku, send)
        if send <= 1e-9:
            return 0.0
        extra = mods.route_extra_transit.get(route.route_id, 0)
        self._create_shipment(state, route, sku, send, day, extra, unit_product_cost)
        premium = mods.route_expedite_premium.get(route.route_id, 0.0)
        if premium:
            mods.expedite_premium_accrued += send * premium
        route_remaining[route.route_id] = cap - send
        return send

    def _ship_finished_goods(
        self,
        net: NetworkSnapshot,
        state: RunState,
        day: int,
        mods: DayModifiers,
        route_remaining: dict[str, float],
    ) -> None:
        for f in net.factories:
            fg = f.output_sku
            on_hand = state.inv(f.factory_id, fg)
            routes = [r for r in net.outgoing_routes(f.factory_id) if mods.route_available.get(r.route_id, True)]
            if not routes or on_hand <= 0:
                continue
            share = on_hand / len(routes)
            for r in routes:
                self._ship_on_route(net, state, r, fg, share, day, mods, route_remaining)

    def _ship_to_customers_and_dc(
        self,
        net: NetworkSnapshot,
        state: RunState,
        day: int,
        mods: DayModifiers,
        route_remaining: dict[str, float],
    ) -> None:
        fg = net.finished_good_sku
        customer_ids = {c.customer_id for c in net.customers}
        # Customers first by priority, then warehouse-to-warehouse.
        customer_routes = []
        dc_routes = []
        for r in net.routes:
            if r.destination_node_id in customer_ids:
                customer_routes.append(r)
            elif net.node_type_of(r.source_node_id) == NodeType.WAREHOUSE and net.node_type_of(
                r.destination_node_id
            ) == NodeType.WAREHOUSE:
                dc_routes.append(r)
        cust_priority = {c.customer_id: c.priority for c in net.customers}
        customer_routes.sort(key=lambda r: cust_priority.get(r.destination_node_id, 99))

        in_transit_to = defaultdict(float)
        for ship in state.pipeline:
            if ship.sku == fg:
                in_transit_to[ship.destination_id] += ship.quantity

        for r in customer_routes:
            if not mods.warehouse_available.get(r.source_node_id, True):
                continue
            cid = r.destination_node_id
            need = max(0.0, state.backlog.get(cid, 0.0) - in_transit_to[cid] - state.inv(cid, fg))
            sent = self._ship_on_route(net, state, r, fg, need, day, mods, route_remaining)
            in_transit_to[cid] += sent

        for r in dc_routes:
            if not mods.warehouse_available.get(r.source_node_id, True):
                continue
            dest_wh = next((w for w in net.warehouses if w.warehouse_id == r.destination_node_id), None)
            if dest_wh is None:
                continue
            dest_on_hand = state.inv(r.destination_node_id, fg)
            target = max(dest_wh.safety_stock.get(fg, 0.0) * 2.0, 200.0)
            need = max(0.0, target - dest_on_hand - in_transit_to[r.destination_node_id])
            sent = self._ship_on_route(net, state, r, fg, need, day, mods, route_remaining)
            in_transit_to[r.destination_node_id] += sent

    def _ship_materials_to_factories(
        self,
        net: NetworkSnapshot,
        state: RunState,
        day: int,
        mods: DayModifiers,
        route_remaining: dict[str, float],
    ) -> None:
        for f in net.factories:
            routes = [
                r
                for r in net.incoming_routes(f.factory_id)
                if net.node_type_of(r.source_node_id) == NodeType.WAREHOUSE
            ]
            for r in routes:
                if not mods.warehouse_available.get(r.source_node_id, True):
                    continue
                for sku, qty_each in f.bom.items():
                    target = f.current_production_per_day * qty_each * self.COVER_DAYS
                    have = state.inv(f.factory_id, sku)
                    in_tr = sum(
                        s.quantity
                        for s in state.pipeline
                        if s.destination_id == f.factory_id and s.sku == sku
                    )
                    need = max(0.0, target - have - in_tr)
                    self._ship_on_route(net, state, r, sku, need, day, mods, route_remaining)

    def _eligible_suppliers(self, net: NetworkSnapshot, sku: str, mods: DayModifiers) -> list[Supplier]:
        preferred = [
            s
            for s in net.suppliers
            if s.sku == sku and s.preferred_for_sku and mods.supplier_available.get(s.supplier_id, True)
        ]
        alts = [
            s
            for s in net.suppliers
            if s.sku == sku
            and not s.preferred_for_sku
            and s.supplier_id in mods.alt_suppliers_enabled
            and mods.supplier_available.get(s.supplier_id, True)
        ]
        # If preferred is unavailable, do NOT auto-failover unless alt is enabled.
        return preferred + alts

    def _pull_from_suppliers(
        self,
        net: NetworkSnapshot,
        state: RunState,
        day: int,
        mods: DayModifiers,
        route_remaining: dict[str, float],
    ) -> None:
        remaining_cap = {
            s.supplier_id: s.capacity_per_day * mods.supplier_capacity_factor.get(s.supplier_id, 1.0)
            for s in net.suppliers
        }
        in_tr = defaultdict(float)
        for ship in state.pipeline:
            in_tr[(ship.destination_id, ship.sku)] += ship.quantity

        daily_factory_need: dict[str, float] = defaultdict(float)
        for f in net.factories:
            for sku, qty_each in f.bom.items():
                daily_factory_need[sku] += f.current_production_per_day * qty_each

        dest_warehouses: dict[str, Warehouse] = {}
        for supplier in net.suppliers:
            for r in net.outgoing_routes(supplier.supplier_id):
                wh = next((w for w in net.warehouses if w.warehouse_id == r.destination_node_id), None)
                if wh:
                    dest_warehouses[wh.warehouse_id] = wh

        for dest in dest_warehouses.values():
            skus = {s.sku for s in net.suppliers}
            for sku in skus:
                target = max(
                    dest.safety_stock.get(sku, 0.0) * 2.0,
                    daily_factory_need.get(sku, 0.0) * 5.0,
                )
                have = state.inv(dest.warehouse_id, sku)
                need = max(0.0, target - have - in_tr[(dest.warehouse_id, sku)])
                for supplier in self._eligible_suppliers(net, sku, mods):
                    if need <= 1e-9:
                        break
                    if remaining_cap[supplier.supplier_id] <= 1e-9:
                        continue
                    routes = [
                        r
                        for r in net.outgoing_routes(supplier.supplier_id)
                        if r.destination_node_id == dest.warehouse_id
                        and mods.route_available.get(r.route_id, True)
                    ]
                    if not routes:
                        continue
                    route = routes[0]
                    cap = min(remaining_cap[supplier.supplier_id], route_remaining.get(route.route_id, 0.0), need)
                    if cap <= 1e-9:
                        continue
                    extra = mods.route_extra_transit.get(route.route_id, 0)
                    transit = route.transit_time_days + supplier.lead_time_days
                    ship = self._create_shipment(
                        state,
                        route,
                        sku,
                        cap,
                        day,
                        extra,
                        unit_product_cost=supplier.unit_cost,
                        transit_override=transit,
                    )
                    remaining_cap[supplier.supplier_id] -= cap
                    route_remaining[route.route_id] = route_remaining.get(route.route_id, 0.0) - cap
                    premium = mods.route_expedite_premium.get(route.route_id, 0.0)
                    if premium:
                        mods.expedite_premium_accrued += cap * premium
                    state.procurement_cost += cap * supplier.unit_cost
                    state.procurement_units_by_supplier[supplier.supplier_id] += cap
                    need -= cap
                    in_tr[(dest.warehouse_id, sku)] += cap
                    if extra:
                        state.events.append(
                            SimulationEvent(
                                day=day,
                                node_id=route.route_id,
                                category="transport",
                                message=(
                                    f"Shipment {ship.shipment_id} delayed by extra transit; "
                                    f"arrival day {ship.arrival_day}"
                                ),
                            )
                        )

        for s in net.suppliers:
            factor = mods.supplier_capacity_factor.get(s.supplier_id, 1.0)
            if (factor < 1.0 or not mods.supplier_available.get(s.supplier_id, True)) and s.preferred_for_sku:
                downstream = net.outgoing_routes(s.supplier_id)
                node_id = downstream[0].destination_node_id if downstream else s.supplier_id
                state.events.append(
                    SimulationEvent(
                        day=day,
                        node_id=node_id,
                        category="supply_gap",
                        message=(
                            f"Downstream node cannot replenish {s.sku} from preferred {s.name} "
                            f"at full rate (capacity factor {factor})."
                        ),
                    )
                )

    def _status(
        self,
        node_type: NodeType,
        available: bool,
        stockout: bool,
        safety: bool,
        production_ratio: float | None,
        fill_ratio: float | None,
    ) -> NodeStatus:
        if not available:
            return NodeStatus.UNAVAILABLE
        if stockout or (production_ratio is not None and production_ratio < 0.5) or (
            fill_ratio is not None and fill_ratio < 0.8
        ):
            return NodeStatus.CRITICAL
        if safety or (production_ratio is not None and production_ratio < 0.85) or (
            fill_ratio is not None and fill_ratio < 0.95
        ):
            return NodeStatus.WARNING
        return NodeStatus.NORMAL

    def _snapshot_day(
        self,
        net: NetworkSnapshot,
        state: RunState,
        day: int,
        mods: DayModifiers,
        customer_stats: dict[str, dict[str, float]],
        factory_stats: dict[str, dict[str, float]],
    ) -> list[DailyNodeState]:
        rows: list[DailyNodeState] = []
        notes_by_node: dict[str, list[str]] = defaultdict(list)
        for ev in state.events:
            if ev.day == day:
                notes_by_node[ev.node_id].append(ev.message)

        for s in net.suppliers:
            avail = mods.supplier_available.get(s.supplier_id, True)
            factor = mods.supplier_capacity_factor.get(s.supplier_id, 1.0)
            status = NodeStatus.UNAVAILABLE if not avail or factor == 0 else (
                NodeStatus.WARNING if factor < 1 else NodeStatus.NORMAL
            )
            rows.append(
                DailyNodeState(
                    day=day,
                    node_id=s.supplier_id,
                    node_type=NodeType.SUPPLIER,
                    available=avail,
                    status=status,
                    shipped=state.procurement_units_by_supplier.get(s.supplier_id, 0.0),
                    notes=notes_by_node.get(s.supplier_id, []),
                )
            )
        for f in net.factories:
            st = factory_stats.get(f.factory_id, {"planned": 0, "actual": 0})
            planned, actual = st["planned"], st["actual"]
            ratio = (actual / planned) if planned else 1.0
            stockout = any(state.inv(f.factory_id, sku) <= 1e-9 for sku in f.bom)
            rows.append(
                DailyNodeState(
                    day=day,
                    node_id=f.factory_id,
                    node_type=NodeType.FACTORY,
                    inventory_by_sku=dict(state.inventories.get(f.factory_id, {})),
                    production=actual,
                    planned_production=planned,
                    available=mods.factory_available.get(f.factory_id, True),
                    stockout=stockout,
                    status=self._status(
                        NodeType.FACTORY,
                        mods.factory_available.get(f.factory_id, True),
                        stockout,
                        False,
                        ratio,
                        None,
                    ),
                    notes=notes_by_node.get(f.factory_id, []),
                )
            )
        for w in net.warehouses:
            inv = dict(state.inventories.get(w.warehouse_id, {}))
            stockout = any(inv.get(sku, 0) <= 1e-9 and ss > 0 for sku, ss in w.safety_stock.items())
            safety = any(inv.get(sku, 0) < ss for sku, ss in w.safety_stock.items())
            rows.append(
                DailyNodeState(
                    day=day,
                    node_id=w.warehouse_id,
                    node_type=NodeType.WAREHOUSE,
                    inventory_by_sku=inv,
                    available=mods.warehouse_available.get(w.warehouse_id, True),
                    stockout=stockout,
                    safety_stock_violation=safety,
                    status=self._status(
                        NodeType.WAREHOUSE,
                        mods.warehouse_available.get(w.warehouse_id, True),
                        stockout,
                        safety,
                        None,
                        None,
                    ),
                    notes=notes_by_node.get(w.warehouse_id, []),
                )
            )
        for c in net.customers:
            st = customer_stats.get(c.customer_id, {"demand": 0, "fulfilled": 0, "backlog": 0})
            fill = (st["fulfilled"] / st["demand"]) if st["demand"] else 1.0
            rows.append(
                DailyNodeState(
                    day=day,
                    node_id=c.customer_id,
                    node_type=NodeType.CUSTOMER,
                    demand=st["demand"],
                    fulfilled=st["fulfilled"],
                    unfulfilled_backlog=st["backlog"],
                    available=True,
                    status=self._status(NodeType.CUSTOMER, True, st["backlog"] > st["demand"] * 2, False, None, fill),
                    notes=notes_by_node.get(c.customer_id, []),
                )
            )
        return rows

    def _metrics(
        self, net: NetworkSnapshot, state: RunState, daily: list[DailyNodeState], horizon: int
    ) -> ImpactMetrics:
        total_demand = sum(state.demand_total.values())
        delivered = sum(state.fulfilled_total.values())
        unfulfilled = max(0.0, total_demand - delivered)
        # Backlog may include initial outstanding_orders which are not part of horizon demand.
        initial_backlog = sum(c.outstanding_orders for c in net.customers)
        unfulfilled_horizon = max(0.0, sum(state.backlog.values()) - 0.0)
        service = (delivered / total_demand * 100.0) if total_demand > 0 else None

        warehouse_days = [d for d in daily if d.node_type == NodeType.WAREHOUSE]
        stockout_days = len({(d.day, d.node_id) for d in warehouse_days if d.stockout})
        fg_levels = []
        for d in warehouse_days:
            if net.finished_good_sku in d.inventory_by_sku:
                fg_levels.append(d.inventory_by_sku[net.finished_good_sku])
        min_inv = min(fg_levels) if fg_levels else None

        production_shortfall = sum(state.production_planned.values()) - sum(state.production_actual.values())
        delay_num = sum(state.delay_days_weighted.values())
        delay_den = sum(state.delay_units.values())
        avg_delay = (delay_num / delay_den) if delay_den > 0 else None

        lost_revenue = unfulfilled * net.unit_revenue
        return ImpactMetrics(
            total_demand=round(total_demand, 2),
            total_units_delivered=round(delivered, 2),
            unfulfilled_demand=round(sum(state.backlog.values()), 2),
            service_level_pct=round(service, 2) if service is not None else None,
            stockout_days=stockout_days,
            minimum_inventory=round(min_inv, 2) if min_inv is not None else None,
            production_shortfall=round(max(0.0, production_shortfall), 2),
            total_transportation_cost=round(state.transport_cost, 2),
            estimated_disruption_cost=None,
            average_delivery_delay=round(avg_delay, 3) if avg_delay is not None else None,
            affected_customer_count=None,
            recovery_day=None,
            lost_revenue=round(lost_revenue, 2),
            expedite_and_reallocation_cost=round(state.extra_intervention_cost, 2),
            cost_notes=[
                "Unfulfilled demand is closing customer backlog (includes initial outstanding orders plus unmet horizon demand).",
                "Service level (%) = units delivered during the horizon / demand generated during the horizon × 100.",
                "Lost revenue = unfulfilled closing backlog × synthetic unit revenue. Initial outstanding orders can make this larger than horizon-only lost sales.",
                "Disruption cost is filled after baseline comparison so extra transport/procurement are incremental, not double-counted with totals.",
                f"Initial outstanding orders at t=0: {initial_backlog:.0f} units (not part of total_demand).",
                f"Horizon unfulfilled proxy (closing backlog): {unfulfilled_horizon:.2f}.",
            ],
        )

    def _relative_costs(
        self, net: NetworkSnapshot, baseline: dict[str, Any], scenario: dict[str, Any]
    ) -> ImpactMetrics:
        sm: ImpactMetrics = scenario["metrics"].model_copy(deep=True)
        bm: ImpactMetrics = baseline["metrics"]
        extra_transport = max(0.0, sm.total_transportation_cost - bm.total_transportation_cost)
        primary = next((s for s in net.suppliers if s.supplier_id == "SUP-001"), None)
        alt = next((s for s in net.suppliers if s.supplier_id == "SUP-002"), None)
        extra_proc = 0.0
        if primary and alt:
            base_units = baseline.get("procurement_units_by_supplier", {})
            scen_units = scenario.get("procurement_units_by_supplier", {})
            extra_alt = max(0.0, scen_units.get("SUP-002", 0) - base_units.get("SUP-002", 0))
            extra_proc = extra_alt * max(0.0, alt.unit_cost - primary.unit_cost)
        lost = max(0.0, (sm.unfulfilled_demand - bm.unfulfilled_demand) * net.unit_revenue)
        intervention = scenario.get("extra_intervention_cost", 0.0)
        sm.lost_revenue = round(lost, 2)
        sm.excess_transport_cost = round(extra_transport, 2)
        sm.excess_procurement_cost = round(extra_proc, 2)
        sm.expedite_and_reallocation_cost = round(intervention, 2)
        sm.estimated_disruption_cost = round(lost + extra_transport + extra_proc + intervention, 2)
        sm.cost_notes = [
            "estimated_disruption_cost = incremental lost revenue vs baseline + extra transport vs baseline + extra COMP-A procurement vs Alpha unit cost + explicit intervention premiums.",
            "total_transportation_cost is the scenario absolute freight spend and is not added again on top of extra transport.",
            "production_shortfall is a volume metric, not converted to currency (avoids double counting lost sales).",
        ]
        return sm

    def _affected(
        self,
        net: NetworkSnapshot,
        baseline_daily: list[DailyNodeState],
        scenario_daily: list[DailyNodeState],
        events: list[SimulationEvent],
    ) -> tuple[list[AffectedNode], list[str]]:
        bmap = {(d.day, d.node_id): d for d in baseline_daily}
        impacted: dict[str, AffectedNode] = {}
        for d in scenario_daily:
            b = bmap.get((d.day, d.node_id))
            if not b:
                continue
            reasons = []
            score = 0.0
            if d.production + 1e-6 < b.production:
                reasons.append(
                    f"Day {d.day}: production {d.production:.1f} vs baseline {b.production:.1f}"
                )
                score += b.production - d.production
            if d.fulfilled + 1e-6 < b.fulfilled:
                reasons.append(
                    f"Day {d.day}: fulfilled {d.fulfilled:.1f} vs baseline {b.fulfilled:.1f}"
                )
                score += b.fulfilled - d.fulfilled
            binv = sum(b.inventory_by_sku.values())
            sinv = sum(d.inventory_by_sku.values())
            if sinv + 1.0 < binv * 0.85 and binv > 10:
                reasons.append(f"Day {d.day}: on-hand inventory {sinv:.1f} vs baseline {binv:.1f}")
                score += (binv - sinv) * 0.05
            if d.status in {NodeStatus.CRITICAL, NodeStatus.UNAVAILABLE} and b.status == NodeStatus.NORMAL:
                reasons.append(f"Day {d.day}: status {d.status.value}")
                score += 10
            base_notes = set(b.notes or [])
            extra_notes = [n for n in (d.notes or []) if n not in base_notes]
            if extra_notes:
                reasons.extend(extra_notes[:2])
            if reasons:
                rec = impacted.get(d.node_id)
                if rec is None:
                    impacted[d.node_id] = AffectedNode(
                        node_id=d.node_id,
                        node_type=d.node_type.value,
                        impact_summary=reasons[0],
                        reasons=reasons[:8],
                        deviation_score=score,
                    )
                else:
                    rec.reasons.extend(reasons[:2])
                    rec.reasons = rec.reasons[:12]
                    rec.deviation_score += score
        for ev in events:
            if ev.category in {"production_constraint", "supply_gap", "disruption"} and ev.node_id in impacted:
                if ev.message not in impacted[ev.node_id].reasons:
                    impacted[ev.node_id].reasons.append(ev.message)
        nodes = sorted(impacted.values(), key=lambda n: -n.deviation_score)
        path = self._propagation_path(net, nodes)
        return nodes, path

    def _propagation_path(self, net: NetworkSnapshot, affected: list[AffectedNode]) -> list[str]:
        if not affected:
            return []
        origin = affected[0].node_id
        # Prefer a disrupted supplier if present.
        for n in affected:
            if n.node_type == NodeType.SUPPLIER.value:
                origin = n.node_id
                break
        affected_ids = {n.node_id for n in affected}
        ordered = []
        seen = set()
        queue = [origin]
        while queue:
            cur = queue.pop(0)
            if cur in seen:
                continue
            seen.add(cur)
            if cur in affected_ids:
                ordered.append(cur)
            for r in net.outgoing_routes(cur):
                if r.destination_node_id not in seen:
                    queue.append(r.destination_node_id)
        for n in affected:
            if n.node_id not in seen:
                ordered.append(n.node_id)
        return ordered

    def _recovery_day(
        self,
        baseline_daily: list[DailyNodeState],
        scenario_daily: list[DailyNodeState],
        disruptions: list[Disruption],
        horizon: int,
    ) -> int | None:
        if not disruptions:
            return None
        end = max(d.start_day + d.duration_days for d in disruptions)
        b_fill = defaultdict(float)
        s_fill = defaultdict(float)
        b_prod = defaultdict(float)
        s_prod = defaultdict(float)
        for d in baseline_daily:
            if d.node_type == NodeType.CUSTOMER:
                b_fill[d.day] += d.fulfilled
            if d.node_type == NodeType.FACTORY:
                b_prod[d.day] += d.production
        for d in scenario_daily:
            if d.node_type == NodeType.CUSTOMER:
                s_fill[d.day] += d.fulfilled
            if d.node_type == NodeType.FACTORY:
                s_prod[d.day] += d.production
        for day in range(end, horizon + 1):
            bf, sf = b_fill[day], s_fill[day]
            bp, sp = b_prod[day], s_prod[day]
            fill_ok = bf <= 1e-6 or sf >= 0.95 * bf
            prod_ok = bp <= 1e-6 or sp >= 0.95 * bp
            if fill_ok and prod_ok:
                return day
        return None
