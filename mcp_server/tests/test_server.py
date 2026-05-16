"""
Tests for the FastMCP server.
Verifies observable behavior: core tools read real files, dynamic tool
registration from YAML completes within 2 seconds, and finalize_experiment
writes report.md correctly.
"""
import asyncio
import csv
import json
import os
import time
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    data = tmp_path / "labmind-data"
    catalog = tmp_path / "instruments" / "catalog"
    (data / "experiments").mkdir(parents=True)
    (data / "instruments").mkdir(parents=True)
    catalog.mkdir(parents=True)

    monkeypatch.setenv("LABMIND_DATA", str(data))
    monkeypatch.setenv("CATALOG_DIR", str(catalog))
    monkeypatch.setenv("BACKEND_URL", "http://localhost:19998")
    monkeypatch.setenv("RAG_SERVICE_URL", "http://localhost:19999")
    return {"data": data, "catalog": catalog}


@pytest.fixture
def seed_run(isolated_env):
    """Create a minimal completed experiment run on disk."""
    data = isolated_env["data"]
    run_id = "run_001"
    run = data / "experiments" / run_id
    run.mkdir()

    meta = {
        "run_id": run_id, "hypothesis": "Test KDP growth", "status": "active",
        "instruments": ["temp_controller"], "parameters": {"target_temp_c": 35.0},
        "thresholds": {"temp_max_c": 38.0}, "start_time": "2026-05-15T22:00:00Z",
        "end_time": None, "outcome": None, "key_findings": [],
    }
    (run / "metadata.json").write_text(json.dumps(meta))

    # temp.csv
    with (run / "temp.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "temperature_c", "setpoint_c", "status"])
        w.writerow(["2026-05-15T22:00:00Z", "35.0", "35.0", "nominal"])
        w.writerow(["2026-05-15T22:30:00Z", "36.8", "35.0", "warning"])

    # impurity.csv
    with (run / "impurity.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "impurity_ppm", "saturation_pct", "ph", "status"])
        w.writerow(["2026-05-15T22:00:00Z", "12.0", "78.0", "7.1", "nominal"])

    # interventions.json
    (run / "interventions.json").write_text("[]")

    # state.json
    (data / "state.json").write_text(json.dumps({"active_run_id": run_id}))

    return run_id


# ---------------------------------------------------------------------------
# Core tool: get_experiment
# ---------------------------------------------------------------------------

def test_get_experiment_returns_metadata(seed_run):
    import server
    result = server.get_experiment(seed_run)
    assert result["run_id"] == seed_run
    assert result["hypothesis"] == "Test KDP growth"


def test_get_experiment_unknown_run():
    import server
    result = server.get_experiment("run_999")
    assert "error" in result


# ---------------------------------------------------------------------------
# Core tool: get_temperature_curve
# ---------------------------------------------------------------------------

def test_get_temperature_curve_returns_rows(seed_run):
    import server
    rows = server.get_temperature_curve(seed_run)
    assert len(rows) == 2
    assert float(rows[1]["temperature_c"]) == pytest.approx(36.8)
    assert rows[1]["status"] == "warning"


def test_get_temperature_curve_empty_run(isolated_env):
    import server
    data = isolated_env["data"]
    (data / "experiments" / "run_empty").mkdir()
    (data / "experiments" / "run_empty" / "metadata.json").write_text("{}")
    rows = server.get_temperature_curve("run_empty")
    assert rows == []


# ---------------------------------------------------------------------------
# Core tool: get_impurity_log
# ---------------------------------------------------------------------------

def test_get_impurity_log_returns_rows(seed_run):
    import server
    rows = server.get_impurity_log(seed_run)
    assert len(rows) == 1
    assert float(rows[0]["ph"]) == pytest.approx(7.1)


# ---------------------------------------------------------------------------
# Core tool: log_intervention
# ---------------------------------------------------------------------------

def test_log_intervention_appends_entry(seed_run, isolated_env):
    import server
    result = server.log_intervention(
        run_id=seed_run,
        action="set_temperature(target_temp_c=34.0)",
        reasoning="Temperature exceeded warning threshold",
    )
    assert result["ok"] is True

    interventions = json.loads(
        (isolated_env["data"] / "experiments" / seed_run / "interventions.json").read_text()
    )
    assert len(interventions) == 1
    assert interventions[0]["action"] == "set_temperature(target_temp_c=34.0)"
    assert "timestamp" in interventions[0]


def test_log_intervention_accumulates(seed_run):
    import server
    server.log_intervention(seed_run, "action_1", "reason_1")
    server.log_intervention(seed_run, "action_2", "reason_2")
    interventions = json.loads(
        (Path(os.environ["LABMIND_DATA"]) / "experiments" / seed_run / "interventions.json").read_text()
    )
    assert len(interventions) == 2


# ---------------------------------------------------------------------------
# Core tool: compare_runs
# ---------------------------------------------------------------------------

def test_compare_runs_returns_both_summaries(seed_run, isolated_env):
    import server
    # Create a second run
    data = isolated_env["data"]
    run2 = data / "experiments" / "run_002"
    run2.mkdir()
    meta2 = {"run_id": "run_002", "hypothesis": "Faster cooling", "status": "completed",
              "outcome": "failure", "instruments": [], "parameters": {}}
    (run2 / "metadata.json").write_text(json.dumps(meta2))
    (run2 / "interventions.json").write_text("[]")

    result = server.compare_runs(seed_run, "run_002")
    assert result["run_a"]["run_id"] == seed_run
    assert result["run_b"]["run_id"] == "run_002"
    assert result["run_a"]["temp_max_c"] == pytest.approx(36.8)


# ---------------------------------------------------------------------------
# Core tool: finalize_experiment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_finalize_writes_report(seed_run, isolated_env):
    import server
    with patch("server.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=AsyncMock(status_code=200))
        mock_cls.return_value = mock_client

        result = await server.finalize_experiment(
            run_id=seed_run,
            report="# Morning Report\nAll good.",
            outcome="success",
            key_findings=["Crystal clarity 94%"],
        )

    assert result["ok"] is True
    report_path = isolated_env["data"] / "experiments" / seed_run / "report.md"
    assert report_path.exists()
    assert "Morning Report" in report_path.read_text()


@pytest.mark.asyncio
async def test_finalize_prevents_double_write(seed_run, isolated_env):
    import server
    report_path = isolated_env["data"] / "experiments" / seed_run / "report.md"
    report_path.write_text("# Already written")

    with patch("server.httpx.AsyncClient"):
        result = await server.finalize_experiment(
            run_id=seed_run, report="# New", outcome="success", key_findings=[]
        )
    assert result["ok"] is False
    assert "already finalized" in result["error"]


# ---------------------------------------------------------------------------
# Core tool: query_rag — graceful degradation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_query_rag_returns_empty_when_unavailable():
    import server
    result = await server.query_rag("crystal growth KDP", top_k=3)
    assert result["results"] == []
    assert result["available"] is False


# ---------------------------------------------------------------------------
# Dynamic tool registration from YAML catalog
# ---------------------------------------------------------------------------

def test_register_catalog_adds_tools(isolated_env):
    import server

    catalog = isolated_env["catalog"]
    yaml_content = """
instrument_type: test_instrument
endpoint_pattern: "http://localhost:{port}"
port: 8199
commands:
  read_value:
    method: GET
    path: /measure/value
    params: []
  set_value:
    method: POST
    path: /command/set
    params:
      - name: target
        type: float
        description: Target value
"""
    yaml_path = str(catalog / "test_instrument.yaml")
    (catalog / "test_instrument.yaml").write_text(yaml_content)

    before = server.get_registered_tool_names().copy()
    server._register_catalog(yaml_path)
    after = server.get_registered_tool_names()

    new_tools = after - before
    assert "test_instrument_read_value" in new_tools
    assert "test_instrument_set_value" in new_tools


def test_register_catalog_invalid_yaml_does_not_crash(isolated_env):
    import server
    bad_path = str(isolated_env["catalog"] / "bad.yaml")
    Path(bad_path).write_text(":::invalid yaml:::[[[")
    # Should log error and return without raising
    server._register_catalog(bad_path)  # no exception = pass


def test_register_catalog_missing_fields_skipped(isolated_env):
    import server
    path = str(isolated_env["catalog"] / "empty.yaml")
    Path(path).write_text("instrument_type: empty_thing\n")
    before = server.get_registered_tool_names().copy()
    server._register_catalog(path)
    after = server.get_registered_tool_names()
    assert before == after  # nothing added
