"""Optional end-to-end test against real Ollama.

This is the only test that proves *semantic* similarity behavior:
  - paraphrased crystal-growth queries retrieve crystal-growth runs
  - unrelated queries (biology) score below the block threshold

Skipped automatically if OLLAMA_HOST is not reachable. Run locally with:
    OLLAMA_HOST=http://localhost:11434 pytest tests/test_e2e_ollama.py
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

import rag.api as api_module
from rag.api import ingest_experiment, query_similar
from rag.embeddings import OllamaEmbedder
from rag.profile import build_profile
from rag.store import ChromaStore

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_DATA_ROOT = REPO_ROOT / "labmind-data"


def _ollama_reachable() -> bool:
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    try:
        return httpx.get(f"{host}/api/tags", timeout=1.0).status_code == 200
    except Exception:  # noqa: BLE001
        return False


ollama_required = pytest.mark.skipif(
    not _ollama_reachable(), reason="Ollama not reachable at OLLAMA_HOST"
)


@pytest.fixture
def real_rag_env(tmp_path, monkeypatch):
    api_module.reset_singletons()
    monkeypatch.setattr(api_module, "_embedder", OllamaEmbedder())
    monkeypatch.setattr(api_module, "_store", ChromaStore(path=str(tmp_path / "chroma")))
    monkeypatch.setenv("LABMIND_DATA", str(SEED_DATA_ROOT))
    yield
    api_module.reset_singletons()


@ollama_required
def test_exact_profile_retrieves_self_with_high_similarity(real_rag_env):
    ingest_experiment("run_001")
    p = build_profile("run_001", SEED_DATA_ROOT)
    results = query_similar(p.text, top_k=3)
    assert results[0].run_id == "run_001"
    assert results[0].similarity > 0.95


@ollama_required
def test_unrelated_query_scores_below_threshold(real_rag_env):
    """Acceptance criterion: an unrelated biology query should not match
    crystal-growth runs above the 0.85 block threshold."""
    ingest_experiment("run_001")
    ingest_experiment("run_002")

    results = query_similar(
        "Hypothesis: investigating mouse hippocampus neurogenesis under stress\n"
        "Instruments: fluorescence_microscope, behavioral_chamber\n"
        "Parameters: target_temp=22.0C, animal=mouse, age_weeks=8\n",
        top_k=2,
    )
    if results:
        assert results[0].similarity < 0.85, (
            f"unrelated query matched too strongly: {results[0].similarity}"
        )


@ollama_required
def test_similar_but_different_temp_returns_key_diff(real_rag_env):
    """A paraphrase of run_001 with a different setpoint should still
    match run_001 as top hit AND surface the temperature delta in
    key_differences."""
    ingest_experiment("run_001")
    p = build_profile("run_001", SEED_DATA_ROOT)
    # Mutate the target_temp from 35C → 38C in the same template.
    mutated = p.text.replace("target_temp=35.0C", "target_temp=38.0C")

    results = query_similar(mutated, top_k=1)
    assert results[0].run_id == "run_001"
    assert any("temperature setpoint" in d for d in results[0].key_differences)
