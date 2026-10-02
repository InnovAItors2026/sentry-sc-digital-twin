"""Adapter: consume AI/ML disruption predictions without training a model."""

from __future__ import annotations

from app.api.schemas import RiskPredictionIn
from app.domain.models import Disruption, DisruptionType, NodeType
from app.store import store

EVENT_MAP = {
    "supplier_outage": DisruptionType.SUPPLIER_OUTAGE,
    "factory_shutdown": DisruptionType.FACTORY_SHUTDOWN,
    "transportation_delay": DisruptionType.TRANSPORTATION_DELAY,
    "warehouse_disruption": DisruptionType.WAREHOUSE_DISRUPTION,
    "demand_spike": DisruptionType.DEMAND_SPIKE,
}


class RiskPredictionAdapter:
    """Maps an external prediction payload onto a validated Disruption.

    This module does not estimate risk. It only translates a contract.
    """

    def to_disruption(self, prediction: RiskPredictionIn) -> Disruption:
        event = EVENT_MAP.get(prediction.event_type)
        if event is None:
            raise ValueError(f"Unsupported event_type '{prediction.event_type}'")
        net = store.baseline_network
        delay = prediction.predicted_delay_days or 1
        kwargs: dict = {
            "event_type": event,
            "target_node_id": prediction.target_node_id,
            "start_day": 1,
            "duration_days": max(1, delay),
            "source": prediction.source,
        }
        ntype = net.node_type_of(prediction.target_node_id)
        route_ids = {r.route_id for r in net.routes}
        if event == DisruptionType.TRANSPORTATION_DELAY:
            if prediction.target_node_id not in route_ids:
                raise ValueError(f"Transportation delay target must be a route id, got {prediction.target_node_id}")
            kwargs["extra_transit_days"] = delay
            if prediction.capacity_factor is not None:
                kwargs["capacity_factor"] = prediction.capacity_factor
            return Disruption(**kwargs)
        if ntype is None:
            raise ValueError(f"Unknown target_node_id {prediction.target_node_id}")
        expected = {
            DisruptionType.SUPPLIER_OUTAGE: NodeType.SUPPLIER,
            DisruptionType.FACTORY_SHUTDOWN: NodeType.FACTORY,
            DisruptionType.WAREHOUSE_DISRUPTION: NodeType.WAREHOUSE,
            DisruptionType.DEMAND_SPIKE: NodeType.CUSTOMER,
        }
        if expected.get(event) not in (None, ntype):
            raise ValueError("Prediction target/type mismatch")
        if event == DisruptionType.SUPPLIER_OUTAGE:
            kwargs["capacity_factor"] = prediction.capacity_factor if prediction.capacity_factor is not None else 0.0
        elif event == DisruptionType.FACTORY_SHUTDOWN:
            kwargs["capacity_factor"] = prediction.capacity_factor if prediction.capacity_factor is not None else 0.0
        elif event == DisruptionType.DEMAND_SPIKE:
            kwargs["demand_increase_pct"] = 25.0
        elif event == DisruptionType.WAREHOUSE_DISRUPTION:
            kwargs["unavailable_inventory_pct"] = 40.0
            kwargs["capacity_factor"] = prediction.capacity_factor if prediction.capacity_factor is not None else 0.0
        return Disruption(**kwargs)
