# Modeling assumptions and limitations

These rules are implemented in `backend/app/simulation/engine.py`. They are not forecasts from an ML model.

## Time and causality

- One simulated day per tick.
- Arrivals are processed before production and new shipments.
- New shipments never arrive on the same day they are created (`arrival_day = depart_day + max(1, transit)`).
- Supplier `lead_time_days` is added to route `transit_time_days` for supplier-origin shipments.

## Inventory and production

- Inventory is never negative. Unmet customer demand is backlog.
- Factories consume only on-hand BOM inventory. Same-day replenishment cannot feed the same day's production.
- Each factory is seeded with `COVER_DAYS` (3) of on-hand BOM so plants can produce while inbound materials are in transit. Warehouse opening stock comes from the twin.
- Warehouse capacity is the sum of units across SKUs. Over-capacity receipts are deferred one day.
- Frozen warehouse inventory (unavailable %) cannot be shipped until the disruption window ends.

## Sourcing

- Preferred suppliers (`preferred_for_sku=true`) are used first.
- Supplier Beta is **not** an automatic failover for COMP-A. It is used only when an `activate_alternative_supplier` recovery is in force (and SKU matches).
- If a preferred supplier is down and no alternative is activated, replenishment of that SKU stops.

## Demand and service

- `total_demand` is demand generated during the horizon (daily demand × spike multipliers). It excludes opening outstanding orders.
- `total_units_delivered` is quantity consumed from customer on-hand to reduce backlog.
- `unfulfilled_demand` is **closing backlog**, which includes opening outstanding orders plus unmet horizon demand.
- Service level (%) = delivered / horizon demand × 100.

## Costing (no double counting)

`estimated_disruption_cost` after a paired baseline run is:

1. Incremental lost revenue vs baseline closing backlog × unit revenue ($75 synthetic list price)
2. Extra transportation spend vs baseline (only the positive difference)
3. Extra COMP-A units bought from Beta vs baseline × (Beta unit cost − Alpha unit cost)
4. Explicit reallocation / expedite premiums

Absolute `total_transportation_cost` is reported separately and is not added on top of (2). Production shortfall is a volume KPI, not converted to money (that would double-count lost sales).

## Recovery day

First day **on or after** the last disruption window where both network production and customer fulfillments are at least 95% of that day's baseline. If that never happens inside the horizon, the metric is `null` (unavailable), not invented.

## What this module does not do

- No stochastic reliability sampling (`reliability_score` is descriptive).
- No live SAP master data, ATP, or IDoc exchange (`adapters/sap.py` is a stub).
- No trained delay/risk model (`adapters/risk.py` only maps inbound JSON to a `Disruption`).
- Recovery “feasibility” is limited to SKU match, node/route existence, and available unfrozen inventory at reallocation time. It is **not** a real-world operations certificate.
