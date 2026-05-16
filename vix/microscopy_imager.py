from __future__ import annotations

import argparse
import asyncio
import base64
import os
import random
from io import BytesIO
from pathlib import Path

import httpx
import uvicorn
from PIL import Image, ImageDraw

from vix.instrument_base import InstrumentBase
from vix.scenario import Scenario
from vix.status import compute_status

SCENARIO_DIR = Path(__file__).parent / "scenarios"
IMAGE_SIZE = (256, 256)


class MicroscopyImager(InstrumentBase):
    instrument_type = "microscopy_imager"
    instrument_id = "microscopy_imager_01"
    name = "Crystal Microscopy Imager"
    capabilities = ["capture_image", "read_clarity_score", "read_defect_classification"]

    def __init__(self, scenario: Scenario, **kw) -> None:
        super().__init__(scenario=scenario, **kw)
        self._rng = random.Random(0)

        self.register_measure("clarity", lambda: {
            "value": self.scenario.sample("clarity_pct"), "unit": "%", "timestamp": self._now(),
        })
        self.register_measure("defects", lambda: {
            "value": int(round(self.scenario.sample("defect_count"))),
            "unit": "count", "timestamp": self._now(),
        })
        self.register_command("capture", self._capture)

    def build_readings(self) -> dict:
        return {
            "clarity_pct": self.scenario.sample("clarity_pct"),
            "defect_count": int(round(self.scenario.sample("defect_count"))),
        }

    async def _capture(self, body: dict) -> dict:
        b64 = self._render_image_b64()
        payload = {
            "instrument_id": self.instrument_id,
            "timestamp": self._now(),
            "readings": {"image_b64": b64},
            "status": compute_status(self.build_readings(), self.scenario.thresholds),
        }
        try:
            await self._client.post("/api/analytics", json=payload, timeout=5.0)
        except httpx.HTTPError:
            pass
        return {"ok": True, "image_b64": b64}

    def _render_image_b64(self) -> str:
        spec = self.scenario.phase_spec()["image"]
        base_color = tuple(spec["base_color"])
        noise_amp = int(spec["noise_amp"])
        defect_blobs = int(spec["defect_blobs"])

        img = Image.new("RGB", IMAGE_SIZE, base_color)
        px = img.load()
        for x in range(IMAGE_SIZE[0]):
            for y in range(IMAGE_SIZE[1]):
                r, g, b = px[x, y]
                jitter = self._rng.randint(-noise_amp, noise_amp)
                px[x, y] = (
                    max(0, min(255, r + jitter)),
                    max(0, min(255, g + jitter)),
                    max(0, min(255, b + jitter)),
                )

        draw = ImageDraw.Draw(img)
        for _ in range(defect_blobs):
            cx = self._rng.randint(0, IMAGE_SIZE[0] - 1)
            cy = self._rng.randint(0, IMAGE_SIZE[1] - 1)
            r = self._rng.randint(4, 12)
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(180, 30, 30))

        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")


async def _run(port: int) -> None:
    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
    interval = float(os.environ.get("VIX_INTERVAL_SECONDS", "60"))
    initial_phase = os.environ.get("SCENARIO", "baseline")
    scenario = Scenario(SCENARIO_DIR / "microscopy_imager.json")
    if initial_phase != "baseline":
        scenario.set_phase(initial_phase)
    async with httpx.AsyncClient(base_url=backend_url) as client:
        inst = MicroscopyImager(
            scenario=scenario,
            port=port,
            backend_client=client,
            interval_seconds=interval,
        )

        @inst.app.on_event("startup")
        async def _startup() -> None:
            asyncio.create_task(inst.register())
            asyncio.create_task(inst.analytics_loop())

        config = uvicorn.Config(inst.app, host="0.0.0.0", port=port, log_level="info")
        await uvicorn.Server(config).serve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8103)
    args = parser.parse_args()
    asyncio.run(_run(args.port))


if __name__ == "__main__":
    main()
