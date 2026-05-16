from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path

import httpx
import pytest

from vix.instrument_base import InstrumentBase
from vix.scenario import Scenario


def _spec(tmp_path: Path) -> Path:
    spec = {
        "thresholds": {"value": {"nominal": [0.0, 2.0], "warning": [-1.0, 8.0]}},
        "baseline": {"readings": {"value": {"mean": 1.0, "noise": 0.0}}},
        "failure":  {"readings": {"value": {"mean": 9.0, "noise": 0.0}}},
    }
    p = tmp_path / "dummy.json"
    p.write_text(json.dumps(spec))
    return p


class DummyInstrument(InstrumentBase):
    instrument_type = "dummy"
    instrument_id = "dummy_01"
    name = "Dummy"
    capabilities = ["read_value", "set_value"]

    def __init__(self, scenario: Scenario, **kw):
        super().__init__(scenario=scenario, **kw)
        self.last_set: float | None = None
        self.register_measure("value", lambda: {
            "value": self.scenario.sample("value"), "unit": "x", "timestamp": self._now(),
        })
        self.register_command("value", self._set_value)

    def _set_value(self, body: dict) -> dict:
        self.last_set = float(body["value"])
        return {"ok": True, "new_value": self.last_set}

    def build_readings(self) -> dict:
        return {"value": self.scenario.sample("value")}


@pytest.mark.asyncio
async def test_health(tmp_path, backend_client) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "instrument_id": "dummy_01"}


@pytest.mark.asyncio
async def test_self_registers_on_startup(tmp_path, backend_client, mock_backend) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    await inst.register()
    reg = mock_backend.registrations[0]
    assert reg["instrument_id"] == "dummy_01"
    assert reg["type"] == "dummy"
    assert reg["port"] == 9999
    assert reg["capabilities"] == ["read_value", "set_value"]


@pytest.mark.asyncio
async def test_analytics_loop_emits_on_interval_with_status(tmp_path, backend_client, mock_backend) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    task = asyncio.create_task(inst.analytics_loop())
    await asyncio.sleep(0.18)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert len(mock_backend.analytics) >= 2
    p = mock_backend.analytics[0]
    assert p["instrument_id"] == "dummy_01"
    assert p["readings"]["value"] == 1.0
    assert p["status"] == "nominal"
    assert p["timestamp"].endswith("Z")


@pytest.mark.asyncio
async def test_analytics_loop_status_reflects_phase(tmp_path, backend_client, mock_backend) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    inst.scenario.set_phase("failure")
    task = asyncio.create_task(inst.analytics_loop())
    await asyncio.sleep(0.12)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert mock_backend.analytics[0]["status"] == "critical"


@pytest.mark.asyncio
async def test_analytics_loop_survives_409(tmp_path, backend_client, mock_backend) -> None:
    mock_backend.reject_analytics = True
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    task = asyncio.create_task(inst.analytics_loop())
    await asyncio.sleep(0.12)
    mock_backend.reject_analytics = False
    await asyncio.sleep(0.12)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    assert len(mock_backend.analytics) >= 1


@pytest.mark.asyncio
async def test_measure_endpoint(tmp_path, backend_client) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.get("/measure/value")
        assert r.status_code == 200
        assert r.json()["value"] == 1.0


@pytest.mark.asyncio
async def test_unknown_measure_404(tmp_path, backend_client) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        assert (await c.get("/measure/nope")).status_code == 404


@pytest.mark.asyncio
async def test_command_endpoint_dispatches_sync(tmp_path, backend_client) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.post("/command/value", json={"value": 7.5})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "new_value": 7.5}
        assert inst.last_set == 7.5


@pytest.mark.asyncio
async def test_command_endpoint_dispatches_async(tmp_path, backend_client) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)

    async def async_handler(body: dict) -> dict:
        await asyncio.sleep(0)
        return {"ok": True, "asynced": True, "value": body.get("v")}

    inst.register_command("async_action", async_handler)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.post("/command/async_action", json={"v": 3})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "asynced": True, "value": 3}


@pytest.mark.asyncio
async def test_scenario_phase_endpoint(tmp_path, backend_client) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.post("/scenario/phase", json={"phase": "failure"})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "phase": "failure"}
        m = (await c.get("/measure/value")).json()
        assert m["value"] == 9.0


@pytest.mark.asyncio
async def test_scenario_phase_unknown_400(tmp_path, backend_client) -> None:
    inst = DummyInstrument(scenario=Scenario(_spec(tmp_path), rng=random.Random(0)),
                            port=9999, backend_client=backend_client, interval_seconds=0.05)
    transport = httpx.ASGITransport(app=inst.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://inst") as c:
        r = await c.post("/scenario/phase", json={"phase": "explode"})
        assert r.status_code == 400
