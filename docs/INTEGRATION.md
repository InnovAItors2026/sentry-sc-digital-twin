# Integration contracts

Other Hackfest workstreams should treat these Pydantic models as the source of truth (`backend/app/domain/models.py`, `backend/app/api/schemas.py`).

## AI / ML — disruption prediction in

`POST /api/scenarios` accepts `ingested_predictions`:

```json
{
  "target_node_id": "SUP-001",
  "event_type": "supplier_outage",
  "predicted_delay_days": 8,
  "risk_probability": 0.82,
  "capacity_factor": 0.0,
  "source": "external_risk_engine"
}
```

`event_type` must be one of: `supplier_outage`, `factory_shutdown`, `transportation_delay`, `warehouse_disruption`, `demand_spike`.

The adapter (`app.adapters.risk.RiskPredictionAdapter`) maps delay days to disruption duration. It does **not** train or score a model. `risk_probability` is stored only as provenance on the source field today; it does not stochasticize the engine.

## Recovery / optimization — interventions in

```json
{
  "recovery_type": "activate_alternative_supplier",
  "start_day": 5,
  "target_node_id": "SUP-001",
  "alternative_supplier_id": "SUP-002",
  "source": "recovery_optimization_engine"
}
```

Supported `recovery_type` values: `restore_supplier`, `activate_alternative_supplier`, `expedite_route`, `increase_route_capacity`, `reallocate_inventory`, `restore_factory`.

Optional fields: `transit_days_saved`, `capacity_multiplier`, `sku`, `quantity`, `source_node_id`, `destination_node_id`, `unit_premium`.

`POST /api/scenarios` also accepts `ingested_recoveries` (list of the objects above). The adapter (`app.adapters.recovery.RecoveryOptimizationAdapter.to_interventions`) maps them onto `RecoveryIntervention` records. You may still send `recoveries` directly.

## Simulation result out

`POST /api/scenarios/{id}/simulate` returns:

```json
{
  "scenario_id": "SCN-001",
  "baseline_metrics": {},
  "scenario_metrics": {},
  "affected_nodes": [],
  "propagation_path": [],
  "daily_timeline": [],
  "baseline_daily_timeline": [],
  "events": [],
  "assumptions": [],
  "feasibility": [],
  "horizon_days": 30
}
```

Metric fields are defined on `ImpactMetrics`. Missing values are JSON `null`, never fabricated.

## SAP / enterprise

`app.adapters.sap.SapNetworkAdapter.available()` is `False`. Replace `load_network` when IDoc/OData mapping exists. Do not report a live SAP connection until that adapter returns real data.

## Frontend

The Vite app is a reference console. Another frontend can consume the same `/api/*` routes. Graph layout data is included on `GET /api/network` as `graph_nodes` / `graph_edges`.
