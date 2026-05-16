from __future__ import annotations

import random
from pathlib import Path

import httpx
import pytest

from vix.scenario import Scenario
from vix.temp_controller import TempController


def _make(backend_client, alpha=1.0):
    return TempController(
        scenario=Scenario(Path("scenarios/temp_controller.json"), rng=random.Random(0)),
        port=8101,
        backend_client=backend_client,
        interval_seconds=0.05,
        dynamics_alpha=alpha,
    )


@pytest.mark.asyncio
async def test_registration_payload(backend_client, mock_backend) -> None:
    inst = _make(backend_client)
    await inst.register()
    reg = mock_backend.registrations[0]
    assert reg["instrument_id"] == "temp_controller_01"
    assert reg["type"] == "temp_controller"
    assert reg["port"] == 8101
    for cap in ("read_temperature", "set_temperature", "read_cooling_rate", "set_cooling_rate"):
        assert cap in reg["capabilities"]


@pytest.mark.asyncio
async def test_measure_temperature_baseline(backend_client) -> None:
    inst = _make(backend_client)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        body = (await c.get("/measure/temperature")).json()
        assert body["unit"] == "C"
        assert 34.8 < body["value"] < 35.2


@pytest.mark.asyncio
async def test_build_readings_has_required_keys(backend_client) -> None:
    inst = _make(backend_client)
    readings = inst.build_readings()
    assert {"temperature_c", "setpoint_c", "cooling_rate_c_per_hour"} <= set(readings)


@pytest.mark.asyncio
async def test_set_temperature_changes_setpoint_immediately(backend_client) -> None:
    inst = _make(backend_client, alpha=1.0)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.post("/command/temperature", json={"target_temp_c": 34.0})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "new_value": 34.0}
        readings = inst.build_readings()
        assert readings["setpoint_c"] == 34.0


@pytest.mark.asyncio
async def test_intervention_converges_temperature_under_failure(backend_client) -> None:
    inst = _make(backend_client, alpha=1.0)
    inst.scenario.set_phase("failure")
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r1 = inst.build_readings()
        from vix.status import compute_status
        assert compute_status(r1, inst.scenario.thresholds) == "critical"

        await c.post("/command/temperature", json={"target_temp_c": 35.0})
        r2 = inst.build_readings()
        assert 34.7 <= r2["temperature_c"] <= 35.3
        assert compute_status(r2, inst.scenario.thresholds) == "nominal"


@pytest.mark.asyncio
async def test_set_cooling_rate_command(backend_client) -> None:
    inst = _make(backend_client)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.post("/command/cooling_rate", json={"rate_c_per_hour": 1.5})
        assert r.status_code == 200
        readings = inst.build_readings()
        assert readings["cooling_rate_c_per_hour"] == 1.5
