"""Thin wrapper around Ollama's /api/embed endpoint.

We own the embedding step ourselves (rather than wrapping it as a
chromadb.EmbeddingFunction) so we have a single retry point, get clear
error surfaces, and avoid version-coupling pain with chromadb's embedding
function interface.
"""
from __future__ import annotations

import os
import time

import httpx

DEFAULT_MODEL = "nomic-embed-text"
DEFAULT_HOST = "http://localhost:11434"
DEFAULT_TIMEOUT = 30.0


class EmbeddingError(RuntimeError):
    """Raised when Ollama returns no embeddings or an unexpected payload."""


class OllamaEmbedder:
    def __init__(
        self,
        host: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self._host = (host or os.getenv("OLLAMA_HOST") or DEFAULT_HOST).rstrip("/")
        self._model = model
        self._client = httpx.Client(timeout=timeout)

    def embed(self, text: str) -> list[float]:
        vectors = self._embed_request([text])
        return vectors[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._embed_request(texts)

    def _embed_request(self, inputs: list[str]) -> list[list[float]]:
        url = f"{self._host}/api/embed"
        payload = {"model": self._model, "input": inputs}
        try:
            resp = self._client.post(url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError:
            # one retry — Ollama may be cold-starting on first call
            time.sleep(0.5)
            resp = self._client.post(url, json=payload)
            resp.raise_for_status()

        body = resp.json()
        embeddings = body.get("embeddings")
        if not embeddings or not isinstance(embeddings, list):
            raise EmbeddingError(
                f"unexpected ollama response shape: keys={list(body.keys())}"
            )
        return embeddings

    def close(self) -> None:
        self._client.close()
