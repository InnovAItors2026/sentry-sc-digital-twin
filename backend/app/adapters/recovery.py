"""Adapter: future Recovery/Optimization engine candidate interventions."""

from __future__ import annotations

from typing import Any

from app.domain.models import RecoveryIntervention, RecoveryType


class RecoveryOptimizationAdapter:
    """Accepts candidate interventions from an external optimizer.

    This module does not search or optimize. It validates and forwards.
    """

    def to_interventions(self, payload: dict[str, Any]) -> list[RecoveryIntervention]:
        items = payload.get("interventions") or payload.get("candidates") or []
        out: list[RecoveryIntervention] = []
        for raw in items:
            rec_type = raw.get("recovery_type") or raw.get("type")
            out.append(
                RecoveryIntervention(
                    recovery_type=RecoveryType(rec_type),
                    start_day=int(raw.get("start_day", 1)),
                    target_node_id=raw.get("target_node_id"),
                    alternative_supplier_id=raw.get("alternative_supplier_id"),
                    transit_days_saved=raw.get("transit_days_saved"),
                    capacity_multiplier=raw.get("capacity_multiplier"),
                    sku=raw.get("sku"),
                    quantity=raw.get("quantity"),
                    source_node_id=raw.get("source_node_id"),
                    destination_node_id=raw.get("destination_node_id"),
                    unit_premium=float(raw.get("unit_premium", 0)),
                    source=str(raw.get("source", "recovery_optimization_engine")),
                )
            )
        return out
