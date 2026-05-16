from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import httpx
import uvicorn

from vix.instrument_base import InstrumentBase
from vix.scenario import Scenario

SCENARIO_DIR = Path(__file__).parent / "scenarios"


class PhProbe(InstrumentBase):
    instrument_type = "ph_probe"
    instrument_id = "ph_probe_01"
    name = "Solution pH and Saturation Probe"
    capabilities = ["read_ph", "read_saturation", "add_buffer"]

    def __init__(self, scenario: Scenario, dynamics_alpha: float = 0.4, **kw) -> None:
        super().__init__(scenario=scenario, **kw)
        self._ph_override: float | None = None
        self._ph_state: float | None = None
        self._alpha = dynamics_alpha

        self.register_measure("ph", lambda: {
            "value": self._next_ph(), "unit": "pH", "timestamp": self._now(),
        })
        self.register_measure("saturation", lambda: {
            "value": self.scenario.sample("saturation_pct"), "unit": "%", "timestamp": self._now(),
        })
        self.register_command("buffer", self._add_buffer)

    def _next_ph(self) -> float:
        sample = self.scenario.sample("ph")
        if self._ph_override is None:
            self._ph_state = sample
            return sample
        if self._ph_state is None:
            self._ph_state = sample
        self._ph_state = self._ph_state + self._alpha * (self._ph_override - self._ph_state)
        return self._ph_state

    def _add_buffer(self, body: dict) -> dict:
        target = float(body["target_ph"])
        _ = float(body.get("volume_ml", 0.0))
        self._ph_override = target
        return {"ok": True, "new_value": target}

    def build_readings(self) -> dict:
        return {
            "ph": self._next_ph(),
            "saturation_pct": self.scenario.sample("saturation_pct"),
            "impurity_ppm": self.scenario.sample("impurity_ppm"),
        }


async def _run(port: int) -> None:
    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
    interval = float(os.environ.get("VIX_INTERVAL_SECONDS", "30"))
    initial_phase = os.environ.get("SCENARIO", "baseline")
    scenario = Scenario(SCENARIO_DIR / "ph_probe.json")
    if initial_phase != "baseline":
        scenario.set_phase(initial_phase)
    async with httpx.AsyncClient(base_url=backend_url) as client:
        inst = PhProbe(
            scenario=scenario,
            port=port,
            backend_client=client,
            interval_seconds=interval,
        )

        config = uvicorn.Config(inst.app, host="0.0.0.0", port=port, log_level="info")
        await uvicorn.Server(config).serve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8102)
    args = parser.parse_args()
    asyncio.run(_run(args.port))


if __name__ == "__main__":
    main()
