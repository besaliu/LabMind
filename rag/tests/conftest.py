"""Test fixtures.

Strategy:
- Real ChromaDB in a tmp path (per acceptance criteria — no Chroma mocks).
- Fake deterministic embedder by default (so the suite doesn't need Ollama).
- One real-Ollama test (test_e2e_with_ollama) gates on OLLAMA_HOST reachability.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

import rag.api as api_module
from rag.embeddings import OllamaEmbedder
from rag.store import ChromaStore

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_DATA_ROOT = REPO_ROOT / "labmind-data"
EMBED_DIM = 768  # match nomic-embed-text dim so the fake is shape-compatible


class FakeEmbedder:
    """Deterministic embedder for tests.

    Each text is hashed; the digest seeds a pseudo-random vector. Same text
    → same vector, so retrieving an exact-match query always returns the
    same-text doc with similarity 1.0. Different text → effectively random
    vector, so semantic similarity tests with this fake are meaningless
    (use the real Ollama test for those).
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return _hash_vector(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]

    def close(self) -> None:
        pass


def _hash_vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    # Stretch the 32-byte digest into EMBED_DIM normalized floats deterministically.
    seed = int.from_bytes(digest[:8], "big")
    import random

    rng = random.Random(seed)
    vec = [rng.uniform(-1.0, 1.0) for _ in range(EMBED_DIM)]
    # L2 normalize so cosine distance behaves cleanly.
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


@pytest.fixture
def tmp_chroma_path(tmp_path: Path) -> str:
    return str(tmp_path / "chroma")


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def rag_env(tmp_chroma_path: str, fake_embedder: FakeEmbedder, monkeypatch: pytest.MonkeyPatch):
    """Wire api.py's module singletons to the test embedder + a tmp Chroma store.

    Yields a small dict so tests can access the underlying instances if needed.
    """
    api_module.reset_singletons()
    store = ChromaStore(path=tmp_chroma_path)
    monkeypatch.setattr(api_module, "_embedder", fake_embedder)
    monkeypatch.setattr(api_module, "_store", store)
    monkeypatch.setenv("LABMIND_DATA", str(SEED_DATA_ROOT))
    yield {"store": store, "embedder": fake_embedder, "data_root": str(SEED_DATA_ROOT)}
    api_module.reset_singletons()


@pytest.fixture
def isolated_data_root(tmp_path: Path) -> Path:
    """A fresh experiments/ tree copied from the seed data, safe to mutate."""
    dst = tmp_path / "labmind-data"
    shutil.copytree(SEED_DATA_ROOT, dst)
    return dst


