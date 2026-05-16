"""FastAPI HTTP wrapper for the RAG library.

Wire contract (agreed with the MCP server team):
    POST /query   {"query": str, "top_k": int}  -> {"results": [...]}
    POST /ingest  {"run_id": str}               -> {"status": "ok", "run_id": str}
    GET  /health                                -> {"status": "ok"}

Each result in /query matches the SimilarityResult dataclass serialized
to JSON (run_id, similarity, summary, instruments, status, key_differences).

Seed bootstrap runs in the lifespan startup so the corpus is warm by the
time the first request arrives.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from rag.api import ingest_experiment, query_similar
from rag.seed import seed_unindexed

logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=50)


class IngestRequest(BaseModel):
    run_id: str = Field(min_length=1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        report = seed_unindexed()
        logger.info("startup seed report: %s", report)
    except Exception:  # noqa: BLE001
        logger.exception("startup seed failed (non-fatal)")
    yield


app = FastAPI(title="LabMind RAG", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/query")
def query(req: QueryRequest) -> dict:
    results = query_similar(req.query, req.top_k)
    return {"results": [asdict(r) for r in results]}


@app.post("/ingest")
def ingest(req: IngestRequest) -> dict:
    try:
        ingest_experiment(req.run_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "run_id": req.run_id}
