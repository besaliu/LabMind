"""ChromaDB persistence layer for experiment profiles.

Single collection: experiment_profiles, cosine distance space, 768-dim
vectors from nomic-embed-text. We pass embeddings in directly (rather than
registering a chromadb.EmbeddingFunction) so embedding errors surface at
the caller, not inside Chroma.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import chromadb

DEFAULT_CHROMADB_PATH = "/labmind-data/chromadb"
COLLECTION_NAME = "experiment_profiles"


@dataclass
class Hit:
    run_id: str
    similarity: float
    text: str
    metadata: dict[str, Any]


class ChromaStore:
    def __init__(self, path: str | None = None):
        self._path = path or os.getenv("CHROMADB_PATH") or DEFAULT_CHROMADB_PATH
        self._client = chromadb.PersistentClient(path=self._path)
        self._coll = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(
        self,
        run_id: str,
        embedding: list[float],
        text: str,
        metadata: dict[str, Any],
    ) -> None:
        self._coll.upsert(
            ids=[run_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata],
        )

    def has(self, run_id: str) -> bool:
        got = self._coll.get(ids=[run_id])
        return bool(got and got.get("ids"))

    def existing_ids(self) -> set[str]:
        got = self._coll.get()
        return set(got.get("ids", []) or [])

    def query(self, embedding: list[float], top_k: int) -> list[Hit]:
        if top_k <= 0:
            return []
        # Chroma errors on n_results > collection size; clamp defensively.
        size = self._coll.count()
        if size == 0:
            return []
        n = min(top_k, size)
        result = self._coll.query(
            query_embeddings=[embedding],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]

        hits: list[Hit] = []
        for run_id, doc, meta, dist in zip(ids, docs, metas, dists):
            # Cosine distance in Chroma is 1 - cosine_similarity, so similarity = 1 - distance.
            # Clamp to [0, 1] — floating point can push it microscopically outside.
            similarity = max(0.0, min(1.0, 1.0 - float(dist)))
            hits.append(
                Hit(
                    run_id=run_id,
                    similarity=similarity,
                    text=doc or "",
                    metadata=dict(meta or {}),
                )
            )
        return hits

    def count(self) -> int:
        return self._coll.count()
