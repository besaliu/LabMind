import os
import httpx
from fastapi import APIRouter

from models import RagQuery

router = APIRouter(prefix="/api/rag", tags=["rag"])

RAG_SERVICE_URL = os.environ.get("RAG_SERVICE_URL", "http://localhost:8002")


@router.post("/query")
async def query_rag(payload: RagQuery):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{RAG_SERVICE_URL}/query",
                json=payload.model_dump(),
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    # RAG service unavailable — return empty results so the rest of the system still works
    return {"results": [], "available": False}
