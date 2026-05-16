from __future__ import annotations

import base64
import random
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from PIL import Image

from vix.microscopy_imager import MicroscopyImager
from vix.scenario import Scenario
from vix.status import compute_status


def _make(backend_client):
    return MicroscopyImager(
        scenario=Scenario(Path("scenarios/microscopy_imager.json"), rng=random.Random(0)),
        port=8103,
        backend_client=backend_client,
        interval_seconds=0.05,
    )


@pytest.mark.asyncio
async def test_registration_payload(backend_client, mock_backend) -> None:
    inst = _make(backend_client)
    await inst.register()
    reg = mock_backend.registrations[0]
    assert reg["instrument_id"] == "microscopy_imager_01"
    assert reg["type"] == "microscopy_imager"
    assert reg["port"] == 8103
    for cap in ("capture_image", "read_clarity_score", "read_defect_classification"):
        assert cap in reg["capabilities"]


@pytest.mark.asyncio
async def test_measure_clarity_baseline(backend_client) -> None:
    inst = _make(backend_client)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        body = (await c.get("/measure/clarity")).json()
        assert 90.0 < body["value"] < 94.0


@pytest.mark.asyncio
async def test_measure_defects_baseline(backend_client) -> None:
    inst = _make(backend_client)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        body = (await c.get("/measure/defects")).json()
        assert 0 <= body["value"] <= 2


@pytest.mark.asyncio
async def test_build_readings_excludes_image(backend_client) -> None:
    inst = _make(backend_client)
    r = inst.build_readings()
    assert set(r) == {"clarity_pct", "defect_count"}
    assert "image_b64" not in r


@pytest.mark.asyncio
async def test_status_critical_during_failure(backend_client) -> None:
    inst = _make(backend_client)
    inst.scenario.set_phase("failure")
    r = inst.build_readings()
    assert compute_status(r, inst.scenario.thresholds) == "critical"


@pytest.mark.asyncio
async def test_capture_image_posts_b64_analytics(backend_client, mock_backend) -> None:
    inst = _make(backend_client)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.post("/command/capture", json={})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        img = Image.open(BytesIO(base64.b64decode(body["image_b64"])))
        assert img.format == "PNG"
    img_posts = [p for p in mock_backend.analytics if "image_b64" in p["readings"]]
    assert len(img_posts) == 1
    assert img_posts[0]["instrument_id"] == "microscopy_imager_01"
