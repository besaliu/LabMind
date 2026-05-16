"""Dashboard bundle assembly.

Pre-processes a run's CSVs, interventions, and metadata into a single
ready-to-render JSON payload for the React dashboard. Includes contiguous
event-range derivation from the row-level `event` column added in the
per-run CSV schema.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import storage


# Tag → category mapping. Single source of truth for the dashboard's
# filter chips and band coloring. agent_intervention:* tags are
# intentionally excluded — those are rendered by the dashboard as
# cross-panel vertical lines sourced from interventions.json, not as
# background bands.
TAG_CATEGORIES: Dict[str, str] = {
    "impurity_rising_nominal_range":        "anomaly",
    "impurity_spike_rate_5ppm_per_min":     "anomaly",
    "ph_monotonic_drift_detected":          "anomaly",
    "temp_probe_lag_suspected":             "anomaly",
    "minor_surface_stress_observed":        "anomaly",
    "impurity_above_warning_threshold":     "threshold",
    "impurity_recovering":                  "recovery",
    "ph_drift_arrested":                    "recovery",
    "temp_dip_confirmed_post_intervention": "recovery",
}


# Per-CSV schema: which fields are numeric and need float coercion.
_NUMERIC_FIELDS = {
    "temp":       ("temperature_c", "setpoint_c"),
    "impurity":   ("impurity_ppm", "saturation_pct", "ph"),
    "microscopy": ("clarity_pct", "defect_count"),
}

_CSV_FILES = {
    "temp":       "temp.csv",
    "impurity":   "impurity.csv",
    "microscopy": "microscopy.csv",
}


def _coerce_row(row: Dict[str, str], panel: str) -> Dict[str, Any]:
    """Return a row with numeric fields coerced to float, blank event → None."""
    out: Dict[str, Any] = {"t": row.get("timestamp")}
    for field in _NUMERIC_FIELDS[panel]:
        raw = row.get(field, "")
        try:
            out[field] = float(raw) if raw not in ("", None) else None
        except (TypeError, ValueError):
            out[field] = None
    out["status"] = row.get("status") or None
    event = row.get("event")
    out["event"] = event if event else None
    return out


def _compute_event_ranges(panel: str, rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Walk rows in order, emit one range per run of consecutive same-tag rows.

    Range end is the NEXT row's timestamp (so single-row tags still produce
    visible bands and adjacent different-tag ranges touch cleanly without
    overlap). `agent_intervention:*` tags are skipped — they're handled
    separately by the dashboard via interventions.json.
    """
    ranges: List[Dict[str, Any]] = []
    n = len(rows)
    i = 0
    while i < n:
        tag = rows[i].get("event") or ""
        if not tag or tag.startswith("agent_intervention"):
            i += 1
            continue
        j = i
        while j + 1 < n and rows[j + 1].get("event") == tag:
            j += 1
        start = rows[i]["timestamp"]
        end = rows[j + 1]["timestamp"] if j + 1 < n else rows[j]["timestamp"]
        ranges.append({
            "panel": panel,
            "tag": tag,
            "category": TAG_CATEGORIES.get(tag, "anomaly"),
            "start": start,
            "end": end,
        })
        i = j + 1
    return ranges


def _extract_thresholds(meta: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Pull threshold bounds out of metadata.monitoring for each panel."""
    monitoring = meta.get("monitoring") or {}
    return {
        "temp":     _threshold_block(monitoring.get("temperature_c") or {}),
        "impurity": _threshold_block(monitoring.get("impurity_ppm") or {}),
        "ph":       _threshold_block(monitoring.get("ph") or {}),
    }


def _threshold_block(block: Dict[str, Any]) -> Dict[str, Any]:
    return {
        k: block.get(k)
        for k in ("target", "warning_above", "critical_above", "warning_below", "critical_below")
        if block.get(k) is not None
    }


def _read_microscopy_snapshot(run_id: str) -> Optional[Dict[str, Any]]:
    """End-of-run microscopy.json (separate from the timeseries microscopy.csv)."""
    path = storage.run_dir(run_id) / "microscopy.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def build_bundle(run_id: str) -> Dict[str, Any]:
    """Assemble the full dashboard bundle for one run.

    Raises FileNotFoundError if metadata.json is missing — callers convert this
    to an HTTP 404.
    """
    meta = storage.read_metadata(run_id)  # FileNotFoundError → 404 upstream

    series: Dict[str, List[Dict[str, Any]]] = {}
    event_ranges: List[Dict[str, Any]] = []
    for panel, filename in _CSV_FILES.items():
        rows = storage.read_csv_rows(run_id, filename)
        series[panel] = [_coerce_row(r, panel) for r in rows]
        event_ranges.extend(_compute_event_ranges(panel, rows))

    return {
        "run_id": run_id,
        "metadata": meta,
        "interventions": storage.read_interventions(run_id),
        "microscopy_snapshot": _read_microscopy_snapshot(run_id),
        "series": series,
        "event_ranges": event_ranges,
        "thresholds": _extract_thresholds(meta),
    }
