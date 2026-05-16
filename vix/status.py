from __future__ import annotations

from typing import Any

Status = str  # "nominal" | "warning" | "critical"

_RANK = {"nominal": 0, "warning": 1, "critical": 2}


def compute_status(readings: dict[str, Any], thresholds: dict[str, dict[str, list[float]]]) -> Status:
    """Return the worst status implied by the current readings.

    Thresholds shape per metric: {"nominal": [lo, hi], "warning": [lo, hi]}.
    Bounds are inclusive. Anything outside the warning band is "critical".
    Metrics not in `thresholds` or non-numeric values are ignored.
    """
    worst: Status = "nominal"
    for metric, value in readings.items():
        if metric not in thresholds:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        spec = thresholds[metric]
        nom_lo, nom_hi = spec["nominal"]
        warn_lo, warn_hi = spec["warning"]
        if nom_lo <= value <= nom_hi:
            level: Status = "nominal"
        elif warn_lo <= value <= warn_hi:
            level = "warning"
        else:
            level = "critical"
        if _RANK[level] > _RANK[worst]:
            worst = level
    return worst
