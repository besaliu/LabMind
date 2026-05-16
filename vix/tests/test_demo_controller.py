from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request

from vix.demo_controller import drive_phase


@pytest.mark.asyncio
async def test_drive_phase_posts_to_each_instrument() -> None:
    captured: list[tuple[str, dict]] = []

    def make_app(label: str) -> FastAPI:
        app = FastAPI()

        @app.post("/scenario/phase")
        async def hit(req: Request) -> dict:
            payload = await req.json()
            captured.append((label, payload))
            return {"ok": True, "phase": payload.get("phase")}

        return app

    clients = {
        "temp": httpx.AsyncClient(transport=httpx.ASGITransport(app=make_app("temp")), base_url="http://temp"),
        "ph":   httpx.AsyncClient(transport=httpx.ASGITransport(app=make_app("ph")),   base_url="http://ph"),
        "img":  httpx.AsyncClient(transport=httpx.ASGITransport(app=make_app("img")),  base_url="http://img"),
    }
    try:
        results = await drive_phase("failure", list(clients.values()))
    finally:
        for c in clients.values():
            await c.aclose()
    assert len(results) == 3
    assert all(r["ok"] for r in results)
    assert {label for label, _ in captured} == {"temp", "ph", "img"}
    assert all(body == {"phase": "failure"} for _, body in captured)
