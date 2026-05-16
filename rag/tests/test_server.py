"""HTTP wire-contract tests for server.py.

Proves the JSON shapes the MCP server expects:
    POST /query   {"query": str, "top_k": int} -> {"results": [...]}
    POST /ingest  {"run_id": str}              -> {"status": "ok", "run_id": str}
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import rag.api as api_module
import rag.server as server_module
from rag.store import ChromaStore


@pytest.fixture
def client(tmp_chroma_path, fake_embedder, monkeypatch):
    api_module.reset_singletons()
    store = ChromaStore(path=tmp_chroma_path)
    monkeypatch.setattr(api_module, "_embedder", fake_embedder)
    monkeypatch.setattr(api_module, "_store", store)

    # Disable the seed step in the lifespan so tests start with an empty corpus.
    monkeypatch.setattr(server_module, "seed_unindexed", lambda *a, **kw: {})

    with TestClient(server_module.app) as c:
        yield c

    api_module.reset_singletons()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ingest_endpoint_happy_path(client, monkeypatch):
    from pathlib import Path
    REPO_ROOT = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("LABMIND_DATA", str(REPO_ROOT / "labmind-data"))

    r = client.post("/ingest", json={"run_id": "run_001"})
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "ok", "run_id": "run_001"}


def test_ingest_missing_run_returns_404(client):
    r = client.post("/ingest", json={"run_id": "run_does_not_exist"})
    assert r.status_code == 404


def test_query_endpoint_returns_results_wire_shape(client, monkeypatch):
    from pathlib import Path
    REPO_ROOT = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("LABMIND_DATA", str(REPO_ROOT / "labmind-data"))

    client.post("/ingest", json={"run_id": "run_001"})

    # Use the same profile text the ingest produced so the exact-match works.
    from rag.profile import build_profile
    profile = build_profile("run_001", REPO_ROOT / "labmind-data")

    r = client.post("/query", json={"query": profile.text, "top_k": 3})
    assert r.status_code == 200
    body = r.json()
    assert "results" in body
    assert len(body["results"]) >= 1

    result = body["results"][0]
    assert set(result.keys()) == {
        "run_id", "similarity", "summary",
        "instruments", "status", "key_differences",
    }
    assert result["run_id"] == "run_001"
    assert isinstance(result["instruments"], list)
    assert isinstance(result["key_differences"], list)


def test_query_rejects_invalid_top_k(client):
    r = client.post("/query", json={"query": "x", "top_k": 0})
    assert r.status_code == 422  # pydantic validation
