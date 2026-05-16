from __future__ import annotations

from typing import Any

import httpx
import pytest_asyncio
from fastapi import FastAPI, HTTPException, Request


class MockBackend:
    """FastAPI app that captures register/analytics calls and can return 409 for analytics."""

    def __init__(self) -> None:
        self.registrations: list[dict[str, Any]] = []
        self.analytics: list[dict[str, Any]] = []
        self.reject_analytics: bool = False
        self.app = FastAPI()

        @self.app.post("/api/instruments/register")
        async def register(req: Request) -> dict[str, Any]:
            self.registrations.append(await req.json())
            return {"ok": True, "run_id": None}

        @self.app.post("/api/analytics")
        async def analytics(req: Request) -> dict[str, Any]:
            payload = await req.json()
            if self.reject_analytics:
                raise HTTPException(409, "No active experiment")
            self.analytics.append(payload)
            return {"ok": True}


@pytest_asyncio.fixture
async def mock_backend() -> MockBackend:
    return MockBackend()


@pytest_asyncio.fixture
async def backend_client(mock_backend: MockBackend):
    transport = httpx.ASGITransport(app=mock_backend.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend") as c:
        yield c
