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


class TempController(InstrumentBase):
    instrument_type = "temp_controller"
    instrument_id = "temp_controller_01"
    name = "Crystal Growth Temperature Controller"
    capabilities = [
        "read_temperature",
        "set_temperature",
        "read_cooling_rate",
        "set_cooling_rate",
    ]

    def __init__(self, scenario: Scenario, dynamics_alpha: float = 0.4, **kw) -> None:
        super().__init__(scenario=scenario, **kw)
        self._setpoint_override: float | None = None
        self._cooling_rate_override: float | None = None
        self._temp_state: float | None = None
        self._alpha = dynamics_alpha

        self.register_measure("temperature", lambda: {
            "value": self._next_temperature(), "unit": "C", "timestamp": self._now(),
        })
        self.register_measure("setpoint", lambda: {
            "value": self._setpoint(), "unit": "C", "timestamp": self._now(),
        })
        self.register_measure("cooling_rate", lambda: {
            "value": self._cooling_rate(), "unit": "C/h", "timestamp": self._now(),
        })
        self.register_command("temperature", self._set_temperature)
        self.register_command("cooling_rate", self._set_cooling_rate)

    def _setpoint(self) -> float:
        if self._setpoint_override is not None:
            return self._setpoint_override
        return self.scenario.sample("setpoint_c")

    def _cooling_rate(self) -> float:
        if self._cooling_rate_override is not None:
            return self._cooling_rate_override
        return self.scenario.sample("cooling_rate_c_per_hour")

    def _next_temperature(self) -> float:
        sample = self.scenario.sample("temperature_c")
        if self._setpoint_override is None:
            self._temp_state = sample
            return sample
        if self._temp_state is None:
            self._temp_state = sample
        target = self._setpoint_override
        self._temp_state = self._temp_state + self._alpha * (target - self._temp_state)
        return self._temp_state

    def _set_temperature(self, body: dict) -> dict:
        v = float(body["target_temp_c"])
        self._setpoint_override = v
        return {"ok": True, "new_value": v}

    def _set_cooling_rate(self, body: dict) -> dict:
        v = float(body["rate_c_per_hour"])
        self._cooling_rate_override = v
        return {"ok": True, "new_value": v}

    def build_readings(self) -> dict:
        return {
            "temperature_c": self._next_temperature(),
            "setpoint_c": self._setpoint(),
            "cooling_rate_c_per_hour": self._cooling_rate(),
        }


async def _run(port: int) -> None:
    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
    interval = float(os.environ.get("VIX_INTERVAL_SECONDS", "30"))
    initial_phase = os.environ.get("SCENARIO", "baseline")
    scenario = Scenario(SCENARIO_DIR / "temp_controller.json")
    if initial_phase != "baseline":
        scenario.set_phase(initial_phase)
    async with httpx.AsyncClient(base_url=backend_url) as client:
        inst = TempController(
            scenario=scenario,
            port=port,
            backend_client=client,
            interval_seconds=interval,
        )

        config = uvicorn.Config(inst.app, host="0.0.0.0", port=port, log_level="info")
        await uvicorn.Server(config).serve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8101)
    args = parser.parse_args()
    asyncio.run(_run(args.port))


if __name__ == "__main__":
    main()
