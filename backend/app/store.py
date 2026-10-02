"""In-memory scenario store. Baseline network is never mutated by simulation."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.data.demo_network import build_demo_network
from app.domain.models import Disruption, NetworkSnapshot, RecoveryIntervention


@dataclass
class ScenarioRecord:
    scenario_id: str
    name: str
    horizon_days: int
    disruptions: list[Disruption]
    recoveries: list[RecoveryIntervention]
    notes: str | None
    network: NetworkSnapshot
    results: dict[str, Any] | None = None


class ScenarioStore:
    def __init__(self) -> None:
        self._baseline_network = build_demo_network()
        self._scenarios: dict[str, ScenarioRecord] = {}
        self.seed_demo_scenarios()

    @property
    def baseline_network(self) -> NetworkSnapshot:
        return NetworkSnapshot.model_validate(copy.deepcopy(self._baseline_network.model_dump()))

    def seed_demo_scenarios(self) -> None:
        if self._scenarios:
            return
        self._scenarios["SCN-BASELINE"] = ScenarioRecord(
            scenario_id="SCN-BASELINE",
            name="30-day baseline (no disruption)",
            horizon_days=30,
            disruptions=[],
            recoveries=[],
            notes="Fair comparison control. Same initial inventories, demand, and routing rules.",
            network=self.baseline_network,
        )
        self._scenarios["SCN-ALPHA-OUTAGE"] = ScenarioRecord(
            scenario_id="SCN-ALPHA-OUTAGE",
            name="Supplier Alpha 10-day outage from day 3",
            horizon_days=30,
            disruptions=[
                Disruption(
                    disruption_id="D-ALPHA",
                    event_type="supplier_outage",
                    target_node_id="SUP-001",
                    start_day=3,
                    duration_days=10,
                    capacity_factor=0.0,
                    source="demo",
                )
            ],
            recoveries=[],
            notes="Critical COMP-A source is unavailable. Beta is present but not activated.",
            network=self.baseline_network,
        )
        self._scenarios["SCN-ALPHA-RECOVERY"] = ScenarioRecord(
            scenario_id="SCN-ALPHA-RECOVERY",
            name="Alpha outage + activate Supplier Beta on day 5",
            horizon_days=30,
            disruptions=[
                Disruption(
                    disruption_id="D-ALPHA",
                    event_type="supplier_outage",
                    target_node_id="SUP-001",
                    start_day=3,
                    duration_days=10,
                    capacity_factor=0.0,
                    source="demo",
                )
            ],
            recoveries=[
                RecoveryIntervention(
                    intervention_id="R-BETA",
                    recovery_type="activate_alternative_supplier",
                    start_day=5,
                    target_node_id="SUP-001",
                    alternative_supplier_id="SUP-002",
                    source="demo",
                )
            ],
            notes="Recovery uses Beta's longer lead time and higher unit cost. Not claimed operationally feasible beyond model checks.",
            network=self.baseline_network,
        )

    def list_scenarios(self) -> list[ScenarioRecord]:
        return list(self._scenarios.values())

    def get(self, scenario_id: str) -> ScenarioRecord | None:
        return self._scenarios.get(scenario_id)

    def create(
        self,
        name: str,
        horizon_days: int,
        disruptions: list[Disruption],
        recoveries: list[RecoveryIntervention],
        notes: str | None,
    ) -> ScenarioRecord:
        sid = f"SCN-{uuid.uuid4().hex[:8].upper()}"
        rec = ScenarioRecord(
            scenario_id=sid,
            name=name,
            horizon_days=horizon_days,
            disruptions=disruptions,
            recoveries=recoveries,
            notes=notes,
            network=self.baseline_network,
        )
        self._scenarios[sid] = rec
        return rec

    def save_results(self, scenario_id: str, results: dict[str, Any]) -> None:
        rec = self._scenarios[scenario_id]
        rec.results = results


store = ScenarioStore()
