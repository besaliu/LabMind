"""
Integration tests for the LabMind FastAPI backend.
Tests verify external behavior through the HTTP interface — no internal mocks.
All filesystem I/O uses a real temporary directory.
"""
import csv
import json
import os
import pytest
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_data_dir(monkeypatch, tmp_path):
    """Point all storage paths at a fresh temp directory for each test.
    Storage uses lazy path functions, so setting the env var is sufficient."""
    data = tmp_path / "labmind-data"
    (data / "experiments").mkdir(parents=True)
    (data / "instruments").mkdir(parents=True)

    monkeypatch.setenv("LABMIND_DATA", str(data))
    return data


@pytest.fixture
def client():
    import main
    return TestClient(main.app, raise_server_exceptions=True)


@pytest.fixture
def active_experiment(client):
    """Upload + confirm an experiment, returning the run_id."""
    doc = b"hypothesis: Test crystal growth\ninstruments:\n  - temp_controller\n  - ph_probe\nparameters:\n  target_temp_c: 35.0\nthresholds:\n  temp_max_c: 38.0\n  impurity_max_ppm: 50.0\nsuccess_criteria: Crystal clarity > 90%\n"
    resp = client.post("/api/experiments/upload", files={"doc": ("experiment.yaml", doc, "text/yaml")})
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    resp = client.post(f"/api/experiments/{run_id}/confirm")
    assert resp.status_code == 200
    return run_id


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health(client):
    assert client.get("/health").status_code == 200


# ---------------------------------------------------------------------------
# Instrument registration
# ---------------------------------------------------------------------------

def test_register_instrument_writes_registry(client, isolated_data_dir):
    payload = {
        "instrument_id": "temp_controller_01",
        "type": "temp_controller",
        "name": "Crystal Growth Temp Controller",
        "port": 8101,
        "capabilities": ["read_temperature", "set_temperature"],
    }
    resp = client.post("/api/instruments/register", json=payload)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    registry = json.loads((isolated_data_dir / "instruments" / "registry.json").read_text())
    assert "temp_controller_01" in registry
    assert registry["temp_controller_01"]["type"] == "temp_controller"
    assert registry["temp_controller_01"]["status"] == "online"


def test_register_instrument_upserts_on_repeat(client):
    payload = {"instrument_id": "ph_probe_01", "type": "ph_probe", "name": "pH Probe", "port": 8102, "capabilities": []}
    client.post("/api/instruments/register", json=payload)
    client.post("/api/instruments/register", json=payload)

    resp = client.get("/api/instruments")
    assert resp.status_code == 200
    instruments = resp.json()
    assert len([k for k in instruments if k == "ph_probe_01"]) == 1


def test_list_instruments_returns_registry(client):
    client.post("/api/instruments/register", json={"instrument_id": "a_01", "type": "a", "name": "A", "port": 8101, "capabilities": []})
    client.post("/api/instruments/register", json={"instrument_id": "b_01", "type": "b", "name": "B", "port": 8102, "capabilities": []})
    resp = client.get("/api/instruments")
    assert resp.status_code == 200
    data = resp.json()
    assert "a_01" in data
    assert "b_01" in data


# ---------------------------------------------------------------------------
# Analytics ingestion
# ---------------------------------------------------------------------------

def test_analytics_rejected_with_no_active_experiment(client):
    resp = client.post("/api/analytics", json={
        "instrument_id": "temp_controller_01",
        "timestamp": "2026-05-15T22:00:00Z",
        "readings": {"temperature_c": 35.0, "setpoint_c": 35.0},
        "status": "nominal",
    })
    assert resp.status_code == 409


def test_analytics_appends_temp_row(client, active_experiment, isolated_data_dir):
    client.post("/api/instruments/register", json={
        "instrument_id": "temp_controller_01", "type": "temp_controller",
        "name": "TC", "port": 8101, "capabilities": [],
    })
    resp = client.post("/api/analytics", json={
        "instrument_id": "temp_controller_01",
        "timestamp": "2026-05-15T22:00:00Z",
        "readings": {"temperature_c": 35.2, "setpoint_c": 35.0},
        "status": "nominal",
    })
    assert resp.status_code == 200

    csv_path = isolated_data_dir / "experiments" / active_experiment / "temp.csv"
    assert csv_path.exists()
    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == 1
    assert float(rows[0]["temperature_c"]) == pytest.approx(35.2)
    assert rows[0]["status"] == "nominal"


def test_analytics_appends_impurity_row_for_ph_probe(client, active_experiment, isolated_data_dir):
    client.post("/api/instruments/register", json={
        "instrument_id": "ph_probe_01", "type": "ph_probe",
        "name": "pH", "port": 8102, "capabilities": [],
    })
    client.post("/api/analytics", json={
        "instrument_id": "ph_probe_01",
        "timestamp": "2026-05-15T22:00:00Z",
        "readings": {"ph": 7.1},
        "status": "nominal",
    })

    csv_path = isolated_data_dir / "experiments" / active_experiment / "impurity.csv"
    assert csv_path.exists()
    rows = list(csv.DictReader(csv_path.open()))
    assert float(rows[0]["ph"]) == pytest.approx(7.1)


def test_multiple_analytics_rows_accumulate(client, active_experiment, isolated_data_dir):
    client.post("/api/instruments/register", json={
        "instrument_id": "temp_controller_01", "type": "temp_controller",
        "name": "TC", "port": 8101, "capabilities": [],
    })
    for temp in [35.0, 35.5, 36.0]:
        client.post("/api/analytics", json={
            "instrument_id": "temp_controller_01",
            "timestamp": "2026-05-15T22:00:00Z",
            "readings": {"temperature_c": temp, "setpoint_c": 35.0},
            "status": "nominal",
        })

    csv_path = isolated_data_dir / "experiments" / active_experiment / "temp.csv"
    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == 3


# ---------------------------------------------------------------------------
# Experiment lifecycle
# ---------------------------------------------------------------------------

def test_upload_creates_run_directory(client, isolated_data_dir):
    doc = b"hypothesis: Grow KDP crystals\ninstruments:\n  - temp_controller\n"
    resp = client.post("/api/experiments/upload", files={"doc": ("e.yaml", doc, "text/yaml")})
    assert resp.status_code == 200
    body = resp.json()
    assert "run_id" in body
    assert body["status"] == "pending"  # RAG check is agent's job via MCP tool

    meta_path = isolated_data_dir / "experiments" / body["run_id"] / "metadata.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["status"] == "pending"
    assert meta["hypothesis"] == "Grow KDP crystals"


def test_upload_blocked_when_experiment_already_active(client, active_experiment):
    doc = b"hypothesis: Another experiment\ninstruments:\n  - temp_controller\n"
    resp = client.post("/api/experiments/upload", files={"doc": ("e.yaml", doc, "text/yaml")})
    assert resp.status_code == 409


def test_confirm_transitions_to_active(client, isolated_data_dir):
    doc = b"hypothesis: Test\ninstruments:\n  - temp_controller\n"
    run_id = client.post("/api/experiments/upload", files={"doc": ("e.yaml", doc, "text/yaml")}).json()["run_id"]

    resp = client.post(f"/api/experiments/{run_id}/confirm")
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    meta = json.loads((isolated_data_dir / "experiments" / run_id / "metadata.json").read_text())
    assert meta["status"] == "active"
    assert meta["start_time"] is not None


def test_confirm_sets_active_run(client, isolated_data_dir):
    doc = b"hypothesis: Test\ninstruments:\n  - temp_controller\n"
    run_id = client.post("/api/experiments/upload", files={"doc": ("e.yaml", doc, "text/yaml")}).json()["run_id"]
    client.post(f"/api/experiments/{run_id}/confirm")

    resp = client.get("/api/experiments/current")
    assert resp.json()["active"] is True
    assert resp.json()["run_id"] == run_id


def test_current_returns_inactive_when_no_experiment(client):
    resp = client.get("/api/experiments/current")
    assert resp.status_code == 200
    assert resp.json()["active"] is False


def test_current_returns_pending_after_upload(client):
    doc = b"hypothesis: Grow KDP crystals\ninstruments:\n  - temp_controller\n"
    run_id = client.post("/api/experiments/upload", files={"doc": ("e.yaml", doc, "text/yaml")}).json()["run_id"]

    resp = client.get("/api/experiments/current")
    assert resp.status_code == 200
    assert resp.json()["active"] is False
    assert resp.json()["status"] == "pending"
    assert resp.json()["run_id"] == run_id


def test_current_clears_pending_after_confirm(client):
    doc = b"hypothesis: Test\ninstruments:\n  - temp_controller\n"
    run_id = client.post("/api/experiments/upload", files={"doc": ("e.yaml", doc, "text/yaml")}).json()["run_id"]
    client.post(f"/api/experiments/{run_id}/confirm")

    resp = client.get("/api/experiments/current")
    assert resp.json()["status"] == "active"
    assert resp.json()["active"] is True


def test_finalize_rejects_missing_report(client, active_experiment):
    resp = client.post(f"/api/experiments/{active_experiment}/finalize", json={
        "report": "# Report\nSome findings.",
        "outcome": "success",
        "key_findings": ["Crystal clarity 94%"],
    })
    # report.md not written yet — MCP tool owns this step
    assert resp.status_code == 422


def test_finalize_succeeds_when_report_exists(client, active_experiment, isolated_data_dir):
    # Simulate the MCP tool having written the report
    report_path = isolated_data_dir / "experiments" / active_experiment / "report.md"
    report_path.write_text("# Report\nExperiment concluded successfully.")

    resp = client.post(f"/api/experiments/{active_experiment}/finalize", json={
        "report": "# Report\nExperiment concluded successfully.",
        "outcome": "success",
        "key_findings": ["Crystal clarity 94%", "No interventions needed"],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "run_id" in body

    meta = json.loads((isolated_data_dir / "experiments" / active_experiment / "metadata.json").read_text())
    assert meta["status"] == "completed"
    assert meta["outcome"] == "success"
    assert meta["end_time"] is not None


def test_finalize_clears_active_run(client, active_experiment, isolated_data_dir):
    report_path = isolated_data_dir / "experiments" / active_experiment / "report.md"
    report_path.write_text("# Done")

    client.post(f"/api/experiments/{active_experiment}/finalize", json={
        "report": "# Done", "outcome": "success", "key_findings": [],
    })

    assert client.get("/api/experiments/current").json()["active"] is False


def test_finalize_prevents_double_finalization(client, active_experiment, isolated_data_dir):
    report_path = isolated_data_dir / "experiments" / active_experiment / "report.md"
    report_path.write_text("# Done")
    payload = {"report": "# Done", "outcome": "success", "key_findings": []}

    client.post(f"/api/experiments/{active_experiment}/finalize", json=payload)
    resp = client.post(f"/api/experiments/{active_experiment}/finalize", json=payload)
    assert resp.status_code == 409


def test_get_report_returns_markdown(client, active_experiment, isolated_data_dir):
    report_path = isolated_data_dir / "experiments" / active_experiment / "report.md"
    report_path.write_text("# Morning Report\nAll good.")

    resp = client.get(f"/api/experiments/{active_experiment}/report")
    assert resp.status_code == 200
    assert "Morning Report" in resp.text


def test_get_report_404_before_finalization(client, active_experiment):
    resp = client.get(f"/api/experiments/{active_experiment}/report")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Dashboard bundle
# ---------------------------------------------------------------------------

def _seed_dashboard_run(data_dir: Path, run_id: str = "run_005") -> Path:
    """Seed a complete run with event-tagged CSVs for dashboard tests."""
    run = data_dir / "experiments" / run_id
    run.mkdir(parents=True)

    meta = {
        "run_id": run_id,
        "hypothesis": "Test hypothesis",
        "experiment_type": "crystallization",
        "instruments": ["temp_controller", "ph_probe"],
        "parameters": {"target_temp_c": 36.0, "cooling_rate_c_per_hour": 2.0, "substrate": "KDP"},
        "monitoring": {
            "temperature_c": {"target": 36.0, "warning_above": 38.0, "critical_above": 39.0,
                              "warning_below": 34.0, "critical_below": 32.0},
            "impurity_ppm":  {"target": 15.0, "warning_above": 35.0, "critical_above": 50.0},
            "ph":            {"target": 7.1,  "warning_above": 7.4,  "critical_above": 7.6,
                              "warning_below": 6.8, "critical_below": 6.5},
        },
        "status": "completed",
        "outcome": "success",
        "key_findings": ["finding A"],
    }
    (run / "metadata.json").write_text(json.dumps(meta))

    (run / "temp.csv").write_text(
        "timestamp,temperature_c,setpoint_c,status,event\n"
        "2026-05-17T01:00:00Z,33.0,33.0,nominal,\n"
        "2026-05-17T01:05:00Z,33.0,33.0,nominal,temp_probe_lag_suspected\n"
        "2026-05-17T01:10:00Z,33.1,33.0,nominal,temp_probe_lag_suspected\n"
        "2026-05-17T01:15:00Z,33.0,33.5,nominal,agent_intervention:set_temperature\n"
        "2026-05-17T01:20:00Z,32.4,33.5,warning,temp_dip_confirmed_post_intervention\n"
    )
    (run / "impurity.csv").write_text(
        "timestamp,impurity_ppm,saturation_pct,ph,status,event\n"
        "2026-05-17T01:00:00Z,24.0,77.8,7.14,nominal,impurity_rising_nominal_range\n"
        "2026-05-17T01:05:00Z,28.0,77.7,7.14,nominal,impurity_spike_rate_5ppm_per_min\n"
        "2026-05-17T01:10:00Z,38.0,77.6,7.14,warning,impurity_above_warning_threshold\n"
        "2026-05-17T01:15:00Z,42.0,77.4,7.14,warning,impurity_above_warning_threshold\n"
        "2026-05-17T01:20:00Z,39.0,77.3,7.14,warning,impurity_recovering\n"
    )
    (run / "microscopy.csv").write_text(
        "timestamp,clarity_pct,defect_count,status,event\n"
        "2026-05-17T01:30:00Z,92.8,2,nominal,minor_surface_stress_observed\n"
        "2026-05-17T02:00:00Z,92.4,2,nominal,\n"
    )
    (run / "interventions.json").write_text(json.dumps([
        {"timestamp": "2026-05-17T01:15:00Z",
         "action": "set_temperature(target_temp_c=33.5)",
         "reasoning": "sensor lag suspected",
         "outcome": "temperature dipped to 32.4°C as predicted"}
    ]))
    (run / "microscopy.json").write_text(json.dumps({
        "clarity": 0.91, "morphology": "single_crystal", "captured_at": "2026-05-17T06:00:00Z"
    }))
    return run


def test_dashboard_bundle_returns_full_shape(client, isolated_data_dir):
    _seed_dashboard_run(isolated_data_dir)
    resp = client.get("/api/experiments/run_005/dashboard_bundle")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "run_005"
    assert {"metadata", "interventions", "microscopy_snapshot",
            "series", "event_ranges", "thresholds"} <= body.keys()
    assert {"temp", "impurity", "microscopy"} == set(body["series"].keys())


def test_dashboard_bundle_coerces_numeric_fields(client, isolated_data_dir):
    _seed_dashboard_run(isolated_data_dir)
    body = client.get("/api/experiments/run_005/dashboard_bundle").json()
    first_temp = body["series"]["temp"][0]
    assert first_temp["temperature_c"] == 33.0
    assert isinstance(first_temp["temperature_c"], float)
    assert first_temp["t"] == "2026-05-17T01:00:00Z"


def test_dashboard_bundle_collapses_same_tag_runs_into_one_range(client, isolated_data_dir):
    _seed_dashboard_run(isolated_data_dir)
    body = client.get("/api/experiments/run_005/dashboard_bundle").json()
    warning_ranges = [r for r in body["event_ranges"]
                      if r["tag"] == "impurity_above_warning_threshold"]
    assert len(warning_ranges) == 1
    assert warning_ranges[0]["start"] == "2026-05-17T01:10:00Z"
    # end = next-row timestamp (the row where the tag changes)
    assert warning_ranges[0]["end"] == "2026-05-17T01:20:00Z"
    assert warning_ranges[0]["category"] == "threshold"
    assert warning_ranges[0]["panel"] == "impurity"


def test_dashboard_bundle_excludes_agent_intervention_tags_from_event_ranges(client, isolated_data_dir):
    _seed_dashboard_run(isolated_data_dir)
    body = client.get("/api/experiments/run_005/dashboard_bundle").json()
    tags = [r["tag"] for r in body["event_ranges"]]
    assert not any(t.startswith("agent_intervention") for t in tags)
    # but the interventions array still carries the full record
    assert len(body["interventions"]) == 1
    assert "reasoning" in body["interventions"][0]


def test_dashboard_bundle_extracts_thresholds_from_metadata(client, isolated_data_dir):
    _seed_dashboard_run(isolated_data_dir)
    body = client.get("/api/experiments/run_005/dashboard_bundle").json()
    assert body["thresholds"]["temp"]["warning_above"] == 38.0
    assert body["thresholds"]["impurity"]["warning_above"] == 35.0
    assert body["thresholds"]["ph"]["critical_above"] == 7.6


def test_dashboard_bundle_404_for_unknown_run(client):
    resp = client.get("/api/experiments/run_999/dashboard_bundle")
    assert resp.status_code == 404


def test_dashboard_bundle_handles_missing_microscopy_csv(client, isolated_data_dir):
    run = _seed_dashboard_run(isolated_data_dir, "run_min")
    (run / "microscopy.csv").unlink()
    body = client.get("/api/experiments/run_min/dashboard_bundle").json()
    assert body["series"]["microscopy"] == []


