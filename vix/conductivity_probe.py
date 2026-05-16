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


class ConductivityProbe(InstrumentBase):
    instrument_type = "conductivity_probe"
    instrument_id = "conductivity_probe_04"
    name = "Solution Conductivity Probe"
    capabilities = ["read_conductivity", "set_alert_threshold"]

    def __init__(self, scenario: Scenario, **kw) -> None:
        super().__init__(scenario=scenario, **kw)
        self._alert_threshold: float = 9.0

        self.register_measure("conductivity", lambda: {
            "conductivity_ms_cm": round(self.scenario.sample("conductivity_ms_cm"), 2),
            "temperature_c": round(self.scenario.sample("temperature_c"), 2),
            "alert_threshold_ms_cm": self._alert_threshold,
            "status": self._conductivity_status(),
            "timestamp": self._now(),
        })
        self.register_command("set_alert_threshold", self._set_alert_threshold)

    def _conductivity_status(self) -> str:
        val = self.scenario.sample("conductivity_ms_cm")
        if val < self._alert_threshold:
            return "alert"
        thresholds = self.scenario.thresholds.get("conductivity_ms_cm", {})
        nom_lo, nom_hi = thresholds.get("nominal", [9.0, 14.5])
        if nom_lo <= val <= nom_hi:
            return "nominal"
        return "warning"

    def _set_alert_threshold(self, body: dict) -> dict:
        self._alert_threshold = float(body["threshold_ms_cm"])
        return {"ok": True, "threshold_ms_cm": self._alert_threshold}

    def build_readings(self) -> dict:
        return {
            "conductivity_ms_cm": round(self.scenario.sample("conductivity_ms_cm"), 2),
            "temperature_c": round(self.scenario.sample("temperature_c"), 2),
        }


async def _run(port: int) -> None:
    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
    interval = float(os.environ.get("VIX_INTERVAL_SECONDS", "30"))
    initial_phase = os.environ.get("SCENARIO", "baseline")
    scenario = Scenario(SCENARIO_DIR / "conductivity_probe.json")
    if initial_phase != "baseline":
        scenario.set_phase(initial_phase)
    async with httpx.AsyncClient(base_url=backend_url) as client:
        inst = ConductivityProbe(
            scenario=scenario,
            port=port,
            backend_client=client,
            interval_seconds=interval,
        )
        config = uvicorn.Config(inst.app, host="0.0.0.0", port=port, log_level="info")
        await uvicorn.Server(config).serve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8104)
    args = parser.parse_args()
    asyncio.run(_run(args.port))


if __name__ == "__main__":
    main()
