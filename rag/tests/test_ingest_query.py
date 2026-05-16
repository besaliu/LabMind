"""End-to-end ingest + query against a real ChromaDB with a fake embedder.

The fake embedder produces deterministic same-text-same-vector embeddings,
so exact-match retrieval works perfectly. Semantic similarity (paraphrase
matching) is *not* meaningful with this fake — see test_e2e.py for that
under a real Ollama.
"""
from __future__ import annotations

from rag.api import ingest_experiment, query_similar
from rag.profile import build_profile


def test_ingest_run_001_is_retrievable(rag_env):
    ingest_experiment("run_001")
    assert rag_env["store"].count() == 1

    p = build_profile("run_001", rag_env["data_root"])
    results = query_similar(p.text, top_k=3)

    assert len(results) >= 1
    assert results[0].run_id == "run_001"
    assert results[0].similarity > 0.99  # exact-match with deterministic embedder


def test_ingest_active_run_rejected(rag_env, isolated_data_root, monkeypatch):
    """Active experiments must not be ingested — would pollute results."""
    import json
    md_path = isolated_data_root / "experiments" / "run_001" / "metadata.json"
    md = json.loads(md_path.read_text())
    md["status"] = "active"
    md_path.write_text(json.dumps(md))

    import pytest
    with pytest.raises(ValueError, match="status"):
        ingest_experiment("run_001", data_root=str(isolated_data_root))


def test_ingest_is_idempotent(rag_env):
    ingest_experiment("run_001")
    ingest_experiment("run_001")
    ingest_experiment("run_001")
    assert rag_env["store"].count() == 1


def test_query_returns_correct_shape(rag_env):
    ingest_experiment("run_001")
    p = build_profile("run_001", rag_env["data_root"])
    results = query_similar(p.text, top_k=1)

    assert len(results) == 1
    r = results[0]
    # Wire-contract field set — must match what the MCP server expects.
    assert r.run_id == "run_001"
    assert 0.0 <= r.similarity <= 1.0
    assert isinstance(r.summary, str) and r.summary
    assert isinstance(r.instruments, list) and r.instruments
    assert r.status == "completed"
    assert isinstance(r.key_differences, list)


def test_query_against_empty_collection_returns_empty(rag_env):
    assert query_similar("anything", top_k=5) == []


def test_query_empty_text_returns_empty(rag_env):
    ingest_experiment("run_001")
    assert query_similar("", top_k=5) == []


def test_seed_picks_up_finalized_runs(rag_env):
    """seed_unindexed ingests both seed runs (both are completed)."""
    from rag.seed import seed_unindexed
    report = seed_unindexed(data_root=rag_env["data_root"])
    assert set(report["ingested"]) == {"run_001", "run_002"}
    assert rag_env["store"].count() == 2


def test_chromadb_persists_across_reopen(tmp_chroma_path, fake_embedder, monkeypatch):
    """Re-opening a ChromaStore at the same path must see prior data."""
    import rag.api as api_module
    from rag.store import ChromaStore
    from rag.api import ingest_experiment

    api_module.reset_singletons()
    monkeypatch.setenv("LABMIND_DATA", str((__import__("pathlib").Path(__file__).resolve().parents[2] / "labmind-data")))
    monkeypatch.setattr(api_module, "_embedder", fake_embedder)
    monkeypatch.setattr(api_module, "_store", ChromaStore(path=tmp_chroma_path))

    ingest_experiment("run_001")

    # Reopen
    api_module.reset_singletons()
    monkeypatch.setattr(api_module, "_embedder", fake_embedder)
    fresh_store = ChromaStore(path=tmp_chroma_path)
    monkeypatch.setattr(api_module, "_store", fresh_store)

    assert fresh_store.count() == 1
    assert fresh_store.has("run_001")
