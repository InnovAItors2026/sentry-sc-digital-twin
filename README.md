# SENTRY-SC — Digital Twin & Disruption Simulation

AI-powered Supply Chain Stress-Test Digital Twin module for SAP Hackfest 2026.

This repository implements the **digital twin, disruption configuration, discrete-time simulator, APIs, and demonstration UI**. It does **not** train an ML model and does **not** connect to live SAP.

## Architecture

```
frontend/                 React + Vite + Tailwind + React Flow + Recharts
backend/app/
  domain/models.py        Twin entities, disruptions, recoveries, metrics
  data/demo_network.py    Synthetic Northwind Precision Manufacturing network
  simulation/engine.py    Discrete-time (1 day) material-flow engine
  api/routes.py           FastAPI contracts
  adapters/
    risk.py               Ingest AI/ML disruption predictions
    recovery.py           Ingest optimizer candidate interventions
    sap.py                Stub — no live SAP connector
  store.py                In-memory scenarios (baseline twin is copied, never mutated)
backend/tests/             Pytest: flow, outages, cascade, metrics, API
docs/                     Assumptions and integration contracts
```

## Requirements

- Python 3.11+
- Node.js 20+

## Run the backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

OpenAPI: http://127.0.0.1:8000/api/docs

## Run the frontend

```bash
cd frontend
npm install
npm run dev
```

UI: http://127.0.0.1:5173  (Vite proxies `/api` to port 8000)

## Tests

```bash
cd backend
pytest -q

cd frontend
npm test
```

## Seeded demo (required walkthrough)

Network: four suppliers (Alpha critical COMP-A, Beta alternate COMP-A, Gamma COMP-B, Delta PACK), two factories, three warehouses, twelve routes, three customers.

1. Open **Overview** — inspect the twin. Baseline inventories are synthetic and labeled.
2. Open **Compare** and run:
   - `SCN-BASELINE` — 30 days, no injected disruption
   - `SCN-ALPHA-OUTAGE` — Alpha capacity 0 from day 3 for 10 days
   - `SCN-ALPHA-RECOVERY` — same outage, Beta activated on day 5
3. Or use **Stress test** → “Load demo (Alpha outage)” → run.

You should see COMP-A inventory fall, factory production drop when BOM inventory is insufficient, and customer fulfillment lag. Activating Beta does not teleport inventory: Beta’s 6-day lead time plus transit still applies.

KPIs are computed from the engine. They are not hardcoded.

## API (stable for other team members)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness |
| GET | `/api/network` | Full twin + React Flow graph payload |
| GET | `/api/network/{node_id}` | Node + incident edges |
| GET | `/api/scenarios` | Scenario list |
| POST | `/api/scenarios` | Create scenario (optional `ingested_predictions`) |
| POST | `/api/scenarios/{id}/simulate` | Run baseline + scenario |
| GET | `/api/scenarios/{id}/results` | Last results |
| GET | `/api/scenarios/{id}/timeline` | Daily series |
| GET | `/api/scenarios/{id}/affected-nodes` | Cascade set |
| POST | `/api/scenarios/compare` | Side-by-side KPIs |

See [docs/INTEGRATION.md](docs/INTEGRATION.md) and [docs/ASSUMPTIONS.md](docs/ASSUMPTIONS.md).
