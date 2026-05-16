"""Public RAG surface: ingest_experiment, query_similar.

These two functions are what server.py wraps over HTTP and what tests
import directly. Keeping the logic here (not in server.py) lets the unit
tests run without spinning up FastAPI.

Module-level singletons (`_embedder`, `_store`) are lazily created on
first call. This keeps cold-start cheap (no Ollama hit at import time)
and avoids leaking process-wide state into tests, which use the
configuration overrides in get_*() to inject fakes.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from rag.diff import compute_key_differences
from rag.embeddings import OllamaEmbedder
from rag.profile import build_profile
from rag.store import ChromaStore, Hit
from rag.models import SimilarityResult

logger = logging.getLogger(__name__)

DEFAULT_DATA_ROOT = "/labmind-data"
INGESTIBLE_STATUSES = {"completed", "failed"}

_embedder: Optional[OllamaEmbedder] = None
_store: Optional[ChromaStore] = None


def get_embedder() -> OllamaEmbedder:
    global _embedder
    if _embedder is None:
        _embedder = OllamaEmbedder()
    return _embedder


def get_store() -> ChromaStore:
    global _store
    if _store is None:
        _store = ChromaStore()
    return _store


def reset_singletons() -> None:
    """Test-only: drop module-level singletons so the next call rebuilds them."""
    global _embedder, _store
    if _embedder is not None:
        _embedder.close()
    _embedder = None
    _store = None


def ingest_experiment(run_id: str, data_root: str | None = None) -> None:
    """Read /labmind-data/experiments/{run_id}/, build profile, embed, upsert.

    Idempotent (uses upsert, so re-ingesting overwrites cleanly).
    Raises:
        FileNotFoundError: run dir missing.
        ValueError: status is not in {completed, failed} — only finalized
            runs are eligible for retrieval. Active/pending runs would
            pollute similarity results with half-baked outcomes.
    """
    root = data_root or os.getenv("LABMIND_DATA") or DEFAULT_DATA_ROOT
    profile = build_profile(run_id, root)
    status = profile.metadata.get("status", "")
    if status not in INGESTIBLE_STATUSES:
        raise ValueError(
            f"run {run_id} has status={status!r}; only "
            f"{sorted(INGESTIBLE_STATUSES)} are ingestible"
        )

    embedding = get_embedder().embed(profile.text)
    get_store().upsert(
        run_id=profile.run_id,
        embedding=embedding,
        text=profile.text,
        metadata=profile.metadata,
    )
    logger.info("ingested run %s (text len=%d)", run_id, len(profile.text))


def query_similar(doc_text: str, top_k: int = 5) -> list[SimilarityResult]:
    """Embed doc_text, return top-k hits sorted by similarity desc.

    Each hit is enriched with summary (from stored metadata) and
    key_differences (computed against the query). doc_text is expected
    to be a structured profile string in the same shape produced by
    build_profile() — this matches the upload-time contract where the
    backend hands RAG an already-structured doc.
    """
    if not doc_text or not doc_text.strip():
        return []
    embedding = get_embedder().embed(doc_text)
    hits = get_store().query(embedding=embedding, top_k=top_k)
    return [_to_similarity_result(h, doc_text) for h in hits]


def _to_similarity_result(hit: Hit, query_text: str) -> SimilarityResult:
    meta = hit.metadata or {}
    instruments_raw = meta.get("instruments", "")
    instruments = [i for i in str(instruments_raw).split("|") if i]
    summary = _summary_from_metadata(meta)
    differences = compute_key_differences(
        query_text=query_text,
        hit_metadata=meta,
        hit_text=hit.text,
    )
    return SimilarityResult(
        run_id=hit.run_id,
        similarity=hit.similarity,
        summary=summary,
        instruments=instruments,
        status=str(meta.get("status", "")),
        key_differences=differences,
    )


def _summary_from_metadata(meta: dict) -> str:
    """Reconstruct a one-liner summary from stored metadata.

    Mirrors profile._render_summary() but works from the flat Chroma
    metadata dict (we don't store the summary string separately).
    """
    substrate = meta.get("substrate") or "?"
    target = meta.get("target_temp_c") or "?"
    rate = meta.get("cooling_rate_c_per_hour") or "?"
    status = meta.get("status", "unknown")
    outcome = meta.get("outcome", "unknown")
    target_str = f"{float(target):.1f}C" if isinstance(target, (int, float)) else str(target)
    rate_str = f"{float(rate):.1f}C/hr" if isinstance(rate, (int, float)) else str(rate)
    return f"{substrate} growth at {target_str}, {rate_str} cooling — {status} ({outcome})"
