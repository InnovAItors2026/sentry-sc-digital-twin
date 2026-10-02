from fastapi.testclient import TestClient

from app.main import app
from app.store import store

client = TestClient(app)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_network_shape():
    res = client.get("/api/network")
    assert res.status_code == 200
    body = res.json()
    assert body["counts"]["suppliers"] >= 4
    assert body["counts"]["factories"] >= 2
    assert body["counts"]["warehouses"] >= 3
    assert body["counts"]["routes"] >= 4
    assert body["counts"]["customers"] >= 3
    assert body["graph_nodes"]
    assert body["graph_edges"]


def test_node_lookup():
    res = client.get("/api/network/SUP-001")
    assert res.status_code == 200
    assert res.json()["node_type"] == "supplier"


def test_demo_outage_simulation_cascades():
    res = client.post("/api/scenarios/SCN-ALPHA-OUTAGE/simulate")
    assert res.status_code == 200
    body = res.json()
    assert body["scenario_metrics"]["service_level_pct"] is not None
    assert body["scenario_metrics"]["service_level_pct"] <= body["baseline_metrics"]["service_level_pct"] + 1e-6
    assert body["affected_nodes"]
    ids = {n["node_id"] for n in body["affected_nodes"]}
    assert "SUP-001" in ids or any("FAC" in i for i in ids)


def test_create_and_compare():
    created = client.post(
        "/api/scenarios",
        json={
            "name": "Spike Apex",
            "horizon_days": 14,
            "disruptions": [
                {
                    "event_type": "demand_spike",
                    "target_node_id": "CUS-001",
                    "start_day": 2,
                    "duration_days": 5,
                    "demand_increase_pct": 40,
                }
            ],
        },
    )
    assert created.status_code == 201
    sid = created.json()["scenario_id"]
    cmp = client.post("/api/scenarios/compare", json={"scenario_ids": ["SCN-BASELINE", sid]})
    assert cmp.status_code == 200
    assert len(cmp.json()["scenarios"]) == 2


def test_invalid_disruption_target():
    created = client.post(
        "/api/scenarios",
        json={
            "name": "bad",
            "horizon_days": 7,
            "disruptions": [
                {
                    "event_type": "supplier_outage",
                    "target_node_id": "NOPE",
                    "start_day": 1,
                    "duration_days": 2,
                }
            ],
        },
    )
    sid = created.json()["scenario_id"]
    res = client.post(f"/api/scenarios/{sid}/simulate")
    assert res.status_code == 422


def test_baseline_network_not_mutated_by_api_simulate():
    before = store.baseline_network.model_dump()
    client.post("/api/scenarios/SCN-ALPHA-OUTAGE/simulate")
    after = store.baseline_network.model_dump()
    assert before == after


def test_baseline_demo_has_no_false_affected_nodes():
    res = client.post("/api/scenarios/SCN-BASELINE/simulate")
    assert res.status_code == 200
    body = res.json()
    assert body["affected_nodes"] == []
    assert body["scenario_metrics"]["service_level_pct"] is not None
    assert body["scenario_metrics"]["service_level_pct"] >= body["baseline_metrics"]["service_level_pct"] - 1e-6


def test_ingested_prediction_and_recovery():
    created = client.post(
        "/api/scenarios",
        json={
            "name": "Adapter ingest",
            "horizon_days": 14,
            "ingested_predictions": [
                {
                    "target_node_id": "SUP-001",
                    "event_type": "supplier_outage",
                    "predicted_delay_days": 6,
                    "capacity_factor": 0.0,
                    "source": "external_risk_engine",
                }
            ],
            "ingested_recoveries": [
                {
                    "recovery_type": "activate_alternative_supplier",
                    "start_day": 3,
                    "target_node_id": "SUP-001",
                    "alternative_supplier_id": "SUP-002",
                    "source": "recovery_optimization_engine",
                }
            ],
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["disruption_count"] == 1
    assert body["recovery_count"] == 1
    sim = client.post(f"/api/scenarios/{body['scenario_id']}/simulate")
    assert sim.status_code == 200
    assert sim.json()["scenario_metrics"]["service_level_pct"] is not None


def test_ingested_transport_delay_targets_route():
    created = client.post(
        "/api/scenarios",
        json={
            "name": "Route delay ingest",
            "horizon_days": 10,
            "ingested_predictions": [
                {
                    "target_node_id": "RTE-001",
                    "event_type": "transportation_delay",
                    "predicted_delay_days": 3,
                    "source": "external_risk_engine",
                }
            ],
        },
    )
    assert created.status_code == 201
    sid = created.json()["scenario_id"]
    sim = client.post(f"/api/scenarios/{sid}/simulate")
    assert sim.status_code == 200
    assert sim.json()["events"]
