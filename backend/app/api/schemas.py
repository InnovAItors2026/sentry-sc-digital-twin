"""HTTP request/response contracts. Keep stable for other team modules."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.domain.models import (
    Customer,
    Disruption,
    Factory,
    RecoveryIntervention,
    Supplier,
    TransportationRoute,
    Warehouse,
)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class NetworkGraphNode(BaseModel):
    id: str
    type: str
    label: str
    data: dict[str, Any]


class NetworkGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    label: str
    data: dict[str, Any]


class NetworkResponse(BaseModel):
    network_id: str
    name: str
    finished_good_sku: str
    unit_revenue: float
    counts: dict[str, int]
    suppliers: list[Supplier]
    factories: list[Factory]
    warehouses: list[Warehouse]
    routes: list[TransportationRoute]
    customers: list[Customer]
    graph_nodes: list[NetworkGraphNode]
    graph_edges: list[NetworkGraphEdge]
    assumptions: list[str]
    inventory_overview: list[dict[str, Any]]
    overall_status: str


class RiskPredictionIn(BaseModel):
    """Inbound contract for the AI/ML risk engine (adapter only, not used to train models)."""

    target_node_id: str
    event_type: str
    predicted_delay_days: int | None = None
    risk_probability: float | None = Field(default=None, ge=0, le=1)
    capacity_factor: float | None = Field(default=None, ge=0, le=1)
    source: str = "external_risk_engine"


class ScenarioCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    horizon_days: int = Field(default=30, ge=1, le=365)
    disruptions: list[Disruption] = Field(default_factory=list)
    recoveries: list[RecoveryIntervention] = Field(default_factory=list)
    notes: str | None = None
    ingested_predictions: list[RiskPredictionIn] = Field(default_factory=list)
    ingested_recoveries: list[dict[str, Any]] = Field(default_factory=list)


class ScenarioSummary(BaseModel):
    scenario_id: str
    name: str
    horizon_days: int
    disruption_count: int
    recovery_count: int
    simulated: bool
    notes: str | None = None


class SimulateResponse(BaseModel):
    scenario_id: str
    baseline_metrics: dict[str, Any]
    scenario_metrics: dict[str, Any]
    affected_nodes: list[dict[str, Any]]
    daily_timeline: list[dict[str, Any]]
    baseline_daily_timeline: list[dict[str, Any]]
    events: list[dict[str, Any]]
    assumptions: list[str]
    feasibility: list[dict[str, Any]]
    horizon_days: int
    propagation_path: list[str] = Field(default_factory=list)


class CompareRequest(BaseModel):
    scenario_ids: list[str] = Field(min_length=1, max_length=6)


class CompareResponse(BaseModel):
    scenarios: list[dict[str, Any]]
    trade_offs: list[str]
