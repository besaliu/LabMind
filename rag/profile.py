"""Build a deterministic text profile from an experiment run directory.

The profile is the artifact both ingestion and querying produce. Embedding
asymmetry is the #1 silent failure mode for this kind of RAG; locking a fixed
template means a profile built today and a query built tomorrow embed into
comparable vectors.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from rag.models import ProfileDoc

INTERVENTION_DESCRIPTION_CAP = 5


def build_profile(run_id: str, data_root: str | os.PathLike[str]) -> ProfileDoc:
    run_dir = Path(data_root) / "experiments" / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"experiment run dir not found: {run_dir}")

    metadata = _load_metadata(run_dir / "metadata.json")
    temp_stats = _temp_stats(run_dir / "temp.csv", metadata)
    impurity_stats = _impurity_stats(run_dir / "impurity.csv")
    microscopy_stats = _microscopy_stats(run_dir / "microscopy.csv")
    interventions = _intervention_lines(run_dir / "interventions.json")
    report_body = _load_report(run_dir / "report.md")

    text = _render_profile_text(
        metadata=metadata,
        temp_stats=temp_stats,
        impurity_stats=impurity_stats,
        microscopy_stats=microscopy_stats,
        interventions=interventions,
        report_body=report_body,
    )
    summary = _render_summary(metadata, interventions_count=interventions["count"])
    chroma_metadata = _chroma_metadata(metadata)

    return ProfileDoc(
        run_id=run_id,
        text=text,
        summary=summary,
        metadata=chroma_metadata,
    )


def _load_metadata(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return json.load(f)


def _temp_stats(path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    """Count threshold violations using the schema's monitoring.temperature_c block.

    Falls back to the legacy flat `thresholds` block if present, so older
    seed data without `monitoring` still works.
    """
    if not path.exists():
        return {"present": False}
    temps: list[float] = []
    violations = 0
    monitoring = metadata.get("monitoring", {}) or {}
    temp_block = monitoring.get("temperature_c", {}) or {}
    legacy = metadata.get("thresholds", {}) or {}
    temp_max = temp_block.get("critical_above", legacy.get("temp_max_c"))
    temp_min = temp_block.get("critical_below", legacy.get("temp_min_c"))
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                t = float(row["temperature_c"])
            except (KeyError, ValueError):
                continue
            temps.append(t)
            if temp_max is not None and t > temp_max:
                violations += 1
            elif temp_min is not None and t < temp_min:
                violations += 1
    if not temps:
        return {"present": False}
    arr = np.array(temps)
    return {
        "present": True,
        "mean": float(arr.mean()),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "std": float(arr.std()),
        "violations": violations,
    }


def _impurity_stats(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"present": False}
    impurity: list[float] = []
    ph: list[float] = []
    saturation: list[float] = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                impurity.append(float(row["impurity_ppm"]))
                ph.append(float(row["ph"]))
                saturation.append(float(row["saturation_pct"]))
            except (KeyError, ValueError):
                continue
    if not impurity:
        return {"present": False}
    sat_trend = _trend(saturation)
    return {
        "present": True,
        "peak_impurity": float(max(impurity)),
        "ph_min": float(min(ph)),
        "ph_max": float(max(ph)),
        "saturation_trend": sat_trend,
    }


def _trend(values: list[float]) -> str:
    if len(values) < 3:
        return "flat"
    xs = np.arange(len(values), dtype=float)
    slope = float(np.polyfit(xs, np.array(values), 1)[0])
    # Slope thresholds tuned for saturation_pct (typically 70-90% range over ~17 samples).
    if slope > 0.1:
        return "rising"
    if slope < -0.1:
        return "falling"
    return "flat"


def _microscopy_stats(path: Path) -> dict[str, Any]:
    """Compute clarity and defect statistics from microscopy.csv.

    microscopy.csv is written by the VIX microscopy_imager on every analytics
    tick and by capture_image calls during active experiments. Columns:
        timestamp, clarity_pct, defect_count

    Returns a stats dict parallel to _temp_stats and _impurity_stats.
    Missing or empty file returns {"present": False} so the profile line is
    omitted rather than showing meaningless zeros.
    """
    if not path.exists():
        return {"present": False}
    clarity: list[float] = []
    defects: list[int] = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                clarity.append(float(row["clarity_pct"]))
                defects.append(int(float(row["defect_count"])))
            except (KeyError, ValueError):
                continue
    if not clarity:
        return {"present": False}
    arr = np.array(clarity)
    return {
        "present": True,
        "clarity_mean": float(arr.mean()),
        "clarity_min": float(arr.min()),
        "peak_defect_count": max(defects),
    }


def _intervention_lines(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"count": 0, "descriptions": []}
    try:
        with path.open() as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return {"count": 0, "descriptions": []}
    if not isinstance(data, list):
        return {"count": 0, "descriptions": []}
    descriptions = []
    for entry in data[:INTERVENTION_DESCRIPTION_CAP]:
        action = entry.get("action", "").strip()
        if action:
            descriptions.append(action)
    return {"count": len(data), "descriptions": descriptions}


def _render_profile_text(
    metadata: dict[str, Any],
    temp_stats: dict[str, Any],
    impurity_stats: dict[str, Any],
    microscopy_stats: dict[str, Any],
    interventions: dict[str, Any],
    report_body: str,
) -> str:
    params = metadata.get("parameters", {})
    param_parts = [
        f"target_temp={params.get('target_temp_c', '?')}C",
        f"cooling_rate={params.get('cooling_rate_c_per_hour', '?')}C/hr",
        f"growth_duration={params.get('growth_duration_hours', '?')}h",
        f"substrate={params.get('substrate', '?')}",
    ]

    lines = [
        f"Hypothesis: {metadata.get('hypothesis', '')}",
        f"Instruments: {', '.join(metadata.get('instruments', []))}",
        f"Parameters: {', '.join(param_parts)}",
        f"Success criteria: {_render_success_criteria(metadata.get('success_criteria'))}",
        f"Status: {metadata.get('status', '')} ({metadata.get('outcome', 'unknown')})",
        f"Key findings: {_join_list(metadata.get('key_findings'))}",
        f"Risks: {_join_list(metadata.get('known_risks'))}",
    ]
    if temp_stats.get("present"):
        lines.append(
            f"Temperature: mean={temp_stats['mean']:.2f}C, "
            f"min={temp_stats['min']:.2f}C, max={temp_stats['max']:.2f}C, "
            f"stddev={temp_stats['std']:.2f}C, "
            f"threshold_violations={temp_stats['violations']}"
        )
    if impurity_stats.get("present"):
        lines.append(
            f"Impurity: peak={impurity_stats['peak_impurity']:.1f}ppm, "
            f"pH range=[{impurity_stats['ph_min']:.2f}, {impurity_stats['ph_max']:.2f}], "
            f"saturation trend={impurity_stats['saturation_trend']}"
        )
    if microscopy_stats.get("present"):
        lines.append(
            f"Microscopy: clarity_mean={microscopy_stats['clarity_mean']:.1f}%, "
            f"clarity_min={microscopy_stats['clarity_min']:.1f}%, "
            f"peak_defects={microscopy_stats['peak_defect_count']}"
        )
    intervention_summary = (
        "; ".join(interventions["descriptions"]) if interventions["descriptions"] else "none"
    )
    lines.append(
        f"Interventions: {interventions['count']} total — {intervention_summary}"
    )
    if report_body:
        lines.append(f"Report:\n{report_body}")
    return "\n".join(lines)


def _render_success_criteria(criteria: Any) -> str:
    """Render success criteria as a flat readable string.

    Schema is a list of {metric, target} dicts. Older inline-string form is
    passed through unchanged.
    """
    if not criteria:
        return "none"
    if isinstance(criteria, str):
        return criteria
    if isinstance(criteria, list):
        parts = []
        for item in criteria:
            if isinstance(item, dict):
                metric = item.get("metric", "")
                target = item.get("target", "")
                if metric and target:
                    parts.append(f"{metric} {target}")
            elif isinstance(item, str) and item.strip():
                parts.append(item.strip())
        return ", ".join(parts) if parts else "none"
    return str(criteria)


def _join_list(values: Any) -> str:
    """Join a list of strings into a profile line; emit 'none' for missing/empty."""
    if not values:
        return "none"
    if isinstance(values, str):
        return values
    if isinstance(values, list):
        parts = [str(v).strip() for v in values if str(v).strip()]
        return "; ".join(parts) if parts else "none"
    return str(values)


def _load_report(path: Path) -> str:
    """Return the markdown body of report.md, or empty string if missing.

    Only finalized runs have a report. The ingest API filters to
    completed/failed runs, so this should always find a file in practice —
    but missing is handled gracefully so partial seed data doesn't break.
    """
    if not path.exists():
        return ""
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _render_summary(metadata: dict[str, Any], interventions_count: int) -> str:
    params = metadata.get("parameters", {})
    target = params.get("target_temp_c", "?")
    rate = params.get("cooling_rate_c_per_hour", "?")
    substrate = params.get("substrate", "?")
    status = metadata.get("status", "unknown")
    outcome = metadata.get("outcome", "unknown")
    return (
        f"{substrate} growth at {target}C, {rate}C/hr cooling — "
        f"{status} ({outcome}), {interventions_count} interventions"
    )


def _chroma_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Build a Chroma-storable metadata dict.

    Chroma metadata must be flat (str/int/float/bool only). Lists are joined
    into pipe-delimited strings for storage and split back in diff.py.
    """
    params = metadata.get("parameters", {})
    return {
        "run_id": metadata.get("run_id", ""),
        "status": metadata.get("status", ""),
        "outcome": metadata.get("outcome", "unknown"),
        "instruments": "|".join(metadata.get("instruments", [])),
        "substrate": params.get("substrate", ""),
        "target_temp_c": float(params.get("target_temp_c", 0.0) or 0.0),
        "cooling_rate_c_per_hour": float(params.get("cooling_rate_c_per_hour", 0.0) or 0.0),
        "growth_duration_hours": float(params.get("growth_duration_hours", 0.0) or 0.0),
        "start_time": metadata.get("start_time", ""),
    }
