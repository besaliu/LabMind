from __future__ import annotations

import random
from pathlib import Path

import httpx
import pytest

from vix.ph_probe import PhProbe
from vix.scenario import Scenario
from vix.status import compute_status


def _make(backend_client, alpha=1.0):
    return PhProbe(
        scenario=Scenario(Path("scenarios/ph_probe.json"), rng=random.Random(0)),
        port=8102,
        backend_client=backend_client,
        interval_seconds=0.05,
        dynamics_alpha=alpha,
    )


@pytest.mark.asyncio
async def test_registration_payload(backend_client, mock_backend) -> None:
    inst = _make(backend_client)
    await inst.register()
    reg = mock_backend.registrations[0]
    assert reg["instrument_id"] == "ph_probe_01"
    assert reg["type"] == "ph_probe"
    assert reg["port"] == 8102
    for cap in ("read_ph", "read_saturation", "add_buffer"):
        assert cap in reg["capabilities"]


@pytest.mark.asyncio
async def test_measure_ph_baseline_range(backend_client) -> None:
    inst = _make(backend_client)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        body = (await c.get("/measure/ph")).json()
        assert 7.0 < body["value"] < 7.2


@pytest.mark.asyncio
async def test_build_readings_keys(backend_client) -> None:
    inst = _make(backend_client)
    assert set(inst.build_readings()) == {"ph", "saturation_pct", "impurity_ppm"}


@pytest.mark.asyncio
async def test_status_critical_under_failure_phase(backend_client) -> None:
    inst = _make(backend_client)
    inst.scenario.set_phase("failure")
    r = inst.build_readings()
    assert compute_status(r, inst.scenario.thresholds) == "critical"


@pytest.mark.asyncio
async def test_add_buffer_drives_ph_toward_target(backend_client) -> None:
    inst = _make(backend_client, alpha=1.0)
    inst.scenario.set_phase("failure")
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.post("/command/buffer", json={"target_ph": 7.0, "volume_ml": 5.0})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["new_value"] == 7.0
        ph = inst.build_readings()["ph"]
        assert abs(ph - 7.0) < 0.15
