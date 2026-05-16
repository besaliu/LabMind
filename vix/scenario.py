from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any


class Scenario:
    """Phase-based reading generator loaded from a JSON spec file.

    Spec shape:
        {
            "thresholds": { metric: {"nominal": [lo, hi], "warning": [lo, hi]} },
            "<phase>":    { "readings": { metric: {"mean": float, "noise": float} } },
            ...
        }
    """

    def __init__(self, spec_path: Path | str, rng: random.Random | None = None) -> None:
        self._spec: dict[str, Any] = json.loads(Path(spec_path).read_text())
        if "baseline" not in self._spec:
            raise ValueError(f"Scenario {spec_path} is missing required 'baseline' phase")
        self._rng = rng or random.Random()
        self._phase: str = "baseline"
        self.thresholds: dict[str, Any] = self._spec.get("thresholds", {})

    @property
    def current_phase(self) -> str:
        return self._phase

    def set_phase(self, phase: str) -> None:
        if phase not in self._spec or phase == "thresholds":
            raise ValueError(f"Unknown phase {phase!r}")
        self._phase = phase

    def sample(self, metric: str) -> float:
        readings = self._spec[self._phase]["readings"]
        if metric not in readings:
            raise KeyError(f"Metric {metric!r} not defined for phase {self._phase!r}")
        spec = readings[metric]
        mean = float(spec["mean"])
        noise = float(spec.get("noise", 0.0))
        if noise == 0.0:
            return mean
        return mean + self._rng.uniform(-noise, noise)

    def phase_spec(self, phase: str | None = None) -> dict[str, Any]:
        """Return the raw phase block — used by subclasses (e.g. imager) for non-reading data."""
        return self._spec[phase or self._phase]
